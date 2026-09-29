import time
from playwright.sync_api import Page
from config import safe_goto, get_planet_url

HOSTILE_MISSION_KEYWORDS = ["attack", "angriff",
                            "plunder", "raid", "spionage", "spy"]


class DefenseManager:
    def __init__(self, page: Page):
        self.page = page

    def is_hostile_mission(self, mission_name: str) -> bool:
        """Determines if a mission string indicates hostile intent."""
        m_lower = mission_name.lower()
        return any(k in m_lower for k in HOSTILE_MISSION_KEYWORDS)

    def quick_sentry_radar(self) -> list[dict]:
        """
        Ultra-fast sentry scan on the current page without navigating.
        Detects if any hostile red fleet banners or table rows are visible in the DOM.
        """
        hostile_events = []
        try:
            fleet_rows = self.page.locator(".fleet-table-tr").all()
            for row in fleet_rows:
                mission_loc = row.locator(".fleet-mission")
                timer_loc = row.locator(".timer-timestamp")
                if mission_loc.count() > 0 and timer_loc.count() > 0:
                    mission_type = mission_loc.inner_text().strip()
                    if self.is_hostile_mission(mission_type):
                        target_unix_str = timer_loc.get_attribute("data-time")
                        rem_sec = max(0, int(target_unix_str) -
                                      int(time.time())) if target_unix_str else 0
                        hostile_events.append({
                            "mission": mission_type,
                            "remaining_seconds": rem_sec,
                            "is_hostile": True
                        })
        except Exception:
            pass
        return hostile_events

    def check_incoming_fleets(self, coords: str = "2:30:3") -> list[dict]:
        """Parses the Overview dashboard for incoming fleet movements."""
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
                    
                    # Check if this is an own fleet (outbound) vs incoming fleet
                    # Own fleets typically have "own-fleet" class in the mission cell
                    row_html = row.inner_html()
                    is_own_fleet = "own-fleet" in row_html.lower()
                    
                    # Only classify as hostile if it's NOT our own fleet AND has hostile mission type
                    is_hostile = not is_own_fleet and self.is_hostile_mission(mission_type)
                    
                    incoming_events.append({
                        "mission": mission_type,
                        "remaining_seconds": remaining_sec,
                        "is_hostile": is_hostile,
                        "is_own_fleet": is_own_fleet,
                        "arrival_time": timer_loc.get_attribute("data-bs-original-title") or ""
                    })

        hostiles = [e for e in incoming_events if e.get("is_hostile")]
        own_fleets = [e for e in incoming_events if e.get("is_own_fleet")]
        
        if hostiles:
            print(
                f"[HOSTILE FLEET ALERT] {len(hostiles)} incoming hostile movement(s):")
            for ev in hostiles:
                print(
                    f" └─ {ev['mission']} arriving in {ev['remaining_seconds']}s ({round(ev['remaining_seconds']/60, 1)}m)")
        elif own_fleets:
            print(
                f"[*] {len(own_fleets)} own fleet movement(s) detected (not hostile).")
        elif incoming_events:
            print(
                f"[*] {len(incoming_events)} friendly/routine fleet movement(s) detected.")
        else:
            print("[Fleet Check] No hostile fleet movements detected.")

        return incoming_events
