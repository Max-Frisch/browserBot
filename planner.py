import os
import json
import re
import time
import random
from playwright.sync_api import Page
from config import BASE_URL, BUILD_QUEUE_FILE, safe_goto, get_planet_url, human_delay
from telemetry import TelemetryManager

# Builds under this duration remain in the fast parallel batch loop
FAST_BUILD_THRESHOLD = 45

# Actual GigraWars research topics parsed from UI / tech trees
KNOWN_GIGRAWARS_RESEARCH = {
    "combustion drive", "ion drive", "space curvature drive", "space folding drive",
    "spy technology", "computer technology", "weapon technology", "shield technology",
    "armor technology", "ionization", "explosive projectiles", "energy focusing",
    "recycling technology", "advanced ship armor"
}


class PlannerManager:
    def __init__(self, page: Page, telemetry: TelemetryManager):
        self.page = page
        self.telemetry = telemetry

    def load_queue_data(self) -> dict:
        """Loads complete build queue structure from build_queue.json."""
        if os.path.exists(BUILD_QUEUE_FILE):
            with open(BUILD_QUEUE_FILE, "r") as f:
                return json.load(f)
        return {"main_planet": "3:7:1", "research_goals": [], "planets": {}}

    def _save_queue_data(self, data: dict):
        """Writes updated JSON structure back to build_queue.json."""
        with open(BUILD_QUEUE_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def remove_completed_goal(self, goal_to_remove: dict, coords: str = None, is_research: bool = False):
        """Removes a finished goal from the appropriate list in build_queue.json."""
        data = self.load_queue_data()
        goal_name = goal_to_remove.get("name", "").lower()
        goal_type = goal_to_remove.get("type", "")

        if is_research:
            data["research_goals"] = [
                g for g in data.get("research_goals", [])
                if not (g.get("name", "").lower() == goal_name and g.get("type") == goal_type)
            ]
        elif coords and coords in data.get("planets", {}):
            data["planets"][coords] = [
                g for g in data["planets"][coords]
                if not (g.get("name", "").lower() == goal_name and g.get("type") == goal_type)
            ]
        self._save_queue_data(data)
        print(
            f"[Planner JSON] Removed completed goal '{goal_to_remove.get('name')}' from build_queue.json on [{coords or 'global'}].")

    def update_unit_goal_amount(self, goal: dict, built_amount: int, coords: str):
        """Deducts the built quantity from the requested unit order in build_queue.json."""
        data = self.load_queue_data()
        planet_goals = data.get("planets", {}).get(coords, [])
        for g in planet_goals:
            if g.get("type") == goal.get("type") and g.get("name", "").lower() == goal.get("name", "").lower():
                remaining = g.get("amount", 0) - built_amount
                if remaining <= 0:
                    planet_goals.remove(g)
                    print(
                        f"[Planner JSON] Order complete for '{goal.get('name')}' on [{coords}]. Removed from JSON.")
                else:
                    g["amount"] = remaining
                    print(
                        f"[Planner JSON] [{coords}] Partially built {built_amount}x '{goal.get('name')}'. Remaining: {remaining}.")
                break
        self._save_queue_data(data)

    def get_unmet_prerequisites(self, target_name: str, coords: str = "3:7:1", category: str = "building") -> list[dict]:
        """Checks the Technology tab for missing prerequisites (only red text-danger spans)."""
        category_endpoints = {
            "building": "technology-tree/building",
            "research": "technology-tree/research",
            "ship": "technology-tree/ship",
            "defense": "technology-tree/defense"
        }
        endpoint = category_endpoints.get(category, "technology-tree/building")
        safe_goto(self.page, get_planet_url(coords, endpoint))

        target_row = self.page.locator("tr", has=self.page.locator(
            "a", has_text=re.compile(rf"\b{re.escape(target_name)}\b", re.IGNORECASE)))
        missing = []

        if target_row.count() > 0:
            unmet_spans = target_row.locator("span.text-danger").all()
            for span in unmet_spans:
                ratio_text = span.inner_text().strip()
                match_ratio = re.search(r"\((\d+)/(\d+)\)", ratio_text)
                if not match_ratio:
                    continue

                curr_lvl = int(match_ratio.group(1))
                req_lvl = int(match_ratio.group(2))

                parent_td = span.locator("xpath=..")
                cell_text = parent_td.inner_text()

                for line in cell_text.split("\n"):
                    if ratio_text in line:
                        req_name = re.sub(r"\(\d+/\d+\)", "", line).strip()
                        if req_name:
                            missing.append(
                                {"name": req_name, "current": curr_lvl, "required": req_lvl})
                        break
        return missing

    def process_goals(self) -> dict[str, int]:
        """
        Processes goals across Building, Research, Ship, and Defense queues per planet using Parallel Batching.
        Leverages /app/empire overview for zero-overhead level validation and queue tracking.
        Returns active_timers: {planet_coords: remaining_seconds} across the empire for adaptive sleep.
        """
        queue_data = self.load_queue_data()
        main_coords = queue_data.get("main_planet", "3:7:1")
        research_goals = queue_data.get("research_goals", [])

        empire_active_timers: dict[str, int] = {}

        # 0. Fetch live empire overview to fast-track levels and active timers
        empire = self.telemetry.get_empire_overview(force_refresh=True)

        # Pre-seed active building queues from empire overview
        busy_building_planets: dict[str, float] = {}
        for p, b_info in empire.get("building_queues", {}).items():
            rem = b_info.get("remaining_seconds", 0)
            if rem > 0:
                busy_building_planets[p] = time.time() + rem
                empire_active_timers[p] = rem

        # Pre-validate all building goals against known empire building levels
        planets_dict = queue_data.get("planets", {})
        for coords, goals in list(planets_dict.items()):
            for g in list(goals):
                if g.get("type") == "building":
                    g_name = g.get("name", "")
                    target_lvl = g.get("level", 99)
                    curr_lvl = empire.get("building_levels", {}).get(coords, {}).get(g_name.lower())
                    if curr_lvl is not None and curr_lvl >= target_lvl:
                        print(
                            f"[Planner Empire] '{g_name}' already at level {curr_lvl} (Target: {target_lvl}) on [{coords}]. Marking complete.")
                        self.remove_completed_goal(g, coords=coords)

        # 1. Process Global Research (Main Planet Only)
        is_research_busy, r_remaining = self.telemetry.get_queue_status(
            "research", coords=main_coords)
        if not is_research_busy and research_goals:
            research_goal = research_goals[0]
            status, dur = self._resolve_and_upgrade(
                research_goal, coords=main_coords, is_research=True)
            if status in ("UPGRADED", "BUSY") and dur > 0:
                empire_active_timers[f"{main_coords}:research"] = dur
        elif is_research_busy and r_remaining > 0:
            empire_active_timers[f"{main_coords}:research"] = r_remaining

        # 2. Parallel Building Loop across all planets
        while True:
            fresh_data = self.load_queue_data()
            planets_map = fresh_data.get("planets", {})
            fast_build_durations = []
            loop_now = time.time()

            for coords in list(planets_map.keys()):
                # If we know this planet is currently busy with a long build, check if still running
                if coords in busy_building_planets:
                    remaining_busy = busy_building_planets[coords] - loop_now
                    if remaining_busy > 3:
                        empire_active_timers[coords] = int(remaining_busy)
                        continue
                    else:
                        del busy_building_planets[coords]

                current_goals = planets_map.get(coords, [])
                building_goal = next(
                    (g for g in current_goals if g.get("type") == "building"), None)

                if building_goal:
                    status, dur = self._resolve_and_upgrade(
                        building_goal, coords=coords)

                    if status == "UPGRADED":
                        if dur <= FAST_BUILD_THRESHOLD:
                            fast_build_durations.append(dur)
                        else:
                            busy_building_planets[coords] = time.time() + dur
                            empire_active_timers[coords] = dur
                    elif status == "BUSY":
                        busy_building_planets[coords] = time.time() + dur
                        empire_active_timers[coords] = dur
                    elif status == "COMPLETED":
                        pass  # Goal was satisfied and removed from JSON

            if fast_build_durations:
                # Add human-like dynamic buffer to batch completion wait
                buffer_sec = random.uniform(2.5, 4.2)
                wait_time = max(fast_build_durations) + buffer_sec
                print(
                    f"[*] Parallel batch queued ({fast_build_durations}s). Waiting {round(wait_time, 1)}s for batch completion...")
                time.sleep(wait_time)
            else:
                break

        # 3. Process Ship & Defense orders per Planet
        fresh_data = self.load_queue_data()
        for coords, goals in fresh_data.get("planets", {}).items():
            unit_goals = [g for g in goals if g.get(
                "type") in ["ship", "defense"]]
            for u_goal in unit_goals:
                self._build_units(u_goal, coords=coords)

        return empire_active_timers

    def _resolve_and_upgrade(self, goal: dict, coords: str = "3:7:1", is_research: bool = False) -> tuple[str, int]:
        """
        Resolves prerequisites recursively and triggers building/research upgrades.
        Returns a tuple: (status: str, duration_sec: int)
        Statuses:
          'UPGRADED': Upgrade button was clicked, duration is the build duration.
          'BUSY': Queue is already busy, duration is remaining seconds.
          'COMPLETED': Current level >= target level, goal satisfied.
          'UNAVAILABLE': Upgrade button missing or prerequisite locked.
        """
        goal_type = goal.get("type", "research" if is_research else "building")
        goal_name = goal.get("name")
        target_level = goal.get("level", 99)

        missing_reqs = self.get_unmet_prerequisites(
            goal_name, coords=coords, category=goal_type)
        if missing_reqs:
            sub_req = missing_reqs[0]
            sub_name = sub_req["name"]

            is_sub_req_research = is_research or (
                sub_name.lower() in KNOWN_GIGRAWARS_RESEARCH)

            queue_data = self.load_queue_data()
            main_coords = queue_data.get("main_planet", "3:7:1")

            target_coords = main_coords if is_sub_req_research else coords
            target_type = "research" if is_sub_req_research else "building"

            print(
                f"[Planner] [{coords}] '{goal_name}' needs '{sub_name}' ({sub_req['current']}/{sub_req['required']}). Pivoting -> '{sub_name}' on [{target_coords}].")
            return self._resolve_and_upgrade(
                {"type": target_type, "name": sub_name,
                    "level": sub_req["required"]},
                coords=target_coords,
                is_research=is_sub_req_research
            )

        endpoint = "research" if goal_type == "research" else "building"
        safe_goto(self.page, get_planet_url(coords, endpoint))

        # --- SAFEGUARD 1: Direct On-Page Active Queue Check ---
        timer_loc = self.page.locator(".timer-timestamp").first
        if timer_loc.count() > 0 and timer_loc.is_visible():
            target_unix_str = timer_loc.get_attribute("data-time")
            if target_unix_str:
                remaining = max(0, int(target_unix_str) - int(time.time()))

                # If queue timer has only <= 3 seconds left, settle and reload
                if 0 < remaining <= 3:
                    settle_sec = remaining + random.uniform(1.0, 1.8)
                    print(
                        f"[*] [{coords}] {endpoint.capitalize()} queue has only {remaining}s left. Settling {round(settle_sec, 1)}s for completion...")
                    time.sleep(settle_sec)
                    self.page.reload()
                    self.page.wait_for_load_state("networkidle")
                    timer_loc = self.page.locator(".timer-timestamp").first
                    target_unix_str = timer_loc.get_attribute(
                        "data-time") if (timer_loc.count() > 0 and timer_loc.is_visible()) else None
                    remaining = max(
                        0, int(target_unix_str) - int(time.time())) if target_unix_str else 0

                if remaining > 0:
                    print(
                        f"[-] [{coords}] {endpoint.capitalize()} queue is currently busy ({remaining}s remaining). Skipping upgrade.")
                    return ("BUSY", remaining)

        item_card = self.page.locator(
            ".full-w-entry", has_text=re.compile(rf"\b{re.escape(goal_name)}\b", re.IGNORECASE)).first
        if item_card.count() == 0:
            print(
                f"[-] [{coords}] Item card for '{goal_name}' not found on {endpoint}.")
            return ("UNAVAILABLE", 0)

        card_text = item_card.inner_text()

        # Parse current level ONLY from the item's own header/title section
        # Never match prerequisite description text like "Requires Drilling Tower Level 10"
        header_text = re.split(
            r"requires|benötigt|prerequisite|duration|dauer|kosten|cost",
            card_text,
            flags=re.IGNORECASE
        )[0]

        lvl_match = re.search(r"(?:Level|Stufe)\s*(\d+)", header_text, re.IGNORECASE)
        if not lvl_match:
            # Fallback to first line of the card
            first_line = card_text.splitlines()[0] if card_text else ""
            lvl_match = re.search(r"(?:Level|Stufe)\s*(\d+)", first_line, re.IGNORECASE)

        current_level = int(lvl_match.group(1)) if lvl_match else 0

        upgrade_btn = item_card.get_by_role("link", name=re.compile(
            r"(Upgrade|Research|Ausbauen|Erforschen)", re.IGNORECASE)).first

        # Cross-validate current level against upgrade button text if available
        if upgrade_btn.count() > 0 and upgrade_btn.is_visible():
            btn_text = upgrade_btn.inner_text()
            btn_lvl_match = re.search(r"(\d+)", btn_text)
            if btn_lvl_match:
                next_level = int(btn_lvl_match.group(1))
                if next_level > target_level:
                    print(
                        f"[Planner Filter] [{coords}] '{goal_name}' button targets level {next_level}, but goal target is {target_level}. Goal satisfied.")
                    self.remove_completed_goal(
                        goal, coords=coords, is_research=is_research)
                    return ("COMPLETED", 0)
                # Next level tells us the exact current level
                current_level = max(current_level, next_level - 1)

        if current_level >= target_level:
            self.remove_completed_goal(
                goal, coords=coords, is_research=is_research)
            return ("COMPLETED", 0)

        if upgrade_btn.count() > 0 and upgrade_btn.is_visible():
            dur_match = re.search(
                r"Duration\s*(\d{2}):(\d{2}):(\d{2})", card_text, re.IGNORECASE)
            build_seconds = 0
            if dur_match:
                h, m, s = map(int, dur_match.groups())
                build_seconds = h * 3600 + m * 60 + s

            print(f"[*] [{coords}] Upgrading '{goal_name}' ({current_level} -> {current_level + 1} | Target: {target_level}) | Build Time: {build_seconds}s")
            
            # Subtle human hesitation before clicking upgrade
            human_delay(0.35, 0.75)
            upgrade_btn.click()
            self.page.wait_for_load_state("networkidle")

            # If target reached with this upgrade, remove goal from queue
            if current_level + 1 >= target_level:
                self.remove_completed_goal(
                    goal, coords=coords, is_research=is_research)

            return ("UPGRADED", build_seconds)
        else:
            print(
                f"[-] [{coords}] Upgrade button for '{goal_name}' unavailable (insufficient resources or locked).")
            return ("UNAVAILABLE", 0)

    def _build_units(self, goal: dict, coords: str = "3:7:1"):
        """Orders ships or defense turrets, handling partial orders and JSON cleanup."""
        goal_name = goal.get("name")
        requested_amount = goal.get("amount", 1)
        category = goal.get("type", "ship")

        missing_reqs = self.get_unmet_prerequisites(
            goal_name, coords=coords, category=category)
        if missing_reqs:
            sub_req = missing_reqs[0]
            sub_name = sub_req["name"]
            is_sub_req_research = sub_name.lower() in KNOWN_GIGRAWARS_RESEARCH

            queue_data = self.load_queue_data()
            main_coords = queue_data.get("main_planet", "3:7:1")
            target_coords = main_coords if is_sub_req_research else coords
            target_type = "research" if is_sub_req_research else "building"

            print(
                f"[Planner Unit] [{coords}] Cannot build '{goal_name}'. Missing prerequisite: '{sub_name}'. Pivoting -> '{sub_name}' on [{target_coords}].")
            self._resolve_and_upgrade(
                {"type": target_type, "name": sub_name,
                    "level": sub_req["required"]},
                coords=target_coords,
                is_research=is_sub_req_research
            )
            return

        endpoint = "ship" if category == "ship" else "defense"
        safe_goto(self.page, get_planet_url(coords, endpoint))

        cards = self.page.locator(".full-w-entry").all()
        target_card = None

        for card in cards:
            if re.search(rf"\b{re.escape(goal_name)}\b", card.inner_text(), re.IGNORECASE):
                target_card = card
                break

        if not target_card:
            print(
                f"[Planner Unit] [{coords}] Card for '{goal_name}' not found on page.")
            return

        input_box = target_card.locator(
            "input[type='number'], input[type='text']").first
        global_build_btn = self.page.locator(
            "#add_combat_units_to_queue_send, button[type='submit']").first

        if not input_box.is_visible() or not global_build_btn.is_visible():
            print(
                f"[-] [{coords}] Input field or global Build button unavailable for '{goal_name}'.")
            return

        card_text = target_card.inner_text()
        max_match = re.search(r"max\.?\s*(\d+)", card_text, re.IGNORECASE)
        max_affordable = int(max_match.group(
            1)) if max_match else requested_amount

        build_quantity = min(requested_amount, max_affordable)

        if build_quantity <= 0:
            print(
                f"[-] [{coords}] Insufficient resources to build any '{goal_name}'. Leaving in To-Do queue.")
            return

        print(f"[*] [{coords}] Ordering {build_quantity}x '{goal_name}' (Requested: {requested_amount} | Max Affordable: {max_affordable})...")

        input_box.fill(str(build_quantity))
        human_delay(0.3, 0.65)
        global_build_btn.click()
        self.page.wait_for_load_state("networkidle")

        self.update_unit_goal_amount(goal, build_quantity, coords=coords)
