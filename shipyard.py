import re
import math
from playwright.sync_api import Page
from config import safe_goto, get_planet_url
from telemetry import TelemetryManager

# Fallback base costs for rapid calculation
UNIT_COSTS = {
    "schakal": {"iron": 250, "hydrogen": 75},
    "spySatellite": {"iron": 100, "lutinum": 100}
}


class ShipyardManager:
    def __init__(self, page: Page, telemetry: TelemetryManager):
        self.page = page
        self.telemetry = telemetry

    def cancel_all_ship_queues(self, coords: str = "3:7:1"):
        """Cancels all currently queued ships to return resources to planet."""
        safe_goto(self.page, get_planet_url(coords, "ship"))
        delete_all_btn = self.page.locator(
            "#delete_combat_units_from_queue_deleteAll")
        if delete_all_btn.count() > 0 and delete_all_btn.is_visible():
            print(
                f"[*] [{coords}] Canceling ship queue to recover liquid resources...")
            delete_all_btn.click()
            self.page.wait_for_load_state("networkidle")

    def parse_ship_catalog(self, coords: str = "3:7:1") -> dict[str, dict]:
        """
        Parses live ship specifications, resource costs, build durations, 
        and maximum buildable quantities directly from the /ship page.
        Returns a dict keyed by ship name / identifier.
        """
        safe_goto(self.page, get_planet_url(coords, "ship"))
        catalog = {}
        cards = self.page.locator(".full-w-entry").all()

        for card in cards:
            text = card.inner_text()
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            if not lines:
                continue

            ship_name = lines[0]

            # Parse Build Duration
            dur_match = re.search(r"Duration\s*(\d{2}):(\d{2}):(\d{2})", text, re.IGNORECASE)
            build_seconds = 0
            if dur_match:
                h, m, s = map(int, dur_match.groups())
                build_seconds = h * 3600 + m * 60 + s

            # Parse Max Affordable
            max_match = re.search(r"max\.?\s*(\d+)", text, re.IGNORECASE)
            max_affordable = int(max_match.group(1)) if max_match else 0

            # Parse Resource Costs (e.g. Iron, Lutinum, Water, Hydrogen)
            costs = {}
            for res_name in ["iron", "lutinum", "water", "hydrogen"]:
                res_match = re.search(
                    rf"{res_name}[:\s]*([\d\.,]+)", text, re.IGNORECASE
                )
                if res_match:
                    clean_val = int(re.sub(r"[^\d]", "", res_match.group(1)))
                    costs[res_name] = clean_val

            # Detect input locator selector
            input_box = card.locator("input[type='number'], input[type='text']").first
            input_id = input_box.get_attribute("id") if input_box.count() > 0 else None

            catalog[ship_name.lower()] = {
                "name": ship_name,
                "input_id": input_id,
                "build_seconds": build_seconds,
                "max_affordable": max_affordable,
                "costs": costs,
            }

        return catalog

    def protect_and_recycle_resources(self, exposed_data: dict, coords: str = "3:7:1"):
        """
        Safeguards exposed plunderable resources by queuing units before attack/logout,
        and recycles them before completion to retain liquid resources.
        """
        is_busy, remaining_sec = self.telemetry.get_queue_status(
            "ship", coords=coords)

        if is_busy and remaining_sec <= 30:
            print(
                f"[*] [{coords}] Ship queue near completion! Recycling queue...")
            self.cancel_all_ship_queues(coords=coords)
            self.page.reload()
            exposed_data = self.telemetry.calculate_exposed_resources(
                coords=coords)

        iron_exposed = exposed_data.get("iron", 0)
        if not is_busy and iron_exposed > 500:
            # First attempt dynamic catalog check or fallback to standard unit
            unit_cost = UNIT_COSTS.get("schakal", {}).get("iron", 250)
            needed_quantity = math.ceil(iron_exposed / unit_cost)

            print(
                f"[*] [{coords}] Plunder Risk! ({iron_exposed} Iron exposed). Queueing {needed_quantity}x Schakal...")
            safe_goto(self.page, get_planet_url(coords, "ship"))

            input_loc = self.page.locator(
                "#add_combat_units_to_queue_combatUnits_schakal")
            global_build_btn = self.page.locator(
                "#add_combat_units_to_queue_send, button[type='submit']").first

            if input_loc.count() > 0 and input_loc.is_visible() and global_build_btn.is_visible():
                input_loc.fill(str(needed_quantity))
                global_build_btn.click()
                print(
                    f"[+] [{coords}] Successfully deposited ~{needed_quantity * unit_cost} Iron into ship queue!")
