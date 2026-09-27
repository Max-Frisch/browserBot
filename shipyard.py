import re
import math
from playwright.sync_api import Page
from config import safe_goto, get_planet_url
from config import add_ship_queue_entry, get_ship_queue_origin, clear_defense_ship_queues
from config import SHIP_ORIGIN_DEFENSE, SHIP_ORIGIN_USER, SHIP_ORIGIN_UNKNOWN
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

    def cancel_all_ship_queues(self, coords: str = "2:30:3") -> bool:
        """
        Cancels all currently queued ships to return resources to planet.
        Handles both browser dialog ('OK' popup on 'DELETE ALL') and fallback checkbox approach.
        """
        safe_goto(self.page, get_planet_url(coords, "ship"))

        delete_all_btn = self.page.locator(
            "#delete_combat_units_from_queue_deleteAll, button:has-text('DELETE ALL'), a:has-text('DELETE ALL')"
        ).first

        if delete_all_btn is not None and delete_all_btn.count() > 0 and delete_all_btn.is_visible():
            print(
                f"[*] [{coords}] Canceling ship queue via 'DELETE ALL' (accepting dialog popup)...")
            self.page.once("dialog", lambda dialog: dialog.accept())
            try:
                delete_all_btn.click()
                self.page.wait_for_load_state("networkidle")
                return True
            except Exception as e:
                print(f"[!] Error during DELETE ALL click: {e}")

        return self.cancel_selected_ship_queues(coords=coords)

    def cancel_selected_ship_queues(self, coords: str = "2:30:3") -> bool:
        """
        Cancels queued ship orders by selecting their checkboxes and clicking 'DELETE SELECTED'.
        """
        safe_goto(self.page, get_planet_url(coords, "ship"))
        checkboxes = self.page.locator(
            "input[type='checkbox'][name*='delete']").all()
        if not checkboxes:
            checkboxes = self.page.locator(
                ".current-order-list input[type='checkbox'], table input[type='checkbox']").all()

        if checkboxes:
            print(
                f"[*] [{coords}] Selecting {len(checkboxes)} queue item(s) to cancel...")
            for cb in checkboxes:
                try:
                    if not cb.is_checked():
                        cb.check()
                except Exception:
                    pass

            del_selected_btn = self.page.locator(
                "#delete_combat_units_from_queue_deleteSelected, button:has-text('DELETE SELECTED'), a:has-text('DELETE SELECTED')"
            ).first

            if del_selected_btn is not None and del_selected_btn.count() > 0 and del_selected_btn.is_visible():
                del_selected_btn.click()
                self.page.wait_for_load_state("networkidle")
                print(
                    f"[+] [{coords}] Successfully canceled selected ship queue items!")
                return True

        return False

    def cancel_defense_ship_queues_only(self, coords: str = "2:30:3") -> bool:
        """
        Cancels only defense-originated ship queues while preserving user-queued ships.
        Parses the current ship queue from UI and selectively cancels based on origin tracking.
        """
        safe_goto(self.page, get_planet_url(coords, "ship"))

        queue_rows = self.page.locator(
            ".current-order-list tr, table tbody tr").all()
        if not queue_rows:
            print(f"[*] [{coords}] No ship queue rows found.")
            return False

        items_to_cancel = []
        user_ships_preserved = []

        for row in queue_rows:
            try:
                cb = row.locator("input[type='checkbox']").first
                if cb is None or cb.count() == 0 or not cb.is_visible():
                    continue

                row_text = row.inner_text()
                lines = [line.strip()
                         for line in row_text.split("\n") if line.strip()]
                if not lines:
                    continue

                raw_name = lines[0]
                ship_name = re.sub(
                    r"(?i)\s*\(?(?:level|stufe)?\s*\d+\)?.*$", "", raw_name).strip()

                origin = get_ship_queue_origin(coords, ship_name)
                if origin == SHIP_ORIGIN_DEFENSE:
                    items_to_cancel.append((cb, ship_name))
                elif origin == SHIP_ORIGIN_USER:
                    user_ships_preserved.append(ship_name)
            except Exception:
                continue

        if not items_to_cancel:
            print(
                f"[+] [{coords}] No defense-originated ships to cancel. User ships preserved: {user_ships_preserved}")
            return True

        # Check checkboxes for defense-originated ships
        for cb, s_name in items_to_cancel:
            try:
                if not cb.is_checked():
                    cb.check()
            except Exception:
                continue

        del_selected_btn = self.page.locator(
            "#delete_combat_units_from_queue_deleteSelected, button:has-text('DELETE SELECTED'), a:has-text('DELETE SELECTED')"
        ).first

        if del_selected_btn is not None and del_selected_btn.count() > 0 and del_selected_btn.is_visible():
            del_selected_btn.click()
            self.page.wait_for_load_state("networkidle")
            print(
                f"[+] [{coords}] Cancelled {len(items_to_cancel)} defense ship(s). Preserved user ships: {user_ships_preserved}")

            clear_defense_ship_queues(coords)
            return True

        return False

    def parse_ship_catalog(self, coords: str = "2:30:3") -> dict[str, dict]:
        """
        Parses live ship specifications, resource costs, build durations, 
        and maximum buildable quantities directly from the /ship page.
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

            dur_match = re.search(
                r"Duration\s*(\d{2}):(\d{2}):(\d{2})", text, re.IGNORECASE)
            build_seconds = 0
            if dur_match:
                h, m, s = map(int, dur_match.groups())
                build_seconds = h * 3600 + m * 60 + s

            max_match = re.search(r"max\.?\s*(\d+)", text, re.IGNORECASE)
            max_affordable = int(max_match.group(1)) if max_match else 0

            costs = {}
            for res_name in ["iron", "lutinum", "water", "hydrogen"]:
                res_match = re.search(
                    rf"{res_name}[:\s]*([\d\.,]+)", text, re.IGNORECASE
                )
                if res_match:
                    clean_val = int(re.sub(r"[^\d]", "", res_match.group(1)))
                    costs[res_name] = clean_val

            input_box = card.locator(
                "input[type='number'], input[type='text']").first
            input_id = input_box.get_attribute("id") if (
                input_box is not None and input_box.count() > 0) else None

            catalog[ship_name.lower()] = {
                "name": ship_name,
                "input_id": input_id,
                "build_seconds": build_seconds,
                "max_affordable": max_affordable,
                "costs": costs,
            }

        return catalog

    def protect_and_recycle_resources(self, coords: str = "2:30:3", emergency: bool = False, hostile_eta: int = 0) -> int:
        """
        Dynamically safeguards exposed plunderable resources on ANY planet.
        - Emergency=True: Bunkers liquid resources if hostile fleet is incoming.
        - Peacetime: Does NOT lock up shipyards.
        """
        is_busy, remaining_sec = self.telemetry.get_queue_status(
            "ship", coords=coords)

        if is_busy:
            if not emergency:
                print(
                    f"[+] [{coords}] Threat cleared / peace restored. Canceling defense-originated ships only to refund 100% resources...")
                self.cancel_defense_ship_queues_only(coords=coords)
                return 0
            elif remaining_sec <= 90:
                print(
                    f"[*] [{coords}] Shipyard decoy unit near completion ({remaining_sec}s remaining)! Recycling defense ships before it finishes...")
                self.cancel_defense_ship_queues_only(coords=coords)
                is_busy = False

        exposed_data = self.telemetry.calculate_exposed_resources(
            coords=coords)
        total_exposed = sum(exposed_data.get(r, 0)
                            for r in ["iron", "lutinum", "hydrogen"])

        if emergency and not is_busy and total_exposed > 1000:
            print(
                f"[EMERGENCY BUNKER GUARD] [{coords}] Hostile attack incoming (ETA: {hostile_eta}s | Plunderable: {int(total_exposed)}). Sheltering resources...")
            catalog = self.parse_ship_catalog(coords=coords)
            if not catalog:
                return 0

            buildable_ships = [
                ship for ship in catalog.values()
                if ship.get("max_affordable", 0) > 0 and ship.get("input_id")
            ]

            if not buildable_ships:
                print(
                    f"[*] [{coords}] No ships affordable or ship factory inactive. Cannot hide resources in shipyard.")
                return 0

            buildable_ships.sort(key=lambda s: s.get(
                "build_seconds", 0), reverse=True)

            anchor_ship = buildable_ships[0]
            anchor_name = anchor_ship["name"]
            anchor_input_id = anchor_ship["input_id"]
            anchor_max = anchor_ship["max_affordable"]
            anchor_duration = anchor_ship.get("build_seconds", 0)

            qty_to_queue = anchor_max
            print(
                f"[+] [{coords}] Bunkering excess resources into {qty_to_queue}x '{anchor_name}' ({anchor_duration}s per unit)...")

            input_loc = self.page.locator(f"#{anchor_input_id}").first
            global_build_btn = self.page.locator(
                "#add_combat_units_to_queue_send, button[type='submit']").first

            if (input_loc is not None and input_loc.count() > 0 and input_loc.is_visible() and
                    global_build_btn is not None and global_build_btn.count() > 0 and global_build_btn.is_visible()):
                input_loc.fill(str(qty_to_queue))
                global_build_btn.click()
                self.page.wait_for_load_state("networkidle")
                print(
                    f"[+] [{coords}] Successfully sheltered resources in '{anchor_name}' shipyard queue!")

                add_ship_queue_entry(coords, anchor_name,
                                     qty_to_queue, SHIP_ORIGIN_DEFENSE)
                return max(15, anchor_duration - 90)

        if is_busy and remaining_sec > 90:
            return max(15, remaining_sec - 90)

        return 0
