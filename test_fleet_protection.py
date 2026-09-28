#!/usr/bin/env python3
"""
Fleet Protection Testing Script

This script helps test the fleet protection system by:
1. Monitoring for incoming fleets (hostile detection)
2. Optionally triggering NPC espionage response for testing
3. Capturing detailed fleet information for validation
4. Running in safe dry-run mode by default

Usage:
    python test_fleet_protection.py --monitor                    # Just monitor for fleets
    python test_fleet_protection.py --trigger-espionage --target 2:30:4  # Send spy probes to trigger NPC response
    python test_fleet_protection.py --trigger-espionage --target 2:30:4 2:30:9  # Multiple targets
    python test_fleet_protection.py --help                       # See all options
"""

import os
import sys
import time
import json
import argparse
from playwright.sync_api import sync_playwright, Error as PlaywrightError

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    BASE_URL,
    AUTH_FILE,
    EMAIL,
    PASSWORD,
    HEADLESS,
    USER_AGENT,
    VIEWPORT,
    DEVICE_SCALE_FACTOR,
    LOCALE,
    TIMEZONE_ID,
    CHROMIUM_ARGS,
    STEALTH_SCRIPT,
    setup_route_filtering,
    safe_goto,
    get_planet_url,
    human_delay,
    human_click,
    FLEET_PROTECTION_DRY_RUN,
)
from defense import DefenseManager


def login_if_needed(page, context):
    """Checks session status and executes login if unauthenticated."""
    safe_goto(page, f"{BASE_URL}/login")

    back_to_game = page.get_by_role("link", name="BACK TO GAME")
    if back_to_game.count() > 0 and back_to_game.is_visible():
        human_delay(0.3, 0.6)
        back_to_game.click()
        return

    email_field = page.get_by_role("textbox", name="Email address")
    if email_field.count() > 0 and email_field.is_visible():
        print("[*] Performing automated authentication...")
        human_delay(0.4, 0.8)
        email_field.fill(EMAIL)
        human_delay(0.2, 0.5)
        page.get_by_role("textbox", name="Password").fill(PASSWORD)
        human_delay(0.3, 0.6)
        page.get_by_role("button", name="Log in").click()
        page.wait_for_load_state("networkidle")
        context.storage_state(path=AUTH_FILE)
        print("[+] Session state persisted to auth.json.")


def send_espionage_probe(page, target_coords: str, source_coords: str = "2:30:3", probe_count: int = 1):
    """
    Sends espionage probes to a target planet to trigger NPC response.
    Can be called multiple times for different targets.
    
    Args:
        page: Playwright page object
        target_coords: Target planet coordinates (e.g., "2:30:4")
        source_coords: Source planet coordinates (default: main planet)
        probe_count: Number of spy probes to send
    """
    print(f"\n[ESPIONAGE TEST] Sending {probe_count} spy probe(s) from [{source_coords}] to [{target_coords}]")
    
    # Navigate to fleet interface
    safe_goto(page, get_planet_url(source_coords, "fleet/attack"))
    
    # Parse target coordinates
    try:
        target_galaxy, target_system, target_planet = map(int, target_coords.split(":"))
    except Exception:
        print(f"[!] Invalid target coordinates: {target_coords}")
        return False
    
    # Set target coordinates
    galaxy_input = page.locator("input[name='toCoordinate[galaxy]']").first
    system_input = page.locator("input[name='toCoordinate[system]']").first
    planet_input = page.locator("input[name='toCoordinate[planet]']").first
    
    if galaxy_input.count() > 0 and system_input.count() > 0 and planet_input.count() > 0:
        galaxy_input.fill(str(target_galaxy))
        system_input.fill(str(target_system))
        planet_input.fill(str(target_planet))
        human_delay(0.2, 0.3)
    
    # Set mission to espionage
    mission_select = page.locator("select[name='mission']").first
    if mission_select.count() > 0:
        mission_select.select_option("spy")
        human_delay(0.1, 0.2)
    
    # Set spy probe count
    spy_input = page.locator("input[name='ships[spySatellite]']").first
    if spy_input.count() > 0:
        spy_input.fill(str(probe_count))
        human_delay(0.1, 0.2)
    
    # Submit form
    submit_button = page.locator("button[data-action='fleet#send']").first
    if submit_button.count() > 0 and submit_button.is_visible():
        print(f"[+] Sending espionage mission...")
        submit_button.click()
        page.wait_for_load_state("networkidle")
        
        # Check for errors
        error_elements = page.locator(".alert-danger, .error").all()
        if error_elements:
            for error in error_elements:
                if error.is_visible():
                    error_text = error.inner_text()
                    print(f"[!] Espionage send error: {error_text}")
                    return False
        
        print(f"[+] Espionage mission sent successfully!")
        return True
    else:
        print("[!] Send button not found or not visible.")
        return False


def monitor_incoming_fleets(page, defense, coords: str = "2:30:3", duration_seconds: int = 300, capture_html: bool = True):
    """
    Monitors for incoming fleets and captures detailed information.
    
    Args:
        page: Playwright page object
        defense: DefenseManager instance
        coords: Planet coordinates to monitor
        duration_seconds: How long to monitor (default: 5 minutes)
        capture_html: Whether to capture HTML snapshots of fleet events
    """
    print(f"\n[FLEET MONITOR] Starting monitoring on [{coords}] for {duration_seconds} seconds")
    print(f"[FLEET MONITOR] Dry-run mode: {FLEET_PROTECTION_DRY_RUN}")
    print(f"[FLEET MONITOR] Capture HTML: {capture_html}")
    print("=" * 60)
    
    start_time = time.time()
    captured_events = []
    
    while time.time() - start_time < duration_seconds:
        try:
            # Check for incoming fleets
            incoming = defense.check_incoming_fleets(coords=coords)
            
            if incoming:
                for event in incoming:
                    # Check if this is a new event (not already captured)
                    event_key = f"{event['mission']}_{event['remaining_seconds']}"
                    if event_key not in [e['key'] for e in captured_events]:
                        print(f"\n[🚨 NEW FLEET DETECTED]")
                        print(f"    Mission: {event['mission']}")
                        print(f"    ETA: {event['remaining_seconds']}s ({round(event['remaining_seconds']/60, 1)}m)")
                        print(f"    Hostile: {event['is_hostile']}")
                        print(f"    Arrival: {event.get('arrival_time', 'N/A')}")
                        
                        # Capture HTML if requested
                        if capture_html:
                            html_content = page.content()
                            timestamp = time.strftime("%Y%m%d_%H%M%S")
                            html_file = f"errors/fleet_event_{timestamp}.html"
                            
                            try:
                                os.makedirs("errors", exist_ok=True)
                                with open(html_file, "w", encoding="utf-8") as f:
                                    f.write(html_content)
                                print(f"    HTML captured: {html_file}")
                            except Exception as e:
                                print(f"    [!] Failed to capture HTML: {e}")
                        
                        # Save event details
                        captured_events.append({
                            'key': event_key,
                            'timestamp': int(time.time()),
                            'event': event
                        })
            
            # Short sleep between checks
            time.sleep(5)
            
        except PlaywrightError as e:
            print(f"[!] Monitoring error: {e}")
            time.sleep(10)
        except KeyboardInterrupt:
            print("\n[!] Monitoring interrupted by user.")
            break
    
    print(f"\n[FLEET MONITOR] Monitoring complete. Total events captured: {len(captured_events)}")
    
    # Save captured events to JSON
    if captured_events:
        events_file = "errors/fleet_events_log.json"
        try:
            with open(events_file, "w", encoding="utf-8") as f:
                json.dump(captured_events, f, indent=2)
            print(f"[+] Events saved to: {events_file}")
        except Exception as e:
            print(f"[!] Failed to save events: {e}")
    
    return captured_events


def main():
    parser = argparse.ArgumentParser(
        description="Fleet Protection Testing Script",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        "--mode",
        choices=["monitor", "trigger-espionage", "both"],
        default="monitor",
        help="Testing mode: monitor only, trigger espionage, or both"
    )
    
    parser.add_argument(
        "--coords",
        default="2:30:3",
        help="Planet coordinates to monitor/send from"
    )
    
    parser.add_argument(
        "--target",
        nargs="+",
        default=["2:30:4"],
        help="Target coordinates for espionage (for trigger mode). Can specify multiple: --target 2:30:4 2:30:9"
    )
    
    parser.add_argument(
        "--duration",
        type=int,
        default=300,
        help="Monitoring duration in seconds"
    )
    
    parser.add_argument(
        "--probes",
        type=int,
        default=1,
        help="Number of spy probes to send"
    )
    
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="Disable HTML capture (faster, less detailed)"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("    Fleet Protection Testing Script")
    print("=" * 60)
    print(f"Mode: {args.mode}")
    print(f"Planet: [{args.coords}]")
    print(f"Target(s): {args.target}")
    print(f"Duration: {args.duration}s")
    print(f"Probes: {args.probes}")
    print(f"HTML Capture: {not args.no_html}")
    print(f"Dry-Run: {FLEET_PROTECTION_DRY_RUN}")
    print("=" * 60)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=CHROMIUM_ARGS
        )

        context_kwargs = {
            "user_agent": USER_AGENT,
            "viewport": VIEWPORT,
            "device_scale_factor": DEVICE_SCALE_FACTOR,
            "locale": LOCALE,
            "timezone_id": TIMEZONE_ID,
        }

        if os.path.exists(AUTH_FILE):
            context_kwargs["storage_state"] = AUTH_FILE

        context = browser.new_context(**context_kwargs)
        setup_route_filtering(context)
        context.add_init_script(STEALTH_SCRIPT)
        page = context.new_page()

        defense = DefenseManager(page)

        try:
            login_if_needed(page, context)
            
            if args.mode in ["trigger-espionage", "both"]:
                print("\n[PHASE 1] Triggering NPC espionage response...")
                
                # Handle multiple targets
                targets = args.target if isinstance(args.target, list) else [args.target]
                success_count = 0
                
                for target in targets:
                    print(f"\n[*] Targeting planet [{target}]...")
                    success = send_espionage_probe(
                        page, 
                        target_coords=target,
                        source_coords=args.coords,
                        probe_count=args.probes
                    )
                    if success:
                        success_count += 1
                        human_delay(2, 4)  # Small delay between multiple sends
                
                if success_count == 0:
                    print("[!] Failed to send espionage probes to any target. Continuing to monitor mode.")
                else:
                    print(f"[+] Espionage sent to {success_count}/{len(targets)} target(s).")
                    print("[+] NPC should respond within 1-5 minutes.")
                    print("[*] Starting monitoring immediately...")
            
            if args.mode in ["monitor", "both"]:
                print("\n[PHASE 2] Monitoring for incoming fleets...")
                events = monitor_incoming_fleets(
                    page,
                    defense,
                    coords=args.coords,
                    duration_seconds=args.duration,
                    capture_html=not args.no_html
                )
                
                if events:
                    print(f"\n[✅] Successfully captured {len(events)} fleet event(s)")
                    print("[✅] Check errors/ directory for HTML snapshots and event logs")
                else:
                    print(f"\n[ℹ️] No fleet events captured during monitoring period")
                    print("[ℹ️] This could mean:")
                    print("    - No fleets were incoming")
                    print("    - NPC didn't respond to espionage")
                    print("    - Detection logic needs adjustment")
        
        except KeyboardInterrupt:
            print("\n[!] Testing interrupted by user.")
        except Exception as e:
            print(f"[!] Testing error: {e}")
        finally:
            context.close()
            browser.close()
    
    print("\n" + "=" * 60)
    print("    Testing Complete")
    print("=" * 60)


if __name__ == "__main__":
    main()