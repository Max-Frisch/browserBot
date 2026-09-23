import os
import time
import random
from playwright.sync_api import Page, Error as PlaywrightError

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_URL = "https://apex.gigrawars.de"
AUTH_FILE = "auth.json"
BUILD_QUEUE_FILE = "build_queue.json"

EMAIL = os.getenv("GIGRAWARS_EMAIL", "jakartamax123@gmail.com")
PASSWORD = os.getenv("GIGRAWARS_PASS", "78qj6DzALDe3VaR")

# Discord Remote Management Settings
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_ADMIN_USER_ID = int(os.getenv("DISCORD_ADMIN_USER_ID", "0")) if os.getenv("DISCORD_ADMIN_USER_ID") else 0
DISCORD_CHANNEL_FLEET_ALERTS = int(os.getenv("DISCORD_CHANNEL_FLEET_ALERTS", "0")) if os.getenv("DISCORD_CHANNEL_FLEET_ALERTS") else 0
DISCORD_CHANNEL_BOT_LOGS = int(os.getenv("DISCORD_CHANNEL_BOT_LOGS", "0")) if os.getenv("DISCORD_CHANNEL_BOT_LOGS") else 0
DISCORD_CHANNEL_COMMANDS = int(os.getenv("DISCORD_CHANNEL_COMMANDS", "0")) if os.getenv("DISCORD_CHANNEL_COMMANDS") else 0
DISCORD_CHANNEL_UNIVERSE_MAPPING = int(os.getenv("DISCORD_CHANNEL_UNIVERSE_MAPPING", "0")) if os.getenv("DISCORD_CHANNEL_UNIVERSE_MAPPING") else 0

# Headless & VPS Deployment Settings
HEADLESS = os.getenv("HEADLESS", "true").lower() in ("true", "1", "yes")

# Desktop Browser Spoofing Profile
USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
VIEWPORT = {"width": 1920, "height": 1080}
DEVICE_SCALE_FACTOR = 1
LOCALE = "en-US"
TIMEZONE_ID = "UTC"

# Chromium flags for stealth and headless stability on Linux VPS
CHROMIUM_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--no-first-run",
    "--no-default-browser-check",
]

# Client-side injection script to mask automation & navigator.webdriver
STEALTH_SCRIPT = """
(() => {
    // 1. Mask navigator.webdriver
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
    });

    // 2. Mock chrome runtime object
    if (!window.chrome) {
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };
    }

    // 3. Mock plugins list
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
    });

    // 4. Mock languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
    });

    // 5. Mock permissions query
    const originalQuery = window.navigator.permissions ? window.navigator.permissions.query : null;
    if (originalQuery) {
        window.navigator.permissions.query = (parameters) => (
            parameters && parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : originalQuery(parameters)
        );
    }
})();
"""

# Directory for error snapshots and DOM dumps
ERRORS_DIR = os.getenv("ERRORS_DIR", "errors")


def setup_route_filtering(context):
    """
    Aborts non-essential heavy requests:
    - Images (.png, .jpg, .jpeg, .webp, .gif, .ico)
    - Media (.mp4, .mp3, etc.)
    - Fonts (.woff, .woff2, .ttf)
    - Ads and analytics (googlesyndication, doubleclick, etc.)
    Reduces memory footprint, network I/O, and speeds up page transitions significantly.
    """
    def route_handler(route):
        req = route.request
        # Block resource types that do not impact DOM logic
        if req.resource_type in ("image", "media", "font"):
            return route.abort()

        url_lower = req.url.lower()
        if any(ad in url_lower for ad in ["googlesyndication", "googleadservices", "doubleclick", "adnxs", "analytics"]):
            return route.abort()

        return route.continue_()

    context.route("**/*", route_handler)


def human_delay(min_s: float = 0.35, max_s: float = 0.85):
    """Introduces natural gaussian-curved delay to prevent robotic click cadences."""
    mean = (min_s + max_s) / 2.0
    stdev = (max_s - min_s) / 4.0
    delay = random.gauss(mean, stdev)
    clamped_delay = max(min_s, min(delay, max_s))
    time.sleep(clamped_delay)


def get_planet_url(coords: str, endpoint: str = "planet") -> str:
    """Generates a route URL for a specific planet coordinate."""
    return f"{BASE_URL}/app/{coords}/{endpoint}"


def safe_goto(page: Page, url: str, wait_until: str = "domcontentloaded", retries: int = 2):
    """
    Navigates safely to a URL, catching navigation interruptions 
    and transient session redirects, with human-like jitter.
    """
    if page.url == url:
        return

    # Subtle human hesitation before navigation
    time.sleep(random.uniform(0.15, 0.4))

    for attempt in range(retries):
        try:
            page.goto(url, wait_until=wait_until)
            # Settle pause after page loads
            time.sleep(random.uniform(0.3, 0.65))
            return
        except PlaywrightError as e:
            if "is interrupted by another navigation" in str(e):
                print(
                    f"[*] Navigation conflict detected for {url}. Waiting for browser to settle...")
                time.sleep(random.uniform(1.8, 2.4))
                if page.url == url or "planet" in page.url:
                    return
            elif attempt == retries - 1:
                raise e
            time.sleep(random.uniform(0.8, 1.3))


def save_error_snapshot(page: Page, prefix: str = "error") -> tuple[str | None, str | None]:
    """
    Captures a timestamped PNG screenshot and page HTML DOM source to the ERRORS_DIR.
    Provides complete diagnostic context for headless VPS troubleshooting.
    """
    try:
        os.makedirs(ERRORS_DIR, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        screenshot_path = os.path.join(ERRORS_DIR, f"{prefix}_{timestamp}.png")
        html_path = os.path.join(ERRORS_DIR, f"{prefix}_{timestamp}.html")

        if not page.is_closed():
            # 1. Capture full page screenshot
            page.screenshot(path=screenshot_path, full_page=True)

            # 2. Capture complete DOM source
            html_content = page.content()
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            print(f"[📸 Snapshot Captured] Headless diagnostics saved:")
            print(f" └─ Screenshot: {screenshot_path}")
            print(f" └─ HTML DOM:   {html_path}")
            return screenshot_path, html_path
    except Exception as exc:
        print(f"[!] Failed to capture error snapshot: {exc}")

    return None, None
