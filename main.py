import os
import time
import random
from playwright.sync_api import sync_playwright, Error as PlaywrightError

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
    safe_goto,
    get_planet_url,
    save_error_snapshot,
)
from telemetry import TelemetryManager
from shipyard import ShipyardManager
from defense import DefenseManager
from planner import PlannerManager


def login_if_needed(page, context):
    """Checks session status and executes login if unauthenticated or on login page."""
    safe_goto(page, f"{BASE_URL}/login")

    back_to_game = page.get_by_role("link", name="BACK TO GAME")
    if back_to_game.count() > 0 and back_to_game.is_visible():
        back_to_game.click()
        return

    email_field = page.get_by_role("textbox", name="Email address")
    if email_field.count() > 0 and email_field.is_visible():
        print("[*] Performing automated authentication...")
        email_field.fill(EMAIL)
        page.get_by_role("textbox", name="Password").fill(PASSWORD)
        page.get_by_role("button", name="Log in").click()
        page.wait_for_load_state("networkidle")
        context.storage_state(path=AUTH_FILE)
        print("[+] Session state persisted to auth.json.")


def run():
    print("==================================================")
    print("    GigraWars Headless Automation Daemon Active   ")
    print(f"    Mode: Headless={HEADLESS} | Viewport={VIEWPORT['width']}x{VIEWPORT['height']}")
    print("==================================================")

    with sync_playwright() as p:
        # 1. Launch with Linux VPS compatibility & anti-detection arguments
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=CHROMIUM_ARGS,
        )

        # 2. Configure desktop browser spoofing parameters
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

        # 3. Mask navigator.webdriver and automation signatures
        context.add_init_script(STEALTH_SCRIPT)

        page = context.new_page()

        telemetry = TelemetryManager(page)
        shipyard = ShipyardManager(page, telemetry)
        defense = DefenseManager(page)
        planner = PlannerManager(page, telemetry)

        try:
            login_if_needed(page, context)
        except PlaywrightError as auth_err:
            print(f"[⚠️ Login Exception]: {auth_err}")
            save_error_snapshot(page, prefix="login_failure")

        print("[+] Modular Bot Loop Active.\n")
        try:
            while True:
                print(f"\n=== [Cycle: {time.strftime('%H:%M:%S')}] ===")

                try:
                    # Retrieve primary planet context from build_queue.json
                    queue_data = planner.load_queue_data()
                    main_coords = queue_data.get("main_planet", "3:7:1")

                    # 1. Check Global Fleet Movements
                    incoming = defense.check_incoming_fleets(
                        coords=main_coords)

                    # 2. Check Telemetry & Exposed Resources on Main Planet
                    resources = telemetry.get_resources()
                    exposed = telemetry.calculate_exposed_resources(
                        coords=main_coords)

                    # 3. Process Build Queue Goals Across Empire
                    planner.process_goals()

                    # 4. Safeguard Main Planet Resources
                    shipyard.protect_and_recycle_resources(
                        exposed, coords=main_coords)

                    # 5. Queue Inspection & Capped Adaptive Sleep
                    is_b, b_time = telemetry.get_queue_status(
                        "construction", coords=main_coords)
                    is_r, r_time = telemetry.get_queue_status(
                        "research", coords=main_coords)
                    is_s, s_time = telemetry.get_queue_status(
                        "ship", coords=main_coords)

                    active_timers = [t for t in [
                        b_time, r_time, s_time] if t > 0]
                    heartbeat_cap = random.randint(180, 300)

                    imminent_attack = any(
                        e["mission"].lower(
                        ) == "attack" and e["remaining_seconds"] <= 300
                        for e in incoming
                    )

                    if imminent_attack:
                        sleep_time = 30
                        print(
                            "[🚨 ALERT] Imminent attack detected! High-frequency monitoring active (30s sleep).")
                    elif active_timers:
                        shortest_timer = min(
                            active_timers) + random.randint(5, 10)

                        if shortest_timer < heartbeat_cap:
                            sleep_time = shortest_timer
                            print(
                                f"[*] Build finishing soon ({shortest_timer}s). Sleeping until completion...")
                        else:
                            sleep_time = heartbeat_cap
                            print(
                                f"[*] Long build active ({min(active_timers)}s remaining). Capped sleep heartbeat for {sleep_time}s...")
                    else:
                        sleep_time = heartbeat_cap
                        print(
                            f"[*] Queues free. Sleeping heartbeat ({sleep_time}s)...")

                except PlaywrightError as err:
                    print(f"[⚠️ Network/Navigation Warning]: {err}")
                    # Capture screenshot and HTML DOM dump for headless diagnostics
                    save_error_snapshot(page, prefix="cycle_error")
                    print(
                        "[*] Browser session settling for 10 seconds before next cycle...")
                    sleep_time = 10

                time.sleep(sleep_time)

        except KeyboardInterrupt:
            print("[-] Bot stopped by user.")
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    run()
