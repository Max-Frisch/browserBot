import re
import time
import json
import math
from typing import Dict, List, Optional, Tuple
from playwright.sync_api import Page

from config import (
    BASE_URL,
    safe_goto,
    get_planet_url,
    human_delay,
    BUILD_QUEUE_FILE,
    FLEET_EVACUATION_MIN_SHIPS,
    FLEET_EVACUATION_SAFETY_BUFFER,
    FLEET_RETURN_BUFFER,
    FLEET_PROTECTION_DRY_RUN,
)
from telemetry import TelemetryManager


class FleetManager:
    """
    Manages fleet operations including evacuation, station movement, and return logistics.
    Integrates with defense system for automatic fleet protection during attacks.
    """

    def __init__(self, page: Page, telemetry: TelemetryManager):
        self.page = page
        self.telemetry = telemetry

        # Track evacuation state
        self.evacuation_file = "fleet_evacuation_state.json"
        self.evacuation_state = self._load_evacuation_state()
        
        # Dry-run mode for safe testing
        self.dry_run = FLEET_PROTECTION_DRY_RUN
        if self.dry_run:
            print("[Fleet Manager] DRY-RUN MODE ENABLED - No actual fleet movements will be executed")

    def _load_evacuation_state(self) -> dict:
        """Load evacuation tracking state from JSON file."""
        default_state = {
            "active_evacuations": {},  # {planet_coords: {destination, departure_time, expected_return}}
            "last_updated": 0
        }
        
        try:
            with open(self.evacuation_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return default_state
    
    def get_evacuation_state(self) -> dict:
        """Public getter for evacuation state"""
        return self.evacuation_state

    def _save_evacuation_state(self):
        """Save evacuation tracking state to JSON file."""
        self.evacuation_state["last_updated"] = int(time.time())
        try:
            with open(self.evacuation_file, "w", encoding="utf-8") as f:
                json.dump(self.evacuation_state, f, indent=2)
        except Exception as e:
            print(f"[!] Error saving evacuation state: {e}")

    def parse_stationed_ships(self, coords: str = "2:30:3") -> Dict[str, int]:
        """
        Parses stationed ships from the fleet/own page.
        Returns dict of {ship_type: count} for all available ships.
        """
        safe_goto(self.page, get_planet_url(coords, "fleet/own"))
        
        ships = {}
        
        # Parse ship counts from data-fleet-target="shipCount{shipType}" spans
        ship_count_spans = self.page.locator("span[data-fleet-target^='shipCount']").all()
        
        for span in ship_count_spans:
            try:
                target_attr = span.get_attribute("data-fleet-target")
                if target_attr and target_attr.startswith("shipCount"):
                    ship_type = target_attr.replace("shipCount", "")
                    count_text = span.inner_text().strip()
                    count = int(re.sub(r"[^\d]", "", count_text)) if count_text else 0
                    
                    if count > 0:
                        ships[ship_type] = count
            except Exception:
                continue
        
        return ships

    def get_available_planets(self) -> List[str]:
        """
        Gets list of all player's planets from the fleet target dropdown.
        Returns list of coordinate strings like ["2:30:3", "2:28:6", ...]
        """
        safe_goto(self.page, f"{BASE_URL}/app/2:30:3/fleet/own")
        
        planets = []
        
        # Parse from target list dropdown
        target_select = self.page.locator("select[data-action='fleet#targetList']").first
        if target_select.count() > 0:
            options = target_select.locator("option").all()
            for option in options:
                value = option.get_attribute("value")
                if value and re.match(r"^\d+:\d+:\d+$", value):
                    planets.append(value)
        
        # Fallback: parse from planet dropdown in navigation
        if not planets:
            planet_select = self.page.locator("#switch-by-coordinate").first
            if planet_select.count() > 0:
                options = planet_select.locator("option").all()
                for option in options:
                    value = option.get_attribute("value")
                    if value:
                        # Extract coords from URL like "/app/2:30:3/fleet/own"
                        match = re.search(r"(\d+:\d+:\d+)", value)
                        if match:
                            planets.append(match.group(1))
        
        return planets

    def calculate_distance(self, coords1: str, coords2: str) -> float:
        """
        Calculates approximate distance between two coordinates.
        Uses simplified Euclidean distance for galaxy coordinate system.
        Format: "galaxy:system:planet"
        """
        try:
            g1, s1, p1 = map(int, coords1.split(":"))
            g2, s2, p2 = map(int, coords2.split(":"))
            
            # Weight galaxy distance more heavily than system/planet
            galaxy_weight = 1000
            system_weight = 10
            planet_weight = 1
            
            distance = math.sqrt(
                ((g2 - g1) * galaxy_weight) ** 2 +
                ((s2 - s1) * system_weight) ** 2 +
                ((p2 - p1) * planet_weight) ** 2
            )
            return distance
        except Exception:
            return float('inf')

    def find_safe_destination(
        self, 
        source_coords: str, 
        under_attack_planets: List[str],
        min_safety_buffer_seconds: int = None
    ) -> Optional[Tuple[str, float]]:
        """
        Finds the closest safe planet for fleet evacuation.
        Returns (destination_coords, distance) or None if no safe destination found.
        
        Args:
            source_coords: Planet under attack
            under_attack_planets: List of planets currently under attack
            min_safety_buffer_seconds: Minimum buffer after attack clears (uses config default if None)
        """
        if min_safety_buffer_seconds is None:
            min_safety_buffer_seconds = FLEET_EVACUATION_SAFETY_BUFFER
            
        available_planets = self.get_available_planets()
        
        if not available_planets:
            print("[!] No available planets for evacuation destination.")
            return None
        
        # Filter out source planet and planets under attack
        safe_planets = [
            p for p in available_planets 
            if p != source_coords and p not in under_attack_planets
        ]
        
        if not safe_planets:
            print("[!] No safe planets available (all planets under attack or only source planet exists).")
            return None
        
        # Find closest safe planet
        closest_planet = None
        min_distance = float('inf')
        
        for planet in safe_planets:
            distance = self.calculate_distance(source_coords, planet)
            if distance < min_distance:
                min_distance = distance
                closest_planet = planet
        
        print(f"[Fleet Evacuation] Safe destination found: [{closest_planet}] (distance: {min_distance:.1f})")
        return closest_planet, min_distance

    def send_fleet(
        self,
        source_coords: str,
        target_coords: str,
        ships: Dict[str, int],
        mission: str = "station",
        speed_percent: int = 100,
        resources: Optional[Dict[str, int]] = None
    ) -> bool:
        """
        Sends a fleet with specified ships, mission, and speed.
        
        Args:
            source_coords: Source planet coordinates
            target_coords: Target planet coordinates
            ships: Dict of {ship_type: quantity} to send
            mission: Mission type ("station", "transport", "colonisation")
            speed_percent: Speed percentage (10-100)
            resources: Optional dict of resources to transport
        
        Returns:
            True if fleet sent successfully, False otherwise
        """
        # Dry-run mode: simulate fleet send without actual execution
        if self.dry_run:
            total_ships = sum(ships.values())
            print(f"[DRY-RUN 🛡️] SIMULATED FLEET SEND: {total_ships} ships from [{source_coords}] → [{target_coords}]")
            print(f"[DRY-RUN 🛡️] Details: Mission={mission}, Speed={speed_percent}%, Ships={ships}")
            if resources:
                print(f"[DRY-RUN 🛡️] Resources: {resources}")
            print(f"[DRY-RUN 🛡️] NO ACTUAL GAME REQUESTS MADE - SAFE SIMULATION ONLY")
            return True
        
        safe_goto(self.page, get_planet_url(source_coords, "fleet/own"))
        
        # Parse target coordinates
        try:
            target_galaxy, target_system, target_planet = map(int, target_coords.split(":"))
        except Exception:
            print(f"[!] Invalid target coordinates: {target_coords}")
            return False
        
        # Select ships
        for ship_type, quantity in ships.items():
            if quantity <= 0:
                continue
            
            ship_input = self.page.locator(f"input[name='ships[{ship_type}]']").first
            if ship_input.count() > 0:
                ship_input.fill(str(quantity))
                human_delay(0.1, 0.2)
        
        # Set target coordinates
        galaxy_input = self.page.locator("input[name='toCoordinate[galaxy]']").first
        system_input = self.page.locator("input[name='toCoordinate[system]']").first
        planet_input = self.page.locator("input[name='toCoordinate[planet]']").first
        
        if galaxy_input.count() > 0 and system_input.count() > 0 and planet_input.count() > 0:
            galaxy_input.fill(str(target_galaxy))
            system_input.fill(str(target_system))
            planet_input.fill(str(target_planet))
            human_delay(0.2, 0.3)
        
        # Set mission type
        mission_select = self.page.locator("select[name='mission']").first
        if mission_select.count() > 0:
            mission_select.select_option(mission)
            human_delay(0.1, 0.2)
        
        # Set speed
        speed_select = self.page.locator("select[name='preferredSpeed']").first
        if speed_select.count() > 0:
            speed_select.select_option(str(speed_percent))
            human_delay(0.1, 0.2)
        
        # Set resources if provided (for transport missions)
        if resources and mission == "transport":
            for resource_type, quantity in resources.items():
                resource_input = self.page.locator(f"input[name='resources[{resource_type}]']").first
                if resource_input.count() > 0 and quantity > 0:
                    resource_input.fill(str(quantity))
                    human_delay(0.1, 0.2)
        
        # Submit form
        submit_button = self.page.locator("button[data-action='fleet#send']").first
        if submit_button.count() > 0 and submit_button.is_visible():
            print(f"[Fleet] Sending fleet from [{source_coords}] to [{target_coords}]...")
            submit_button.click()
            self.page.wait_for_load_state("networkidle")
            
            # Check for errors
            error_elements = self.page.locator(".alert-danger, .error").all()
            if error_elements:
                for error in error_elements:
                    if error.is_visible():
                        error_text = error.inner_text()
                        print(f"[!] Fleet send error: {error_text}")
                        return False
            
            print(f"[+] Fleet sent successfully!")
            return True
        else:
            print("[!] Send button not found or not visible.")
            return False

    def evacuate_fleet(
        self,
        source_coords: str,
        under_attack_planets: List[str],
        attack_eta_seconds: int = 0
    ) -> Optional[int]:
        """
        Evacuates all ships from a planet under attack to the nearest safe planet.
        
        Args:
            source_coords: Planet under attack
            under_attack_planets: List of all planets currently under attack
            attack_eta_seconds: Time until attack arrives (for timing calculations)
        
        Returns:
            Travel time in seconds, or None if evacuation failed
        """
        print(f"[FLEET EVACUATION] Emergency evacuation initiated for [{source_coords}]")
        
        # Get stationed ships
        ships = self.parse_stationed_ships(source_coords)
        
        if not ships:
            print(f"[+] [{source_coords}] No ships to evacuate.")
            return None
        
        total_ships = sum(ships.values())
        
        # Check minimum ship threshold
        if total_ships < FLEET_EVACUATION_MIN_SHIPS:
            print(f"[+] [{source_coords}] Only {total_ships} ships (below threshold of {FLEET_EVACUATION_MIN_SHIPS}). Skipping evacuation.")
            return None
        
        print(f"[*] Found {total_ships} ships to evacuate: {ships}")
        
        # Find safe destination
        destination_result = self.find_safe_destination(source_coords, under_attack_planets)
        if not destination_result:
            print("[!] No safe destination found for evacuation.")
            return None
        
        destination_coords, distance = destination_result
        
        # Calculate appropriate speed to ensure arrival after attack
        # Base travel time estimation (rough approximation)
        base_travel_time = int(distance * 60)  # Rough estimate: 1 minute per distance unit
        
        # Ensure fleet arrives at least configured safety buffer after attack
        safety_buffer = FLEET_EVACUATION_SAFETY_BUFFER
        if attack_eta_seconds > 0:
            required_travel_time = attack_eta_seconds + safety_buffer
        else:
            required_travel_time = base_travel_time + safety_buffer
        
        # Calculate speed percentage
        speed_percent = 100
        if required_travel_time > base_travel_time:
            speed_percent = max(10, min(100, int((base_travel_time / required_travel_time) * 100)))
        
        print(f"[*] Travel time: ~{base_travel_time}s | Required: {required_travel_time}s | Speed: {speed_percent}%")
        
        # Send fleet with station mission (one-way)
        success = self.send_fleet(
            source_coords=source_coords,
            target_coords=destination_coords,
            ships=ships,
            mission="station",
            speed_percent=speed_percent
        )
        
        if success:
            # Record evacuation state (skip in dry-run mode)
            if not self.dry_run:
                actual_travel_time = int(base_travel_time * (100 / speed_percent))
                self.evacuation_state["active_evacuations"][source_coords] = {
                    "destination": destination_coords,
                    "departure_time": int(time.time()),
                    "ships": ships,
                    "expected_arrival": int(time.time()) + actual_travel_time
                }
                self._save_evacuation_state()
            else:
                # In dry-run mode, simulate state tracking
                actual_travel_time = int(base_travel_time * (100 / speed_percent))
                print(f"[DRY-RUN 🛡️] Would record evacuation state for [{source_coords}] → [{destination_coords}]")
                print(f"[DRY-RUN 🛡️] Departure: {int(time.time())}, Arrival: {int(time.time()) + actual_travel_time}")
            
            print(f"[+] Fleet evacuation completed. Ships safe at [{destination_coords}]")
            return actual_travel_time
        
        return None

    def check_evacuation_returns(self, under_attack_planets: List[str]) -> List[str]:
        """
        Checks if any evacuated fleets can be returned to their home planets.
        Returns list of planets that had fleets returned.
        """
        # Skip return logic in dry-run mode
        if self.dry_run:
            print("[DRY-RUN 🛡️] Skipping fleet return logic (dry-run mode)")
            return []
        
        returned_planets = []
        current_time = int(time.time())
        
        for source_coords, evacuation_data in list(self.evacuation_state["active_evacuations"].items()):
            # Don't return if source is still under attack
            if source_coords in under_attack_planets:
                continue
            
            destination = evacuation_data["destination"]
            departure_time = evacuation_data["departure_time"]
            expected_arrival = evacuation_data["expected_arrival"]
            
            # Wait at least configured return buffer after arrival before considering return
            return_buffer = FLEET_RETURN_BUFFER
            
            if current_time > expected_arrival + return_buffer:
                print(f"[Fleet Return] Considering return of fleet to [{source_coords}] from [{destination}]")
                
                # Check if destination is safe (not under attack)
                if destination not in under_attack_planets:
                    # Parse ships at destination and send them back
                    ships_at_destination = self.parse_stationed_ships(destination)
                    
                    if ships_at_destination:
                        # Send fleet back with transport mission (round trip)
                        success = self.send_fleet(
                            source_coords=destination,
                            target_coords=source_coords,
                            ships=ships_at_destination,
                            mission="transport",
                            speed_percent=100
                        )
                        
                        if success:
                            print(f"[+] Fleet returned to [{source_coords}]")
                            returned_planets.append(source_coords)
                            del self.evacuation_state["active_evacuations"][source_coords]
                            self._save_evacuation_state()
        
        return returned_planets

    def get_evacuation_status(self) -> dict:
        """Returns current evacuation status for monitoring."""
        return {
            "active_evacuations": self.evacuation_state["active_evacuations"],
            "last_updated": self.evacuation_state["last_updated"]
        }