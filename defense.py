import time
from playwright.sync_api import Page
from config import safe_goto, get_planet_url


class DefenseManager:
    def __init__(self, page: Page):
        self.page = page

    def check_incoming_fleets(self, coords: str = "3:7:1") -> list[dict]:
        """Parses the Overview dashboard for incoming enemy fleet movements."""
        target_url = get_planet_url(coords, "planet")

        if "planet" not in self.page.url:
            safe_goto(self.page, target_url)

        incoming_events = []
        fleet_rows = self.page.locator(".fleet-table-tr").all()

        for row in fleet_rows:
            mission_loc = row.locator(".fleet-mission")
            timer_loc = row.locator(".timer-timestamp")

            if mission_loc.count() > 0 and timer_loc.count() > 0:
                mission_type = mission_loc.inner_text().strip()
                target_unix_str = timer_loc.get_attribute("data-time")

                if target_unix_str:
                    remaining_sec = max(
                        0, int(target_unix_str) - int(time.time()))
                    incoming_events.append({
                        "mission": mission_type,
                        "remaining_seconds": remaining_sec,
                        "arrival_time": timer_loc.get_attribute("data-bs-original-title") or ""
                    })

        if incoming_events:
            print(
                f"[⚠️ FLEET ALERT] {len(incoming_events)} active movement(s):")
            for ev in incoming_events:
                print(
                    f" └─ {ev['mission']} arriving in {ev['remaining_seconds']}s ({round(ev['remaining_seconds']/60, 1)}m)")
        else:
            print("[Fleet Check] No hostile fleet movements detected.")

        return incoming_events
