#!/usr/bin/env python3
"""
scanner.py - Galaxy Cartographer & Universe Scanner for GigraWars.

Inspects solar systems (Galaxy 1-5, System 1-120), maps planet occupancy,
identifies empty slots for colonization, and records players and alliances into universe_map.json.
"""

import os
import re
import sys
import time
import json
import random
import argparse
from typing import Dict, List, Optional, Any, Tuple

from playwright.sync_api import sync_playwright, Page, BrowserContext, Error as PlaywrightError

from config import (
    BASE_URL,
    AUTH_FILE,
    BUILD_QUEUE_FILE,
    EMAIL,
    PASSWORD,
    CHROMIUM_ARGS,
    USER_AGENT,
    VIEWPORT,
    DEVICE_SCALE_FACTOR,
    LOCALE,
    TIMEZONE_ID,
    STEALTH_SCRIPT,
    safe_goto,
    get_planet_url,
    human_delay,
)

MAP_FILE_DEFAULT = "universe_map.json"


def get_main_planet_coords() -> str:
    """Retrieves primary base coordinates from build_queue.json, defaulting to 3:7:1."""
    if os.path.exists(BUILD_QUEUE_FILE):
        try:
            with open(BUILD_QUEUE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("main_planet", "3:7:1")
        except Exception:
            pass
    return "3:7:1"


def load_universe_map(filepath: str = MAP_FILE_DEFAULT) -> dict:
    """Loads existing universe mapping data to ensure incremental updates are preserved."""
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "galaxies" not in data or not isinstance(data["galaxies"], dict):
                    data["galaxies"] = {}
                return data
        except Exception as exc:
            print(f"[!] Warning: Could not parse existing {filepath}: {exc}. Initializing fresh map.")

    return {
        "last_updated": int(time.time()),
        "galaxies": {}
    }


def save_universe_map(data: dict, filepath: str = MAP_FILE_DEFAULT) -> None:
    """Safely flushes universe mapping data to disk using an atomic tempfile write."""
    data["last_updated"] = int(time.time())
    tmp_path = f"{filepath}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, filepath)
    except Exception as exc:
        print(f"[!] Error writing to {filepath}: {exc}")
        # Fallback direct write
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass


def ensure_authenticated(page: Page, context: BrowserContext) -> None:
    """Verifies user session and performs login if unauthenticated."""
    safe_goto(page, f"{BASE_URL}/login")

    back_to_game = page.get_by_role("link", name="BACK TO GAME")
    if back_to_game.count() > 0 and back_to_game.is_visible():
        human_delay(0.2, 0.4)
        back_to_game.click()
        return

    email_field = page.get_by_role("textbox", name="Email address")
    if email_field.count() > 0 and email_field.is_visible():
        print("[*] Re-authenticating session for Galaxy Scanner...")
        human_delay(0.3, 0.6)
        email_field.fill(EMAIL)
        human_delay(0.2, 0.4)
        page.get_by_role("textbox", name="Password").fill(PASSWORD)
        human_delay(0.3, 0.5)
        page.get_by_role("button", name="Log in").click()
        page.wait_for_load_state("networkidle")
        context.storage_state(path=AUTH_FILE)
        print("[+] Authentication persisted to auth.json.")


def parse_galaxy_dom(html: str) -> List[Dict[str, Any]]:
    """
    Parses the planet slots from the galaxy view HTML DOM.
    Returns a list of structured planet objects matching the required schema.
    """
    # Find all planet slot number markers
    matches = list(re.finditer(r"<div[^>]*class=[\"\'][^\"\']*planet-number[^\"\']*[\"\'][^>]*>\s*(\d+)", html))
    slots: List[Dict[str, Any]] = []

    for i, m in enumerate(matches):
        slot_num = int(m.group(1))
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else start + 3500
        block = html[start:end]

        # Extract user container
        user_m = re.search(r"<div[^>]*class=[\"\'][^\"\']*planet-user[^\"\']*[\"\'][^>]*>(.*?)</div>", block, flags=re.DOTALL)
        user_html = user_m.group(1) if user_m else ""

        # Player Name (inside <a href=".../player/UUID">Name</a> or direct text)
        player_m = re.search(r"<a[^>]*href=[\"\'][^\"\']*/player/[^\"\']+[\"\'][^>]*>(.*?)</a>", user_html, flags=re.DOTALL)
        player_name = re.sub(r"<[^>]+>", "", player_m.group(1)).strip() if player_m else None

        # Alliance Name/Tag (<a href=".../alliance/show/TAG">[-TAG-]</a> or [TAG])
        alliance_m = re.search(r"<a[^>]*href=[\"\'][^\"\']*/alliance/[^\"\']+[\"\'][^>]*>(.*?)</a>", user_html, flags=re.DOTALL)
        if alliance_m:
            alliance = re.sub(r"<[^>]+>", "", alliance_m.group(1)).strip()
        else:
            b_m = re.search(r"\[([A-Za-z0-9_\-\s]+)\]", user_html)
            alliance = b_m.group(0).strip() if b_m else None

        # Extract planet name / status info
        info_m = re.search(r"<div[^>]*class=[\"\'][^\"\']*planet-info[^\"\']*[\"\'][^>]*>(.*?)</div>", block, flags=re.DOTALL)
        info_html = info_m.group(1) if info_m else ""
        info_txt = re.sub(r"<[^>]+>", " ", info_html).strip()

        # Determine occupancy
        is_empty = False
        if not player_name:
            if "uncolonized" in info_txt.lower() or not info_txt or info_txt == "Uncolonized":
                is_empty = True
            elif not user_html.strip():
                is_empty = True

        if is_empty:
            status = "empty"
            owner = None
            p_type = "empty"
            alliance = None
        else:
            status = "occupied"
            owner = player_name if player_name else "Unknown"
            lower_owner = owner.lower()
            if "_bot" in lower_owner or "freenation" in lower_owner or "npc" in lower_owner or lower_owner.endswith("bot"):
                p_type = "npc"
            else:
                p_type = "player"

        slots.append({
            "slot": slot_num,
            "status": status,
            "owner": owner,
            "type": p_type,
            "alliance": alliance
        })

    return slots


def scan_solar_system(page: Page, main_coords: str, galaxy: int, system: int) -> Optional[Dict[str, Any]]:
    """
    Navigates to a specific galaxy & system, verifies loaded coordinates,
    and extracts slot statistics.
    """
    # Primary URL specification
    target_query_url = get_planet_url(main_coords, f"galaxy?galaxy={galaxy}&system={system}")
    target_path_url = get_planet_url(main_coords, f"galaxy/{galaxy}/{system}")

    # Navigate via safe_goto
    safe_goto(page, target_query_url)

    # In GigraWars, routing to /galaxy with query params may default to home system.
    # Check if the page reflects the intended galaxy and system; if not, route via path.
    try:
        page.wait_for_selector(".galaxy-view, input[name='system']", timeout=4000)
        sys_input = page.locator("input[name='system']")
        if sys_input.count() > 0:
            current_sys = sys_input.first.input_value()
            if current_sys != str(system):
                safe_goto(page, target_path_url)
                page.wait_for_selector(".galaxy-view", timeout=4000)
    except Exception:
        # Fallback to direct path URL
        safe_goto(page, target_path_url)

    # Wait for galaxy view to render
    page.wait_for_selector(".galaxy-view, .planet-number", timeout=5000)
    html = page.content()

    planets = parse_galaxy_dom(html)
    if not planets:
        return None

    free_count = sum(1 for p in planets if p["status"] == "empty")
    return {
        "total_slots": len(planets),
        "free_slots": free_count,
        "planets": planets
    }


def run_scanner(
    target_galaxy: Optional[int] = None,
    start_system: int = 1,
    end_system: int = 120,
    base_delay: float = 1.2,
    headless: bool = True,
    output_file: str = MAP_FILE_DEFAULT
) -> None:
    """Main scanning routine iterating through galaxies and solar systems."""
    main_coords = get_main_planet_coords()
    universe_data = load_universe_map(output_file)

    galaxies_to_scan = [target_galaxy] if target_galaxy else list(range(1, 6))

    print("==================================================")
    print("        GigraWars Galaxy Scanner Active           ")
    print(f"  Base Planet:   [{main_coords}]")
    print(f"  Galaxies:      {galaxies_to_scan}")
    print(f"  System Range:  {start_system} -> {end_system}")
    print(f"  Delay Cadence: {base_delay}s (+ humanized jitter)")
    print(f"  Headless:      {headless}")
    print(f"  Storage Map:   {output_file}")
    print("==================================================")

    total_systems_scanned = 0
    total_planets_found = 0
    total_free_found = 0
    start_time = time.time()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
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
        context.add_init_script(STEALTH_SCRIPT)
        page = context.new_page()

        try:
            ensure_authenticated(page, context)
        except Exception as auth_err:
            print(f"[!] Authentication warning: {auth_err}")

        try:
            for g in galaxies_to_scan:
                g_key = str(g)
                if g_key not in universe_data["galaxies"]:
                    universe_data["galaxies"][g_key] = {}

                print(f"\n🚀 Scanning Galaxy [{g}] (Systems {start_system}..{end_system})...")

                for s in range(start_system, end_system + 1):
                    s_key = str(s)
                    try:
                        system_data = scan_solar_system(page, main_coords, g, s)
                        if system_data:
                            universe_data["galaxies"][g_key][s_key] = system_data
                            total_systems_scanned += 1
                            total_planets_found += system_data["total_slots"]
                            total_free_found += system_data["free_slots"]

                            free_info = f"({system_data['free_slots']} free)" if system_data["free_slots"] > 0 else "(Full)"
                            print(f"  [{g}:{s:03d}] {system_data['total_slots']} slots {free_info}")
                        else:
                            print(f"  [{g}:{s:03d}] ⚠️ No planet data found.")

                    except PlaywrightError as pw_err:
                        print(f"  [{g}:{s:03d}] ⚠️ Playwright Error: {pw_err}. Retrying once...")
                        time.sleep(1.5)
                        try:
                            retry_data = scan_solar_system(page, main_coords, g, s)
                            if retry_data:
                                universe_data["galaxies"][g_key][s_key] = retry_data
                                total_systems_scanned += 1
                        except Exception as retry_err:
                            print(f"  [{g}:{s:03d}] ❌ Skipped after error: {retry_err}")
                    except Exception as exc:
                        print(f"  [{g}:{s:03d}] ❌ Unexpected error: {exc}")

                    # Incremental flush every 10 systems
                    if total_systems_scanned > 0 and total_systems_scanned % 10 == 0:
                        save_universe_map(universe_data, output_file)
                        print(f"    💾 [Auto-Saved] Flushed progress ({total_systems_scanned} systems mapped) to {output_file}")

                    # Humanized jitter delay between system loads
                    jitter = random.uniform(0.15, 0.45)
                    time.sleep(base_delay + jitter)

        except KeyboardInterrupt:
            print("\n[!] Scan interrupted by user. Preserving all progress...")
        finally:
            save_universe_map(universe_data, output_file)
            browser.close()

    elapsed = round(time.time() - start_time, 1)
    print("\n==================================================")
    print("           Universe Scan Finished                 ")
    print(f"  Total Systems Scanned: {total_systems_scanned}")
    print(f"  Total Planets Found:   {total_planets_found}")
    print(f"  Free Colony Slots:     {total_free_found}")
    print(f"  Elapsed Time:          {elapsed}s")
    print(f"  Saved to:              {output_file}")
    print("==================================================")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Galaxy Cartographer / Universe Scanner for GigraWars",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--galaxy",
        type=int,
        choices=[1, 2, 3, 4, 5],
        default=None,
        help="Target a specific galaxy (1 to 5). If omitted, scans all 5 galaxies."
    )
    parser.add_argument(
        "--start",
        type=int,
        default=1,
        help="Starting solar system number (1 to 120)."
    )
    parser.add_argument(
        "--end",
        type=int,
        default=120,
        help="Ending solar system number (1 to 120)."
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.2,
        help="Pacing delay in seconds between solar system page loads."
    )
    parser.add_argument(
        "--headless",
        type=lambda v: str(v).lower() in ("true", "1", "yes"),
        default=True,
        help="Run browser headlessly (True/False)."
    )
    parser.add_argument(
        "--output",
        type=str,
        default=MAP_FILE_DEFAULT,
        help="Path to save universe mapping JSON."
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_scanner(
        target_galaxy=args.galaxy,
        start_system=args.start,
        end_system=args.end,
        base_delay=args.delay,
        headless=args.headless,
        output_file=args.output
    )
