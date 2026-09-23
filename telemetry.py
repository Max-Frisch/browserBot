import re
import time
import threading
from playwright.sync_api import Page
from config import BASE_URL, safe_goto, get_planet_url, human_delay


class TelemetryManager:
    def __init__(self, page: Page):
        self.page = page
        self._empire_cache: dict | None = None
        self._empire_cache_time: float = 0
        self._cache_ttl: float = 15.0  # seconds
        self._state_lock = threading.Lock()
        self._latest_empire_data: dict = {
            "planets": [],
            "building_queues": {},
            "ship_queues": {},
            "resources": {},
            "production": {},
            "building_levels": {},
            "storage_limits": {},
            "ships": {},
            "defense": {},
            "last_updated": 0
        }

    def get_latest_snapshot(self) -> dict:
        """
        Thread-safe reader for external consumers (e.g. Discord bot thread).
        Never touches Playwright page directly, avoiding greenlet/cross-thread errors.
        """
        with self._state_lock:
            return dict(self._latest_empire_data)

    def _parse_duration(self, text: str) -> int:
        """Converts (hh:mm:ss) or hh:mm:ss into total seconds."""
        m = re.search(r"(\d{2}):(\d{2}):(\d{2})", text)
        if m:
            h, mn, s = map(int, m.groups())
            return h * 3600 + mn * 60 + s
        return 0

    def _clean_num(self, text: str) -> int:
        """Parses German/European formatted numbers (e.g. 26.232 -> 26232)."""
        # Remove parenthetical values
        text = re.sub(r"\(.*?\)", "", text)
        digits = re.sub(r"[^\d]", "", text.strip())
        return int(digits) if digits else 0

    def parse_empire_html(self, html: str) -> dict:
        """Parses complete tabular empire overview from /app/empire HTML source."""
        planets = []
        building_queues = {}
        ship_queues = {}
        resources = {}
        production = {}
        building_levels = {}
        storage_limits = {}
        ships = {}
        defense = {}

        current_section = "overview"

        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.DOTALL | re.IGNORECASE)

        for row in rows:
            th_match = re.search(r"<th[^>]*>(.*?)</th>", row, flags=re.DOTALL | re.IGNORECASE)
            if th_match:
                th_text = re.sub(r"<[^>]+>", "", th_match.group(1)).strip().lower()
                if "empire overview" in th_text:
                    current_section = "overview"
                elif "resource production" in th_text:
                    current_section = "production"
                elif "trading post" in th_text:
                    current_section = "trading_post"
                elif "resources" in th_text:
                    current_section = "resources"
                elif "buildings" in th_text:
                    current_section = "buildings"
                elif "ships" in th_text:
                    current_section = "ships"
                elif "defense" in th_text:
                    current_section = "defense"
                continue

            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.DOTALL | re.IGNORECASE)
            if not cells:
                continue

            label = re.sub(r"<[^>]+>", "", cells[0]).strip()
            label_lower = label.lower()

            # Planet Header Row
            if label_lower == "planet":
                for cell in cells[1:]:
                    clean_coord = re.sub(r"<[^>]+>", "", cell).strip()
                    if re.match(r"^\d+:\d+:\d+$", clean_coord):
                        planets.append(clean_coord)
                continue

            if not planets:
                continue

            # Section: Overview (active construction & ship queues)
            if current_section == "overview":
                if label_lower == "buildings":
                    for idx, cell in enumerate(cells[1:len(planets) + 1]):
                        p = planets[idx]
                        dur = self._parse_duration(cell)
                        if dur > 0:
                            clean_text = re.sub(r"<[^>]+>", "", cell).strip()
                            name_match = re.search(r"([^\(]+?)(?:\s*\(\d{2}:\d{2}:\d{2}\))", clean_text)
                            b_name = name_match.group(1).strip() if name_match else clean_text
                            building_queues[p] = {"name": b_name, "remaining_seconds": dur}
                elif label_lower == "ship factory":
                    for idx, cell in enumerate(cells[1:len(planets) + 1]):
                        p = planets[idx]
                        dur = self._parse_duration(cell)
                        if dur > 0:
                            title_match = re.search(r'title=["\'](.*?)["\']', cell, re.IGNORECASE)
                            detail = title_match.group(1).replace("<br/>", " ") if title_match else ""
                            ship_queues[p] = {"remaining_seconds": dur, "detail": detail}

            # Section: Resources
            elif current_section == "resources":
                if label_lower in ("iron", "lutinum", "water", "hydrogen"):
                    for idx, cell in enumerate(cells[1:len(planets) + 1]):
                        p = planets[idx]
                        val = self._clean_num(re.sub(r"<[^>]+>", "", cell))
                        if p not in resources:
                            resources[p] = {}
                        resources[p][label_lower] = val

            # Section: Production
            elif current_section == "production":
                if label_lower in ("iron", "lutinum", "water", "hydrogen"):
                    for idx, cell in enumerate(cells[1:len(planets) + 1]):
                        p = planets[idx]
                        val = self._clean_num(re.sub(r"<[^>]+>", "", cell))
                        if p not in production:
                            production[p] = {}
                        production[p][label_lower] = val

            # Section: Buildings
            elif current_section == "buildings":
                if label:
                    is_storage = "storage" in label_lower or "tanks" in label_lower
                    for idx, cell in enumerate(cells[1:len(planets) + 1]):
                        p = planets[idx]
                        if p not in building_levels:
                            building_levels[p] = {}
                        lvl = self._clean_num(re.sub(r"\(.*?\)", "", re.sub(r"<[^>]+>", "", cell)))
                        building_levels[p][label_lower] = lvl

                        if is_storage:
                            if p not in storage_limits:
                                storage_limits[p] = {}
                            title_match = re.search(r'title=["\']([\d\.]+)\s+secure["\']', cell, re.IGNORECASE)
                            if title_match:
                                res_type = "iron" if "iron" in label_lower else (
                                    "lutinum" if "lutinum" in label_lower else (
                                        "water" if "water" in label_lower else "hydrogen"
                                    )
                                )
                                storage_limits[p][res_type] = self._clean_num(title_match.group(1))

            # Section: Ships
            elif current_section == "ships":
                if label:
                    for idx, cell in enumerate(cells[1:len(planets) + 1]):
                        p = planets[idx]
                        if p not in ships:
                            ships[p] = {}
                        ships[p][label_lower] = self._clean_num(re.sub(r"<[^>]+>", "", cell))

            # Section: Defense
            elif current_section == "defense":
                if label:
                    for idx, cell in enumerate(cells[1:len(planets) + 1]):
                        p = planets[idx]
                        if p not in defense:
                            defense[p] = {}
                        defense[p][label_lower] = self._clean_num(re.sub(r"<[^>]+>", "", cell))

        return {
            "planets": planets,
            "building_queues": building_queues,
            "ship_queues": ship_queues,
            "resources": resources,
            "production": production,
            "building_levels": building_levels,
            "storage_limits": storage_limits,
            "ships": ships,
            "defense": defense,
        }

    def get_empire_overview(self, force_refresh: bool = False) -> dict:
        """Navigates to /app/empire and parses the comprehensive empire table with caching."""
        now = time.time()
        if not force_refresh and self._empire_cache and (now - self._empire_cache_time) < self._cache_ttl:
            return self._empire_cache

        safe_goto(self.page, f"{BASE_URL}/app/empire")
        html = self.page.content()
        data = self.parse_empire_html(html)

        self._empire_cache = data
        self._empire_cache_time = now

        with self._state_lock:
            self._latest_empire_data = dict(data)
            self._latest_empire_data["last_updated"] = now

        return data

    def get_resources(self, coords: str | None = None) -> dict:
        """Parses resource levels from /app/empire or fallback desktop header."""
        if coords:
            overview = self.get_empire_overview()
            p_res = overview.get("resources", {}).get(coords)
            if p_res:
                return {
                    k: {
                        "current": float(v),
                        "production": float(overview.get("production", {}).get(coords, {}).get(k, 0)),
                        "storage": 0,
                        "fill_pct": 0.0
                    }
                    for k, v in p_res.items()
                }

        # Fallback to desktop header attributes for current active context
        resources = {}
        for key in ["iron", "lutinum", "water", "hydrogen"]:
            loc = self.page.locator(
                f'.header-desktop [data-resource-bar-target="{key}"]').first
            if loc.count() > 0:
                current = float(loc.get_attribute("data-current") or 0)
                production = float(loc.get_attribute("data-production") or 0)
                storage = float(loc.get_attribute("data-storage") or 0)
                resources[key] = {
                    "current": round(current, 2),
                    "production": round(production, 2),
                    "storage": int(storage),
                    "fill_pct": round((current / storage * 100) if storage > 0 else 0, 2)
                }
        return resources

    def get_storage_limits(self, coords: str = "3:7:1") -> dict:
        """Returns safe (unplunderable) storage limits for a specific planet."""
        overview = self.get_empire_overview()
        planet_limits = overview.get("storage_limits", {}).get(coords, {})

        # Default safe limits if not set
        defaults = {"iron": 84000, "lutinum": 84000, "water": 30000, "hydrogen": 30000}
        return {k: planet_limits.get(k, defaults[k]) for k in defaults}

    def calculate_exposed_resources(self, coords: str = "3:7:1") -> dict:
        """Calculates plunderable excess resources for a specific planet."""
        current = self.get_resources(coords=coords)
        safe_limits = self.get_storage_limits(coords=coords)
        exposed = {}
        for res in ["iron", "lutinum", "water", "hydrogen"]:
            curr_val = current.get(res, {}).get("current", 0)
            safe_val = safe_limits.get(res, 30000)
            exposed[res] = round(max(0.0, curr_val - safe_val), 2)
        return exposed

    def get_queue_status(self, category: str = "construction", coords: str = "3:7:1") -> tuple[bool, int]:
        """Checks timer for construction, research, or ship queues on a planet."""
        if category == "construction":
            overview = self.get_empire_overview()
            b_info = overview.get("building_queues", {}).get(coords)
            if b_info and b_info.get("remaining_seconds", 0) > 0:
                return True, b_info["remaining_seconds"]
            return False, 0
        elif category == "ship":
            overview = self.get_empire_overview()
            s_info = overview.get("ship_queues", {}).get(coords)
            if s_info and s_info.get("remaining_seconds", 0) > 0:
                return True, s_info["remaining_seconds"]
            return False, 0

        # Research must be checked on the research endpoint on main planet
        endpoint = "research"
        target_url = get_planet_url(coords, endpoint)
        if target_url not in self.page.url:
            safe_goto(self.page, target_url)

        timer_loc = self.page.locator(".timer-timestamp").first
        if timer_loc.count() > 0 and timer_loc.is_visible():
            target_unix_str = timer_loc.get_attribute("data-time")
            if target_unix_str:
                remaining = max(0, int(target_unix_str) - int(time.time()))
                return True, remaining
        return False, 0

    def get_busy_building_planets(self, coords: str = "3:7:1") -> dict[str, int]:
        """Retrieves all planets currently constructing a building with exact remaining seconds from /app/empire."""
        overview = self.get_empire_overview()
        busy = {}
        for p, q_info in overview.get("building_queues", {}).items():
            rem = q_info.get("remaining_seconds", 0)
            if rem > 0:
                busy[p] = rem
        return busy
