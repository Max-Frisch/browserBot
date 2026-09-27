import os
import time
import random
import math
import json
import datetime
from playwright.sync_api import Page, Error as PlaywrightError

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_URL = "https://apex.gigrawars.de"
AUTH_FILE = "auth.json"
BUILD_QUEUE_FILE = "build_queue.json"
HUMAN_BEHAVIOR_FILE = "human_behavior.json"
SHIP_QUEUE_ORIGINS_FILE = "ship_queue_origins.json"

# Ship origin constants
SHIP_ORIGIN_USER = "user"
SHIP_ORIGIN_DEFENSE = "defense"
SHIP_ORIGIN_UNKNOWN = "unknown"


def load_human_behavior_config() -> dict:
    """Loads human behavior configuration from JSON file."""
    default_config = {
        "timezone": "Asia/Jakarta",
        "sleep_hours": {
            "enabled": True,
            "start_hour": 23,
            "end_hour": 7,
            "sleep_probability": 0.8,
            "min_sleep_duration": 21600,
            "max_sleep_duration": 28800
        },
        "breaks": {
            "short_break": {
                "enabled": True,
                "interval_cycles": [30, 50],
                "duration_seconds": [300, 900]
            },
            "long_break": {
                "enabled": True,
                "interval_cycles": [100, 150],
                "duration_seconds": [1800, 3600]
            }
        },
        "behavior": {
            "mistake_probability": 0.02,
            "exploration_probability": 0.05,
            "shuffle_queue_probability": 0.3,
            "timing_jitter_seconds": [-30, 60]
        },
        "browser_fingerprinting": {
            "random_viewport": True,
            "random_locale": True,
            "random_timezone": False,
            "canvas_protection": True,
            "webrtc_protection": True
        }
    }
    
    if os.path.exists(HUMAN_BEHAVIOR_FILE):
        try:
            with open(HUMAN_BEHAVIOR_FILE, "r", encoding="utf-8") as f:
                user_config = json.load(f)
                # Merge user config with defaults
                default_config.update(user_config)
                return default_config
        except Exception as e:
            print(f"[!] Error loading human behavior config: {e}. Using defaults.")
    
    return default_config


# Load human behavior configuration (must be loaded before use)
HUMAN_CONFIG = load_human_behavior_config()

EMAIL = os.getenv("GIGRAWARS_EMAIL", "jakartamax123@gmail.com")
PASSWORD = os.getenv("GIGRAWARS_PASS", "78qj6DzALDe3VaR")

# Discord Remote Management Settings
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_ADMIN_USER_ID = int(os.getenv("DISCORD_ADMIN_USER_ID", "0")) if os.getenv("DISCORD_ADMIN_USER_ID") else 0
DISCORD_CHANNEL_FLEET_ALERTS = int(os.getenv("DISCORD_CHANNEL_FLEET_ALERTS", "0")) if os.getenv("DISCORD_CHANNEL_FLEET_ALERTS") else 0
DISCORD_CHANNEL_BOT_LOGS = int(os.getenv("DISCORD_CHANNEL_BOT_LOGS", "0")) if os.getenv("DISCORD_CHANNEL_BOT_LOGS") else 0
DISCORD_CHANNEL_COMMANDS = int(os.getenv("DISCORD_CHANNEL_COMMANDS", "0")) if os.getenv("DISCORD_CHANNEL_COMMANDS") else 0
DISCORD_CHANNEL_UNIVERSE_MAPPING = int(os.getenv("DISCORD_CHANNEL_UNIVERSE_MAPPING", "0")) if os.getenv("DISCORD_CHANNEL_UNIVERSE_MAPPING") else 0
DISCORD_CHANNEL_BUILD_QUEUE = int(os.getenv("DISCORD_CHANNEL_BUILD_QUEUE", "1552503746863562803")) if os.getenv("DISCORD_CHANNEL_BUILD_QUEUE", "1552503746863562803") else 1552503746863562803

# Headless & VPS Deployment Settings
HEADLESS = os.getenv("HEADLESS", "true").lower() in ("true", "1", "yes")

# Desktop Browser Spoofing Profile
USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

# Variable viewport for more realistic fingerprinting
def get_random_viewport():
    widths = [1920, 1366, 1536, 1440, 1280]
    heights = [1080, 768, 864, 900, 720]
    width = random.choice(widths)
    height = random.choice([h for h in heights if h >= width * 0.56])  # Aspect ratio ~16:9
    return {"width": width, "height": height}

# Apply human behavior configuration
if HUMAN_CONFIG["browser_fingerprinting"]["random_viewport"]:
    VIEWPORT = get_random_viewport()
else:
    VIEWPORT = {"width": 1920, "height": 1080}

DEVICE_SCALE_FACTOR = random.choice([1.0, 1.25, 1.5])

if HUMAN_CONFIG["browser_fingerprinting"]["random_locale"]:
    LOCALE = random.choice(["en-US", "en-GB", "en-CA"])
else:
    LOCALE = "en-US"

# Use configured timezone (WIB for Indonesia)
if HUMAN_CONFIG["browser_fingerprinting"]["random_timezone"]:
    TIMEZONE_ID = random.choice(["America/New_York", "Europe/London", "Europe/Berlin", "America/Los_Angeles"])
else:
    TIMEZONE_ID = HUMAN_CONFIG["timezone"]

# Chromium flags for stealth and headless stability on Linux VPS
CHROMIUM_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions-except",
    "--disable-extensions",
    "--disable-infobars",
    "--disable-notifications",
    "--disable-popup-blocking",
    "--disable-translate",
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-breakpad",
    "--disable-component-extensions-with-background-pages",
    "--disable-features=TranslateUI,BlinkGenPropertyTrees",
    "--disable-ipc-flooding-protection",
    "--disable-renderer-backgrounding",
    "--enable-features=NetworkService,NetworkServiceInProcess",
    "--force-color-profile=srgb",
    "--hide-scrollbars",
    "--metrics-recording-only",
    "--mute-audio",
    "--no-errdialogs",
    "--no-sandbox",
    "--disable-web-security",  # Use with caution
    "--disable-features=IsolateOrigins,site-per-process",
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

    // 3. Mock plugins list with realistic plugin objects
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const plugins = [
                { name: 'Chrome PDF Plugin', description: 'Portable Document Format', filename: 'internal-pdf-viewer' },
                { name: 'Chrome PDF Viewer', description: '', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                { name: 'Native Client', description: '', filename: 'internal-nacl-plugin' }
            ];
            return plugins;
        },
    });

    // 4. Mock languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en', 'en-GB'],
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

    // 6. Mask automation-related properties
    delete window.cdc_adoQnausk;
    delete window.cdc_adoQnausk_cdc;
    delete window.cdc_adoQnausk_cdc_cdc;
    
    // 7. Override navigator properties
    Object.defineProperty(navigator, 'hardwareConcurrency', {
        get: () => 8,
    });
    
    Object.defineProperty(navigator, 'deviceMemory', {
        get: () => 8,
    });

    // 8. Canvas fingerprint protection
    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(type) {
        if (this.width && this.height && this.width > 0 && this.height > 0) {
            const context = this.getContext('2d');
            if (context) {
                const imageData = context.getImageData(0, 0, this.width, this.height);
                for (let i = 0; i < imageData.data.length; i += 4) {
                    imageData.data[i] = imageData.data[i] + Math.floor(Math.random() * 3) - 1;
                    imageData.data[i + 1] = imageData.data[i + 1] + Math.floor(Math.random() * 3) - 1;
                    imageData.data[i + 2] = imageData.data[i + 2] + Math.floor(Math.random() * 3) - 1;
                }
                context.putImageData(imageData, 0, 0);
            }
        }
        return originalToDataURL.apply(this, arguments);
    };

    // 9. WebRTC leak prevention
    const originalRTCPeerConnection = window.RTCPeerConnection || window.webkitRTCPeerConnection;
    if (originalRTCPeerConnection) {
        window.RTCPeerConnection = function() {
            const pc = new originalRTCPeerConnection(arguments);
            const originalCreateDataChannel = pc.createDataChannel;
            pc.createDataChannel = function() {
                const channel = originalCreateDataChannel.apply(this, arguments);
                const originalSend = channel.send;
                channel.send = function() {
                    // Block WebRTC data channel sends that could leak IP
                    return;
                };
                return channel;
            };
            return pc;
        };
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


def human_mouse_move(page: Page, target_element):
    """
    Simulates realistic mouse movement with natural curves and varying speed.
    This makes clicks look more human-like instead of instant element targeting.
    """
    try:
        # Get element bounding box
        box = target_element.bounding_box()
        if not box:
            return

        # Starting position (slightly random offset from current mouse position)
        start_x = random.randint(100, 500)
        start_y = random.randint(100, 500)
        
        # Target position with slight randomness
        target_x = box['x'] + box['width'] / 2 + random.randint(-5, 5)
        target_y = box['y'] + box['height'] / 2 + random.randint(-5, 5)
        
        # Generate intermediate points for curved path
        points = []
        steps = random.randint(5, 12)
        for i in range(1, steps + 1):
            progress = i / steps
            # Add some curve randomness
            curve_offset = math.sin(progress * math.pi) * random.randint(-20, 20)
            x = start_x + (target_x - start_x) * progress + curve_offset
            y = start_y + (target_y - start_y) * progress + curve_offset
            points.append((x, y))
        
        # Move mouse through points with varying speed
        for i, (x, y) in enumerate(points):
            page.mouse.move(x, y)
            # Varying speed between movements
            delay = random.uniform(0.01, 0.05)
            time.sleep(delay)
        
        # Final small pause before click
        time.sleep(random.uniform(0.02, 0.08))
        
    except Exception as e:
        # Fallback to direct click if mouse movement fails
        pass


def human_click(page: Page, element):
    """
    Performs a human-like click with mouse movement simulation.
    Use this instead of element.click() for important interactions.
    """
    try:
        human_mouse_move(page, element)
        element.click()
        human_delay(0.1, 0.3)  # Post-click delay
    except Exception as e:
        # Fallback to direct click
        element.click()


def should_take_break(cycle_count: int) -> tuple[bool, int]:
    """
    Determines if the bot should take a human-like break.
    Returns (should_break, break_duration_seconds).
    
    Uses configuration from human_behavior.json for customizable behavior patterns.
    """
    # Short breaks (configured in JSON)
    short_break_config = HUMAN_CONFIG["breaks"]["short_break"]
    if short_break_config["enabled"]:
        interval = random.randint(*short_break_config["interval_cycles"])
        if cycle_count % interval == 0:
            duration = random.randint(*short_break_config["duration_seconds"])
            return True, duration
    
    # Long breaks (configured in JSON)
    long_break_config = HUMAN_CONFIG["breaks"]["long_break"]
    if long_break_config["enabled"]:
        interval = random.randint(*long_break_config["interval_cycles"])
        if cycle_count % interval == 0:
            duration = random.randint(*long_break_config["duration_seconds"])
            return True, duration
    
    # Sleep hours (configured in JSON - WIB time)
    sleep_config = HUMAN_CONFIG["sleep_hours"]
    if sleep_config["enabled"]:
        # Get current hour in configured timezone (WIB = UTC+7)
        try:
            # Simple timezone conversion without pytz dependency
            utc_offset = 7  # WIB is UTC+7
            utc_time = datetime.datetime.utcnow()
            wib_time = utc_time + datetime.timedelta(hours=utc_offset)
            current_hour = wib_time.hour
        except Exception as e:
            print(f"[!] Timezone error: {e}, using local time")
            current_hour = time.localtime().tm_hour
        
        start_hour = sleep_config["start_hour"]
        end_hour = sleep_config["end_hour"]
        
        # Handle overnight sleep schedule (e.g., 23:00 to 07:00)
        if start_hour > end_hour:
            in_sleep_hours = current_hour >= start_hour or current_hour < end_hour
        else:
            in_sleep_hours = start_hour <= current_hour < end_hour
        
        if in_sleep_hours and random.random() < sleep_config["sleep_probability"]:
            duration = random.randint(sleep_config["min_sleep_duration"], sleep_config["max_sleep_duration"])
            return True, duration
    
    return False, 0


def add_random_mistake_probability() -> bool:
    """
    Small probability of making a "human mistake" like a misclick or wrong navigation.
    This makes behavior more unpredictable and human-like.
    Uses configured probability from human_behavior.json.
    """
    return random.random() < HUMAN_CONFIG["behavior"]["mistake_probability"]


def should_do_exploration() -> bool:
    """
    Determines if the bot should do random page exploration like a curious player.
    Uses configured probability from human_behavior.json.
    """
    return random.random() < HUMAN_CONFIG["behavior"]["exploration_probability"]


def should_shuffle_queue() -> bool:
    """
    Determines if the bot should shuffle planet processing order.
    Uses configured probability from human_behavior.json.
    """
    return random.random() < HUMAN_CONFIG["behavior"]["shuffle_queue_probability"]


def add_timing_jitter(target_time: int) -> int:
    """
    Adds human-like timing jitter to scheduled events.
    Uses configured jitter range from human_behavior.json.
    """
    jitter_range = HUMAN_CONFIG["behavior"]["timing_jitter_seconds"]
    jitter = random.randint(jitter_range[0], jitter_range[1])
    return max(0, target_time + jitter)


# Ship Queue Origin Tracking Functions
def load_ship_queue_origins() -> dict:
    """Loads ship queue origins from JSON file."""
    default_data = {"ship_queues": {}}
    
    if os.path.exists(SHIP_QUEUE_ORIGINS_FILE):
        try:
            with open(SHIP_QUEUE_ORIGINS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[!] Error loading ship queue origins: {e}. Using defaults.")
    
    return default_data


def save_ship_queue_origins(data: dict):
    """Saves ship queue origins to JSON file atomically."""
    temp_file = f"{SHIP_QUEUE_ORIGINS_FILE}.tmp"
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_file, SHIP_QUEUE_ORIGINS_FILE)
    except Exception as e:
        print(f"[!] Error saving ship queue origins: {e}")
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass


def add_ship_queue_entry(coords: str, ship_name: str, quantity: int, origin: str):
    """Adds a ship queue entry with origin tracking."""
    data = load_ship_queue_origins()
    
    if coords not in data["ship_queues"]:
        data["ship_queues"][coords] = []
    
    # Add new entry
    entry = {
        "ship_name": ship_name,
        "quantity": quantity,
        "origin": origin,
        "timestamp": int(time.time()),
        "planet_coords": coords
    }
    data["ship_queues"][coords].append(entry)
    
    save_ship_queue_origins(data)


def remove_ship_queue_entry(coords: str, ship_name: str):
    """Removes a ship queue entry from tracking."""
    data = load_ship_queue_origins()
    
    if coords in data["ship_queues"]:
        data["ship_queues"][coords] = [
            entry for entry in data["ship_queues"][coords]
            if entry["ship_name"] != ship_name
        ]
        
        # Clean up empty planet entries
        if not data["ship_queues"][coords]:
            del data["ship_queues"][coords]
    
    save_ship_queue_origins(data)


def get_ship_queue_origin(coords: str, ship_name: str) -> str:
    """Gets the origin of a specific ship queue entry."""
    data = load_ship_queue_origins()
    
    if coords in data["ship_queues"]:
        for entry in data["ship_queues"][coords]:
            if entry["ship_name"] == ship_name:
                return entry["origin"]
    
    return SHIP_ORIGIN_UNKNOWN


def clear_defense_ship_queues(coords: str):
    """Clears only defense-originated ship queue entries."""
    data = load_ship_queue_origins()
    
    if coords in data["ship_queues"]:
        data["ship_queues"][coords] = [
            entry for entry in data["ship_queues"][coords]
            if entry["origin"] != SHIP_ORIGIN_DEFENSE
        ]
        
        # Clean up empty planet entries
        if not data["ship_queues"][coords]:
            del data["ship_queues"][coords]
    
    save_ship_queue_origins(data)


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

            print(f"[Snapshot Captured] Headless diagnostics saved:")
            print(f" - Screenshot: {screenshot_path}")
            print(f" - HTML DOM:   {html_path}")
            return screenshot_path, html_path
    except Exception as exc:
        print(f"[!] Failed to capture error snapshot: {exc}")

    return None, None
