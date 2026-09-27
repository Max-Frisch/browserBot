import os
import json
import re
import time
import random
from playwright.sync_api import Page
from config import BASE_URL, BUILD_QUEUE_FILE, safe_goto, get_planet_url, human_delay
from config import add_ship_queue_entry, SHIP_ORIGIN_USER
from telemetry import TelemetryManager

FAST_BUILD_THRESHOLD = 45

KNOWN_GIGRAWARS_RESEARCH = {
    "combustion drive", "ion drive", "space curvature drive", "space folding drive",
    "spy technology", "computer technology", "weapon technology", "shield technology",
    "armor technology", "ionization", "explosive projectiles", "energy focusing",
    "recycling technology", "advanced ship armor"
}

WILDCARD_KEYS = ["*", "default", "all", "template"]

# Expanded alias map for localized or alternate UI building & unit names
NAME_ALIASES = {
    "iron mine": ["iron mine", "eisenmine"],
    "lutinum refinery": ["lutinum refinery", "lutinumraffinerie", "lutinum-raffinerie"],
    "water pump": ["water pump", "wasserpumpe"],
    "solar power plant": ["solar power plant", "solarkraftwerk"],
    "fusion power plant": ["fusion power plant", "fusionskraftwerk"],
    "hydrogen drill": ["hydrogen drill", "wasserstoffbohrer"],
    "iron storage": ["iron storage", "eisenspeicher"],
    "lutinum storage": ["lutinum storage", "lutinumspeicher"],
    "water storage": ["water storage", "wasserspeicher"],
    "hydrogen tanks": ["hydrogen tanks", "wasserstofftanks", "wasserstoffspeicher"],
    "research center": ["research center", "research lab", "forschungszentrum", "forschungslabor"],
    "ship factory": ["ship factory", "shipyard", "schiffsfabrik", "schiffswerft"],
    "defense platform": ["defense platform", "defense facility", "verteidigungsanlage", "verteidigungsplattform"],
    "orbital defense station": ["orbital defense station", "verteidigungsstation"],
    "planetary shield": ["planetary shield", "planetarschild"],
    "fusion reactor": ["fusion reactor", "fusionsreaktor"],
    "trading post": ["trading post", "handelsposten"],
    "command center": ["command center", "kommandozentrale"],
    "drilling tower": ["drilling tower", "bohrturm"],
    "chemical factory": ["chemical factory", "chemiefabrik"],
    "advanced chemical factory": ["advanced chemical factory", "erweiterte chemiefabrik"]
}


def clean_item_name(raw_text: str) -> str:
    """Strips 'Requires', 'Benötigt', level/stufe suffixes/prefixes, quantities, and delimiters."""
    text = raw_text.strip()
    text = re.sub(r"^\d+x?\s*", "", text)
    text = re.sub(
        r"(?i)^(?:requires|benötigt|prerequisite[s]?)\s*:?\s*", "", text)
    text = re.sub(
        r"(?i)\s*[\-\|:\(]?(?:\s*level|\s*stufe)?\s*\d+\)?.*$", "", text)
    return text.strip(" -|:\t\n\r[]()")


def is_name_match(candidate_raw: str, target_goal: str) -> bool:
    c_clean = clean_item_name(candidate_raw).lower()
    t_clean = target_goal.lower()
    if c_clean == t_clean:
        return True
    aliases = NAME_ALIASES.get(t_clean, [t_clean])
    return c_clean in aliases


class PlannerManager:
    def __init__(self, page: Page, telemetry: TelemetryManager):
        self.page = page
        self.telemetry = telemetry

    def load_queue_data(self) -> dict:
        """Loads complete build queue structure from build_queue.json with retry handling."""
        if os.path.exists(BUILD_QUEUE_FILE):
            for attempt in range(3):
                try:
                    with open(BUILD_QUEUE_FILE, "r", encoding="utf-8") as f:
                        return json.load(f)
                except (json.JSONDecodeError, OSError):
                    time.sleep(0.05)
                except Exception as e:
                    print(f"[!] Planner load error attempt #{attempt+1}: {e}")
                    time.sleep(0.05)
        return {"main_planet": "2:30:3", "research_goals": [], "planets": {}}

    def _save_queue_data(self, data: dict):
        """Atomically writes updated JSON structure back to build_queue.json."""
        temp_file = f"{BUILD_QUEUE_FILE}.tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, BUILD_QUEUE_FILE)
        except Exception as e:
            print(f"[!] Planner Atomic Save Error: {e}")
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

    def get_plan_for_coords(self, coords: str, q_data: dict) -> list[dict]:
        """
        Resolves build queue items for given coordinates.
        Supports exact coordinate lookup, or wildcard '*', 'default', 'all', 'template'.
        """
        planets_dict = q_data.get("planets", {})
        if coords and coords in planets_dict and len(planets_dict[coords]) > 0:
            return planets_dict[coords]

        for wildcard in WILDCARD_KEYS:
            if wildcard in planets_dict and len(planets_dict[wildcard]) > 0:
                return planets_dict[wildcard]

        main_coords = q_data.get("main_planet", "2:30:3")
        if main_coords in planets_dict and len(planets_dict[main_coords]) > 0:
            return planets_dict[main_coords]

        return []

    def remove_completed_goal(self, goal_to_remove: dict, coords: str = None, is_research: bool = False):
        """Removes a finished goal from the appropriate list in build_queue.json if explicitly assigned."""
        data = self.load_queue_data()
        goal_name = goal_to_remove.get("name", "").lower()
        goal_type = goal_to_remove.get("type", "")

        if is_research:
            data["research_goals"] = [
                g for g in data.get("research_goals", [])
                if not (g.get("name", "").lower() == goal_name and g.get("type") == goal_type)
            ]
            self._save_queue_data(data)
            print(
                f"[Planner JSON] Removed completed research goal '{goal_to_remove.get('name')}'.")
        elif coords and coords in data.get("planets", {}) and len(data["planets"][coords]) > 0:
            data["planets"][coords] = [
                g for g in data["planets"][coords]
                if not (g.get("name", "").lower() == goal_name and g.get("type") == goal_type)
            ]
            self._save_queue_data(data)
            print(
                f"[Planner JSON] Removed completed goal '{goal_to_remove.get('name')}' from build_queue.json on [{coords}].")

    def update_unit_goal_amount(self, goal: dict, built_amount: int, coords: str):
        """Deducts the built quantity from the requested unit order in build_queue.json."""
        data = self.load_queue_data()
        planets_dict = data.get("planets", {})

        target_list = None
        if coords in planets_dict and len(planets_dict[coords]) > 0:
            target_list = planets_dict[coords]
        else:
            for wk in WILDCARD_KEYS:
                if wk in planets_dict and len(planets_dict[wk]) > 0:
                    target_list = planets_dict[wk]
                    break

        if not target_list:
            return

        for g in target_list:
            if g.get("type") == goal.get("type") and g.get("name", "").lower() == goal.get("name", "").lower():
                remaining = g.get("amount", 0) - built_amount
                if remaining <= 0:
                    target_list.remove(g)
                    print(
                        f"[Planner JSON] Order complete for '{goal.get('name')}' on [{coords}]. Removed from JSON.")
                else:
                    g["amount"] = remaining
                    print(
                        f"[Planner JSON] [{coords}] Partially built {built_amount}x '{goal.get('name')}'. Remaining: {remaining}.")
                break
        self._save_queue_data(data)

    def get_unmet_prerequisites(self, target_name: str, coords: str = "2:30:3", category: str = "building") -> list[dict]:
        """Checks the Technology tab for missing prerequisites (only red text-danger spans)."""
        category_endpoints = {
            "building": "technology-tree/building",
            "research": "technology-tree/research",
            "ship": "technology-tree/ship",
            "defense": "technology-tree/defense"
        }
        endpoint = category_endpoints.get(category, "technology-tree/building")
        safe_goto(self.page, get_planet_url(coords, endpoint))

        all_rows = self.page.locator("tr").all()
        target_row = None

        for row in all_rows:
            try:
                first_td = row.locator("td").first
                if first_td is not None and first_td.count() > 0:
                    item_title = first_td.inner_text().splitlines()[
                        0] if first_td.inner_text() else ""
                else:
                    row_text = row.inner_text()
                    lines = [l.strip()
                             for l in row_text.splitlines() if l.strip()]
                    item_title = lines[0] if lines else ""

                if is_name_match(item_title, target_name):
                    target_row = row
                    break
            except Exception:
                continue

        missing = []

        if target_row:
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
                        raw_req = re.sub(r"\(\d+/\d+\)", "", line).strip()
                        req_name = clean_item_name(raw_req)
                        if req_name:
                            missing.append(
                                {"name": req_name, "current": curr_lvl, "required": req_lvl})
                        break
        return missing

    def process_goals(self) -> dict[str, int]:
        """
        Processes goals across Building, Research, Ship, and Defense queues per planet using Parallel Batching.
        Leverages /app/empire overview for zero-overhead level validation and queue tracking.
        Supports wildcard planet blueprint templates ('*', 'default').
        Returns active_timers: {planet_coords: remaining_seconds} across the empire for adaptive sleep.
        """
        queue_data = self.load_queue_data()
        main_coords = queue_data.get("main_planet", "2:30:3")
        research_goals = queue_data.get("research_goals", [])

        empire_active_timers: dict[str, int] = {}
        empire = self.telemetry.get_empire_overview(force_refresh=True)

        active_planets = list(empire.get("building_levels", {}).keys())
        for c in queue_data.get("planets", {}).keys():
            if c not in active_planets and c not in WILDCARD_KEYS:
                active_planets.append(c)
        if not active_planets:
            active_planets = [main_coords]

        busy_building_planets: dict[str, float] = {}
        for p, b_info in empire.get("building_queues", {}).items():
            rem = b_info.get("remaining_seconds", 0)
            if rem > 0:
                busy_building_planets[p] = time.time() + rem
                empire_active_timers[p] = rem

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

        # 2. Parallel Building Loop across all active planets
        while True:
            fresh_data = self.load_queue_data()
            fast_build_durations = []
            loop_now = time.time()

            for coords in active_planets:
                if coords in busy_building_planets:
                    remaining_busy = busy_building_planets[coords] - loop_now
                    if remaining_busy > 3:
                        empire_active_timers[coords] = int(remaining_busy)
                        continue
                    else:
                        del busy_building_planets[coords]

                current_goals = self.get_plan_for_coords(coords, fresh_data)

                # Pick the FIRST building goal that is NOT yet satisfied on this planet
                building_goal = None
                for g in current_goals:
                    if g.get("type") == "building":
                        g_name = g.get("name", "")
                        target_lvl = g.get("level", 99)
                        curr_lvl = empire.get("building_levels", {}).get(
                            coords, {}).get(g_name.lower(), 0)
                        if curr_lvl < target_lvl:
                            building_goal = g
                            break

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
                        pass

            if fast_build_durations:
                buffer_sec = random.uniform(2.5, 4.2)
                wait_time = max(fast_build_durations) + buffer_sec
                print(
                    f"[*] Parallel batch queued ({fast_build_durations}s). Waiting {round(wait_time, 1)}s for batch completion...")
                time.sleep(wait_time)
            else:
                break

        # 3. Process Ship & Defense orders per Planet
        fresh_data = self.load_queue_data()
        for coords in active_planets:
            goals = self.get_plan_for_coords(coords, fresh_data)
            unit_goals = [g for g in goals if g.get(
                "type") in ["ship", "defense"]]
            for u_goal in unit_goals:
                self._build_units(u_goal, coords=coords)

        return empire_active_timers

    def _resolve_and_upgrade(self, goal: dict, coords: str = "2:30:3", is_research: bool = False) -> tuple[str, int]:
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
            main_coords = queue_data.get("main_planet", "2:30:3")

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

        timer_loc = self.page.locator(".timer-timestamp").first
        if timer_loc is not None and timer_loc.count() > 0 and timer_loc.is_visible():
            target_unix_str = timer_loc.get_attribute("data-time")
            if target_unix_str:
                remaining = max(0, int(target_unix_str) - int(time.time()))

                if 0 < remaining <= 3:
                    settle_sec = remaining + random.uniform(1.0, 1.8)
                    print(
                        f"[*] [{coords}] {endpoint.capitalize()} queue has only {remaining}s left. Settling {round(settle_sec, 1)}s for completion...")
                    time.sleep(settle_sec)
                    self.page.reload()
                    self.page.wait_for_load_state("networkidle")
                    timer_loc = self.page.locator(".timer-timestamp").first
                    target_unix_str = timer_loc.get_attribute(
                        "data-time") if (timer_loc is not None and timer_loc.count() > 0 and timer_loc.is_visible()) else None
                    remaining = max(
                        0, int(target_unix_str) - int(time.time())) if target_unix_str else 0

                if remaining > 0:
                    print(
                        f"[-] [{coords}] {endpoint.capitalize()} queue is currently busy ({remaining}s remaining). Skipping upgrade.")
                    return ("BUSY", remaining)

        cards = self.page.locator(".full-w-entry").all()
        item_card = None

        for card in cards:
            card_text = card.inner_text()
            if not card_text:
                continue

            header_text = re.split(
                r"requires|benötigt|prerequisite|duration|dauer|kosten|cost",
                card_text,
                flags=re.IGNORECASE
            )[0]

            header_lines = [l.strip()
                            for l in header_text.split("\n") if l.strip()]
            for line in header_lines:
                if is_name_match(line, goal_name):
                    item_card = card
                    break
            if item_card:
                break

        if item_card is None:
            print(
                f"[-] [{coords}] Item card for '{goal_name}' not found on {endpoint}.")
            return ("UNAVAILABLE", 0)

        card_text = item_card.inner_text()

        header_text = re.split(
            r"requires|benötigt|prerequisite|duration|dauer|kosten|cost",
            card_text,
            flags=re.IGNORECASE
        )[0]

        lvl_match = re.search(r"(?:Level|Stufe)\s*(\d+)",
                              header_text, re.IGNORECASE)
        if not lvl_match:
            first_line = card_text.splitlines()[0] if card_text else ""
            lvl_match = re.search(
                r"(?:Level|Stufe)\s*(\d+)", first_line, re.IGNORECASE)

        current_level = int(lvl_match.group(1)) if lvl_match else 0

        upgrade_btn = item_card.get_by_role("link", name=re.compile(
            r"(Upgrade|Research|Ausbauen|Erforschen)", re.IGNORECASE)).first

        if upgrade_btn is not None and upgrade_btn.count() > 0 and upgrade_btn.is_visible():
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
                current_level = max(current_level, next_level - 1)

        if current_level >= target_level:
            self.remove_completed_goal(
                goal, coords=coords, is_research=is_research)
            return ("COMPLETED", 0)

        if upgrade_btn is not None and upgrade_btn.count() > 0 and upgrade_btn.is_visible():
            dur_match = re.search(
                r"Duration\s*(\d{2}):(\d{2}):(\d{2})", card_text, re.IGNORECASE)
            build_seconds = 0
            if dur_match:
                h, m, s = map(int, dur_match.groups())
                build_seconds = h * 3600 + m * 60 + s

            print(f"[*] [{coords}] Upgrading '{goal_name}' ({current_level} -> {current_level + 1} | Target: {target_level}) | Build Time: {build_seconds}s")

            human_delay(0.35, 0.75)
            upgrade_btn.click()
            self.page.wait_for_load_state("networkidle")

            if current_level + 1 >= target_level:
                self.remove_completed_goal(
                    goal, coords=coords, is_research=is_research)

            return ("UPGRADED", build_seconds)
        else:
            print(
                f"[-] [{coords}] Upgrade button for '{goal_name}' unavailable (insufficient resources or locked).")
            return ("UNAVAILABLE", 0)

    def _build_units(self, goal: dict, coords: str = "2:30:3"):
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
            main_coords = queue_data.get("main_planet", "2:30:3")
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
            card_text = card.inner_text()
            if not card_text:
                continue

            header_text = re.split(
                r"requires|benötigt|prerequisite|duration|dauer|kosten|cost",
                card_text,
                flags=re.IGNORECASE
            )[0]

            header_lines = [l.strip()
                            for l in header_text.split("\n") if l.strip()]
            for line in header_lines:
                if is_name_match(line, goal_name):
                    target_card = card
                    break
            if target_card:
                break

        if not target_card:
            print(
                f"[Planner Unit] [{coords}] Card for '{goal_name}' not found on page.")
            return

        input_box = target_card.locator(
            "input[type='number'], input[type='text']").first
        global_build_btn = self.page.locator(
            "#add_combat_units_to_queue_send, button[type='submit']").first

        if input_box is None or not input_box.is_visible() or global_build_btn is None or not global_build_btn.is_visible():
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

        add_ship_queue_entry(
            coords, goal_name, build_quantity, SHIP_ORIGIN_USER)
        self.update_unit_goal_amount(goal, build_quantity, coords=coords)

    def clone_planet_blueprint(self, source_coords: str, target_coords_list: list[str]) -> dict:
        """
        Takes current building levels from `source_coords` and populates build queues
        of all planets in `target_coords_list` to match the source planet.
        """
        empire = self.telemetry.get_empire_overview(force_refresh=True)
        source_levels = empire.get(
            "building_levels", {}).get(source_coords, {})

        if not source_levels:
            print(
                f"[!] Blueprint Clone: Source planet [{source_coords}] has no building data in empire overview.")
            return {"success": False, "message": f"Source planet [{source_coords}] not found in empire overview."}

        queue_data = self.load_queue_data()
        if "planets" not in queue_data:
            queue_data["planets"] = {}

        report = {}
        display_names = {
            "iron mine": "Iron Mine",
            "lutinum refinery": "Lutinum Refinery",
            "water pump": "Water Pump",
            "solar power plant": "Solar Power Plant",
            "fusion power plant": "Fusion Power Plant",
            "hydrogen drill": "Hydrogen Drill",
            "iron storage": "Iron Storage",
            "lutinum storage": "Lutinum Storage",
            "water storage": "Water Storage",
            "hydrogen tanks": "Hydrogen Tanks",
            "research center": "Research Center",
            "ship factory": "Ship Factory",
            "defense platform": "Defense Platform",
            "trading post": "Trading Post",
        }

        for target in target_coords_list:
            if target == source_coords:
                continue

            target_curr = empire.get("building_levels", {}).get(target, {})
            if target not in queue_data["planets"]:
                queue_data["planets"][target] = []

            existing_goals = queue_data["planets"][target]
            added_goals_count = 0

            for b_key, src_lvl in source_levels.items():
                if src_lvl <= 0:
                    continue
                tgt_lvl = target_curr.get(b_key, 0)
                if tgt_lvl < src_lvl:
                    b_title = display_names.get(b_key, b_key.title())
                    already_queued = any(
                        g.get("type") == "building" and g.get("name", "").lower(
                        ) == b_title.lower() and g.get("level", 0) >= src_lvl
                        for g in existing_goals
                    )
                    if not already_queued:
                        existing_goals.append({
                            "type": "building",
                            "name": b_title,
                            "level": src_lvl
                        })
                        added_goals_count += 1

            report[target] = added_goals_count

        self._save_queue_data(queue_data)
        print(
            f"[+] Blueprint successfully cloned from [{source_coords}] to {target_coords_list}: {report}")
        return {"success": True, "report": report, "source": source_coords}
