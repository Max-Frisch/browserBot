import re
import time
from playwright.sync_api import Page
from config import BASE_URL, safe_goto, get_planet_url


class TelemetryManager:
    def __init__(self, page: Page):
        self.page = page

    def get_resources(self) -> dict:
        """Parses exact resource levels from desktop header attributes for current active context."""
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
        """Parses safe (unplunderable) storage limits for a specific planet."""
        target_url = get_planet_url(coords, "resource")
        if target_url not in self.page.url:
            safe_goto(self.page, target_url)

        limits = {"iron": 180000, "lutinum": 126000,
                  "water": 84000, "hydrogen": 84000}
        safe_row = self.page.locator("tr", has_text=re.compile(
            r"cannot be plundered", re.IGNORECASE))

        if safe_row.count() > 0:
            cells = safe_row.locator("td").all()
            if len(cells) >= 5:
                limits = {
                    "iron": self._clean_num(cells[1].inner_text()),
                    "lutinum": self._clean_num(cells[2].inner_text()),
                    "water": self._clean_num(cells[3].inner_text()),
                    "hydrogen": self._clean_num(cells[4].inner_text())
                }
        return limits

    def calculate_exposed_resources(self, coords: str = "3:7:1") -> dict:
        """Calculates plunderable excess resources for a specific planet."""
        current = self.get_resources()
        safe_limits = self.get_storage_limits(coords=coords)
        exposed = {}
        for res in ["iron", "lutinum", "water", "hydrogen"]:
            curr_val = current.get(res, {}).get("current", 0)
            safe_val = safe_limits.get(res, 30000)
            exposed[res] = round(max(0.0, curr_val - safe_val), 2)
        return exposed

    def get_queue_status(self, category: str = "construction", coords: str = "3:7:1") -> tuple[bool, int]:
        """Checks timer for construction, research, or ship queues on a planet."""
        endpoint_map = {
            "construction": "building",
            "research": "research",
            "ship": "ship"
        }
        target_url = get_planet_url(
            coords, endpoint_map.get(category, "building"))
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
        """Parses the Overview dashboard to find all planets currently constructing a building."""
        safe_goto(self.page, get_planet_url(coords, "planet"))
        busy_planets = {}

        order_rows = self.page.locator(
            "tr", has=self.page.locator("a[href*='/planet']")).all()
        for row in order_rows:
            link = row.locator("a[href*='/planet']").first
            if link.count() > 0:
                p_coords = link.inner_text().strip()
                busy_planets[p_coords] = 300

        return busy_planets

    def _clean_num(self, text: str) -> int:
        clean_str = re.sub(r"[^\d]", "", text)
        return int(clean_str) if clean_str else 0
