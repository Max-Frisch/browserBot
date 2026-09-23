import os
import json
import re
import time
from playwright.sync_api import Page
from config import BASE_URL, BUILD_QUEUE_FILE, safe_goto, get_planet_url
from telemetry import TelemetryManager

FAST_BUILD_THRESHOLD = 15

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
        if is_research:
            data["research_goals"] = [g for g in data.get(
                "research_goals", []) if g != goal_to_remove]
        elif coords and coords in data.get("planets", {}):
            data["planets"][coords] = [
                g for g in data["planets"][coords] if g != goal_to_remove]
        self._save_queue_data(data)
        print(
            f"[Planner JSON] Removed completed goal '{goal_to_remove.get('name')}' from build_queue.json.")

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
            "a", has_text=re.compile(rf"^{target_name}$", re.IGNORECASE)))
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

    def process_goals(self):
        """Processes goals across Building, Research, Ship, and Defense queues per planet using Parallel Batching."""
        queue_data = self.load_queue_data()
        main_coords = queue_data.get("main_planet", "3:7:1")
        planets_dict = queue_data.get("planets", {})
        research_goals = queue_data.get("research_goals", [])

        # 1. Process Global Research (Main Planet Only)
        is_research_busy, _ = self.telemetry.get_queue_status(
            "research", coords=main_coords)
        if not is_research_busy and research_goals:
            research_goal = research_goals[0]
            self._resolve_and_upgrade(
                research_goal, coords=main_coords, is_research=True)

        # 2. Parallel Building Loop across all planets
        while True:
            fresh_data = self.load_queue_data()
            planets_map = fresh_data.get("planets", {})
            busy_building_planets = self.telemetry.get_busy_building_planets(
                coords=main_coords)

            fast_build_durations = []

            for coords in list(planets_map.keys()):
                if coords in busy_building_planets:
                    continue

                current_goals = planets_map.get(coords, [])
                building_goal = next(
                    (g for g in current_goals if g.get("type") == "building"), None)

                if building_goal:
                    build_sec = self._resolve_and_upgrade(
                        building_goal, coords=coords)
                    if build_sec is not None and build_sec > 0:
                        if build_sec <= FAST_BUILD_THRESHOLD:
                            fast_build_durations.append(build_sec)
                        else:
                            busy_building_planets[coords] = build_sec

            if fast_build_durations:
                wait_time = max(2, max(fast_build_durations) + 2)
                print(
                    f"[*] Parallel batch queued ({fast_build_durations}s). Waiting {wait_time}s for batch completion...")
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

    def _resolve_and_upgrade(self, goal: dict, coords: str = "3:7:1", is_research: bool = False) -> int | None:
        """Resolves prerequisites recursively and triggers building/research upgrades."""
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
                if remaining > 0:
                    print(
                        f"[-] [{coords}] {endpoint.capitalize()} queue is currently busy ({remaining}s remaining). Skipping upgrade.")
                    return remaining

        item_card = self.page.locator(
            ".full-w-entry", has_text=re.compile(rf"\b{re.escape(goal_name)}\b", re.IGNORECASE)).first
        if item_card.count() == 0:
            print(
                f"[-] [{coords}] Item card for '{goal_name}' not found on {endpoint}.")
            return None

        card_text = item_card.inner_text()
        lvl_match = re.search(r"(?:Level|Stufe)\s*(\d+)",
                              card_text, re.IGNORECASE)
        current_level = int(lvl_match.group(1)) if lvl_match else 0

        if current_level >= target_level:
            self.remove_completed_goal(
                goal, coords=coords, is_research=is_research)
            return None

        upgrade_btn = item_card.get_by_role("link", name=re.compile(
            r"(Upgrade|Research)", re.IGNORECASE)).first

        if upgrade_btn.is_visible():
            # --- SAFEGUARD 2: Button Target Level Validation ---
            btn_text = upgrade_btn.inner_text()
            btn_lvl_match = re.search(r"(\d+)", btn_text)
            if btn_lvl_match:
                next_level = int(btn_lvl_match.group(1))
                if next_level > target_level:
                    print(
                        f"[Planner Filter] [{coords}] '{goal_name}' button targets level {next_level}, but goal target is {target_level}. Queue active or goal satisfied.")
                    return None

            dur_match = re.search(
                r"Duration\s*(\d{2}):(\d{2}):(\d{2})", card_text, re.IGNORECASE)
            build_seconds = 0
            if dur_match:
                h, m, s = map(int, dur_match.groups())
                build_seconds = h * 3600 + m * 60 + s

            print(f"[*] [{coords}] Upgrading '{goal_name}' ({current_level} -> {current_level + 1} | Target: {target_level}) | Build Time: {build_seconds}s")
            upgrade_btn.click()
            self.page.wait_for_load_state("networkidle")

            return build_seconds
        else:
            print(
                f"[-] [{coords}] Upgrade button for '{goal_name}' unavailable (insufficient resources?).")
            return None

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
        global_build_btn.click()
        self.page.wait_for_load_state("networkidle")

        self.update_unit_goal_amount(goal, build_quantity, coords=coords)
