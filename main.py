import os
import sys
import json
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
    setup_route_filtering,
    safe_goto,
    get_planet_url,
    save_error_snapshot,
    human_delay,
)
from telemetry import TelemetryManager
from shipyard import ShipyardManager
from defense import DefenseManager
from planner import PlannerManager
from discord_manager import DiscordManager
import discord_manager


class Logger(object):
    def __init__(self, filename="bot.log"):
        self.terminal = sys.stdout
        self.logfile = open(filename, "a", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.terminal.flush()
        self.logfile.write(message)
        self.logfile.flush()

    def flush(self):
        self.terminal.flush()
        self.logfile.flush()


sys.stdout = Logger("bot.log")
sys.stderr = sys.stdout


def login_if_needed(page, context):
    """Checks session status and executes login if unauthenticated or on login page."""
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

        # 3. Setup high-performance route filtering (block images, fonts, media, and ads)
        setup_route_filtering(context)

        # 4. Mask navigator.webdriver and automation signatures
        context.add_init_script(STEALTH_SCRIPT)

        page = context.new_page()

        telemetry = TelemetryManager(page)
        shipyard = ShipyardManager(page, telemetry)
        defense = DefenseManager(page)
        planner = PlannerManager(page, telemetry)

        # Initialize Discord remote manager
        discord_mgr = DiscordManager(
            telemetry_getter=lambda: telemetry.get_empire_overview(),
            snapshot_callback=lambda: save_error_snapshot(page, prefix="manual_snapshot")[0]
        )
        discord_mgr.start()

        try:
            login_if_needed(page, context)
        except PlaywrightError as auth_err:
            print(f"[⚠️ Login Exception]: {auth_err}")
            save_error_snapshot(page, prefix="login_failure")

        print("[+] Modular Bot Loop Active.\n")
        cycle_count = 0
        try:
            while True:
                # Check if paused via Discord
                if discord_manager.BOT_PAUSED:
                    print("[⏸️ BOT PAUSED] Automation temporarily suspended via Discord. Sleeping 15s...")
                    time.sleep(15)
                    continue

                cycle_count += 1
                print(f"\n=== [Cycle: {time.strftime('%H:%M:%S')} | #{cycle_count}] ===")

                try:
                    # Retrieve primary planet context from build_queue.json
                    queue_data = planner.load_queue_data()
                    main_coords = queue_data.get("main_planet", "3:7:1")

                    # 1. Sentry Watchdog: Check Global Fleet Movements & Dispatch Discord Alerts
                    incoming = defense.check_incoming_fleets(coords=main_coords)

                    hostile_incoming = [ev for ev in incoming if ev.get("is_hostile")]
                    imminent_attack = any(
                        ev.get("remaining_seconds", 9999) <= 300 for ev in hostile_incoming
                    )

                    for ev in hostile_incoming:
                        discord_mgr.send_fleet_alert(
                            title=f"Incoming Fleet: {ev['mission']}",
                            description=f"Hostile movement detected heading towards **[{main_coords}]**!",
                            fields={
                                "Target Planet": f"[{main_coords}]",
                                "ETA": f"{ev['remaining_seconds']}s ({round(ev['remaining_seconds'] / 60, 1)}m)",
                                "Arrival Time": ev.get("arrival_time", "N/A"),
                            },
                            urgent=True
                        )

                    # 2. Check Telemetry & Exposed Resources on Main Planet
                    resources = telemetry.get_resources()

                    # 3. Safeguard Main Planet Resources if imminent attack is threatening or excess exists
                    shipyard.protect_and_recycle_resources(
                        coords=main_coords, emergency=imminent_attack
                    )

                    # 4. Process Build Queue Goals Across Empire (returns remaining seconds per planet)
                    empire_timers = planner.process_goals()

                    # 5. Empire-Wide Queue Inspection & Adaptive Sleep
                    # Merge timers from the planner with main planet queues
                    all_active_timers = dict(empire_timers)

                    # Inspect live empire overview for any active ship queues
                    overview = telemetry.get_empire_overview()
                    for p, s_info in overview.get("ship_queues", {}).items():
                        s_rem = s_info.get("remaining_seconds", 0)
                        if s_rem > 0:
                            all_active_timers[f"{p}:ship"] = s_rem

                    # Inspect capital research queue (research only exists on main planet)
                    is_r, r_time = telemetry.get_queue_status(
                        "research", coords=main_coords)
                    if is_r and r_time > 0:
                        all_active_timers[f"{main_coords}:research"] = r_time

                    active_seconds = [t for t in all_active_timers.values() if t > 0]
                    heartbeat_cap = random.randint(180, 300)

                    if imminent_attack:
                        sleep_time = 30
                        print(
                            "[🚨 ALERT] Imminent attack detected! High-frequency monitoring active (30s sleep).")
                    elif active_seconds:
                        # Find the fastest upcoming build completion across the whole empire
                        shortest_sec = min(active_seconds)
                        # Add a humanized jitter buffer
                        jitter_buffer = random.randint(4, 9)
                        target_sleep = shortest_sec + jitter_buffer

                        # Find which planet/queue is triggering this wake-up
                        trigger_target = next(
                            (k for k, v in all_active_timers.items() if v == shortest_sec),
                            "colony"
                        )

                        if target_sleep < heartbeat_cap:
                            sleep_time = target_sleep
                            print(
                                f"[*] Active build on [{trigger_target}] finishing soon ({shortest_sec}s). Adaptive sleep for {sleep_time}s...")
                        else:
                            sleep_time = heartbeat_cap
                            print(
                                f"[*] Long build active on [{trigger_target}] ({shortest_sec}s remaining). Capped sleep heartbeat for {sleep_time}s...")
                    else:
                        sleep_time = heartbeat_cap
                        print(
                            f"[*] All queues idle across empire. Sleeping heartbeat ({sleep_time}s)...")

                    # Dispatch periodic heartbeat log to Discord #bot-logs
                    if cycle_count % 5 == 1 or imminent_attack:
                        discord_mgr.send_bot_log(
                            title=f"Cycle #{cycle_count} Heartbeat",
                            description=f"Primary planet: `[{main_coords}]` | Sleeping `{sleep_time}s`",
                            fields={
                                "Active Queues": str(len(active_seconds)),
                                "Incoming Fleets": str(len(incoming)),
                            }
                        )

                except PlaywrightError as err:
                    print(f"[⚠️ Network/Navigation Warning]: {err}")
                    # Capture screenshot and HTML DOM dump for headless diagnostics
                    save_error_snapshot(page, prefix="cycle_error")
                    print(
                        "[*] Browser session settling for 10 seconds before next cycle...")
                    sleep_time = 10
                except Exception as err:
                    print(f"[⚠️ Unexpected Exception in Cycle]: {err}")
                    save_error_snapshot(page, prefix="unexpected_cycle_error")
                    sleep_time = 15

                time.sleep(sleep_time)

        except KeyboardInterrupt:
            print("[-] Bot stopped by user.")
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    run()
