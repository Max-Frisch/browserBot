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

    def cancel_all_ship_queues(self, coords: str = "3:7:1") -> bool:
        """
        Cancels all currently queued ships to return resources to planet.
        Handles both browser dialog ('OK' popup on 'DELETE ALL') and the fallback checkbox approach.
        """
        safe_goto(self.page, get_planet_url(coords, "ship"))
        
        # Primary: 'DELETE ALL' with dialog listener
        delete_all_btn = self.page.locator(
            "#delete_combat_units_from_queue_deleteAll, button:has-text('DELETE ALL'), a:has-text('DELETE ALL')"
        ).first
        
        if delete_all_btn.count() > 0 and delete_all_btn.is_visible():
            print(f"[*] [{coords}] Canceling ship queue via 'DELETE ALL' (accepting dialog popup)...")
            # Register one-time dialog handler to auto-accept the confirmation popup ("OK")
            self.page.once("dialog", lambda dialog: dialog.accept())
            try:
                delete_all_btn.click()
                self.page.wait_for_load_state("networkidle")
                return True
            except Exception as e:
                print(f"[⚠️ Error during DELETE ALL click]: {e}")

        # Fallback: Select all position checkboxes and click 'DELETE SELECTED' (no popup)
        return self.cancel_selected_ship_queues(coords=coords)

    def cancel_selected_ship_queues(self, coords: str = "3:7:1") -> bool:
        """
        Cancels queued ship orders by selecting their checkboxes and clicking 'DELETE SELECTED' (no confirmation modal needed).
        """
        safe_goto(self.page, get_planet_url(coords, "ship"))
        checkboxes = self.page.locator("input[type='checkbox'][name*='delete']").all()
        if not checkboxes:
            # Check for any row checkboxes under order list
            checkboxes = self.page.locator(".current-order-list input[type='checkbox'], table input[type='checkbox']").all()

        if checkboxes:
            print(f"[*] [{coords}] Selecting {len(checkboxes)} queue item(s) to cancel...")
            for cb in checkboxes:
                try:
                    if not cb.is_checked():
                        cb.check()
                except Exception:
                    pass

            del_selected_btn = self.page.locator(
                "#delete_combat_units_from_queue_deleteSelected, button:has-text('DELETE SELECTED'), a:has-text('DELETE SELECTED')"
            ).first

            if del_selected_btn.count() > 0 and del_selected_btn.is_visible():
                del_selected_btn.click()
                self.page.wait_for_load_state("networkidle")
                print(f"[+] [{coords}] Successfully canceled selected ship queue items!")
                return True

        return False

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

    def protect_and_recycle_resources(self, coords: str = "3:7:1", emergency: bool = False, min_exposed_threshold: int = 5000):
        """
        Dynamically safeguards exposed plunderable resources on a planet.
        - Checks true unplunderable storage thresholds (from Storage/Tank levels).
        - If exposed resources exist (and emergency=True or unplundered excess exceeds min_exposed_threshold):
          hides liquid resources inside the shipyard queue.
        - CRITICAL RULE: Selects the LONGEST build-time unit first (e.g. Cougar, Falcon, Trader)
          instead of fast units (Jackal/Probe) that could finish during an attack and get destroyed!
        - If queue is within 30 seconds of completing (or after threat passes), cancels the queue to recover 100% resources.
        """
        is_busy, remaining_sec = self.telemetry.get_queue_status("ship", coords=coords)

        # 1. Recycle/Cancel queue before it finishes building so liquid resources return
        if is_busy and remaining_sec <= 45:
            print(f"[*] [{coords}] Shipyard decoy queue near completion ({remaining_sec}s)! Recycling queue...")
            self.cancel_all_ship_queues(coords=coords)
            return

        # 2. Check true unplunderable limit and exposed amounts
        exposed_data = self.telemetry.calculate_exposed_resources(coords=coords)
        total_exposed = sum(exposed_data.get(r, 0) for r in ["iron", "lutinum", "hydrogen"])

        # Only trigger bunker guard if an actual attack is incoming or exposed excess is significant
        if not is_busy and (emergency or total_exposed >= min_exposed_threshold):
            print(f"[*] [{coords}] Bunker Guard Alert! (Total plunderable: {int(total_exposed)} | Emergency={emergency}). Inspecting shipyard catalog...")
            catalog = self.parse_ship_catalog(coords=coords)
            if not catalog:
                return

            # Find all ships that we can actually build (max_affordable > 0 and input_id exists)
            buildable_ships = [
                ship for ship in catalog.values()
                if ship.get("max_affordable", 0) > 0 and ship.get("input_id")
            ]

            if not buildable_ships:
                print(f"[*] [{coords}] No ships affordable or ship factory inactive. Cannot hide resources.")
                return

            # Sort by longest build duration first to maximize safe-bunker time!
            buildable_ships.sort(key=lambda s: s.get("build_seconds", 0), reverse=True)

            # Choose the primary long-duration anchor ship
            anchor_ship = buildable_ships[0]
            anchor_name = anchor_ship["name"]
            anchor_input_id = anchor_ship["input_id"]
            anchor_max = anchor_ship["max_affordable"]
            anchor_duration = anchor_ship.get("build_seconds", 0)

            # Queue at least 1 or up to what covers the exposed pile
            # (Queueing max affordable locks the maximum possible resources)
            qty_to_queue = anchor_max

            print(f"[+] [{coords}] Bunkering excess resources into {qty_to_queue}x '{anchor_name}' (Build time: {anchor_duration}s per unit)...")

            input_loc = self.page.locator(f"#{anchor_input_id}")
            global_build_btn = self.page.locator("#add_combat_units_to_queue_send, button[type='submit']").first

            if input_loc.count() > 0 and input_loc.is_visible() and global_build_btn.is_visible():
                input_loc.fill(str(qty_to_queue))
                global_build_btn.click()
                self.page.wait_for_load_state("networkidle")
                print(f"[+] [{coords}] Successfully sheltered resources in '{anchor_name}' shipyard queue!")
