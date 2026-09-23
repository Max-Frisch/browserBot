# GigraWars Headless VPS Browser Bot

A modular Playwright-based automation suite for GigraWars, engineered for 24/7 background operation on headless Linux VPS environments with anti-detection browser fingerprint spoofing.

---

## Refactor Highlights

1. **Headless Execution & Desktop Spoofing (`main.py`, `config.py`)**:
   - Defaults to `headless=True` (configurable via `HEADLESS` environment variable).
   - **User-Agent:** Modern standard desktop Windows 10 Chrome string.
   - **Viewport & Resolution:** Fixed at `1920x1080` with `device_scale_factor=1`.
   - **Locale & Timezone:** Standardized to `locale="en-US"` and `timezone_id="UTC"`.
   - **Stealth & WebDriver Masking:** Injected client-side initialization script masks `navigator.webdriver`, mocks `window.chrome`, and supplies desktop `navigator.plugins`.
   - **VPS Chromium Flags:** Includes `--disable-blink-features=AutomationControlled`, `--no-sandbox`, `--disable-setuid-sandbox`, and `--disable-dev-shm-usage` for crash-free execution on memory-constrained Linux virtual machines.

2. **Automated Error Snapshotting & Headless Debugging (`config.py`, `main.py`)**:
   - On any `PlaywrightError` (navigation conflict, network drop, missing selector, timeout), the bot automatically generates:
     - A full-page PNG screenshot in `./errors/cycle_error_<timestamp>.png`
     - The complete DOM HTML dump in `./errors/cycle_error_<timestamp>.html`
   - Eliminates blind debugging on headless servers.

3. **Core Logic Preservation & Shipyard Enhancements (`planner.py`, `shipyard.py`)**:
   - Multi-planet routing (`get_planet_url`), parallel building loops, and recursive prerequisite pivot logic remain intact.
   - Added `parse_ship_catalog(coords)` to `ShipyardManager` to parse live resource costs, build durations, and maximum buildable counts directly from the game's `/ship` page.

---

## Linux VPS Quickstart

### 1. System Requirements & Setup
```bash
# Update package repositories and install python3 virtual environment
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Chromium browser binary and Linux system shared libraries
playwright install chromium
playwright install-deps chromium
```

### 2. Configure Credentials & Run
You can configure credentials via environment variables or rely on `config.py`:
```bash
export GIGRAWARS_EMAIL="your_email@example.com"
export GIGRAWARS_PASS="your_secret_password"
export HEADLESS=true

# Launch the bot
python main.py
```

---

## 24/7 Headless VPS Service (systemd)

To ensure the bot automatically restarts after server reboots or network disconnects, create a systemd service:

```bash
sudo nano /etc/systemd/system/gigrawars-bot.service
```

Paste the following template (adjust paths and user accordingly):

```ini
[Unit]
Description=GigraWars Headless Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/gigrawars-bot
Environment="PATH=/home/ubuntu/gigrawars-bot/venv/bin"
Environment="HEADLESS=true"
Environment="GIGRAWARS_EMAIL=your_email@example.com"
Environment="GIGRAWARS_PASS=your_secret_password"
ExecStart=/home/ubuntu/gigrawars-bot/venv/bin/python main.py
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable gigrawars-bot
sudo systemctl start gigrawars-bot

# Monitor live logs:
journalctl -u gigrawars-bot -f
```

---

## File Architecture

| File | Role |
| :--- | :--- |
| `main.py` | Orchestrates headless launch, stealth context setup, login verification, error capture, and main cycle loop. |
| `config.py` | Central configuration, desktop spoofing headers, stealth script, safe navigation, and error snapshot utility. |
| `telemetry.py` | Resource parsing, storage capacity calculation, exposed resource analysis, and active queue monitoring. |
| `planner.py` | Recursive tech tree resolution, prerequisite tree pivoting, parallel construction, and ship orders. |
| `shipyard.py` | Live ship catalog parsing from `/ship`, resource safeguard depositing, and auto-recycling. |
| `defense.py` | Hostile and incoming fleet radar monitoring with adaptive high-frequency sleep triggers. |
| `build_queue.json` | Planetary goals, target upgrade levels, unit orders, and empire configuration. |
| `auth.json` | Persisted session cookies (`PHPSESSID`) for uninterrupted headless logins. |
| `errors/` | Directory where timestamped screenshots and DOM HTML snapshots are written. |
