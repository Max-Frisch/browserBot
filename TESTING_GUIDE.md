# Fleet Protection Testing Guide

## Quick Start Testing

### Option 1: Monitor Only (Safest)
Just monitor for any incoming fleets without triggering anything:

```bash
python test_fleet_protection.py --mode monitor --duration 300
```

This will watch your planet for 5 minutes and capture any fleet movements.

### Option 2: Trigger NPC Espionage Response
Send spy probes to trigger an NPC espionage response:

```bash
# Single target
python test_fleet_protection.py --mode trigger-espionage --target 2:30:4 --probes 1

# Multiple targets (sends to both)
python test_fleet_protection.py --mode trigger-espionage --target 2:30:4 2:30:9 --probes 1
```

This sends 1 spy probe to each target planet (change to nearby NPC planets).

### Option 3: Both (Recommended)
Trigger espionage AND monitor for the response:

```bash
# Single target
python test_fleet_protection.py --mode both --target 2:30:4 --duration 600

# Multiple targets
python test_fleet_protection.py --mode both --target 2:30:4 2:30:9 --duration 600
```

This sends probes to all targets then monitors for 10 minutes to catch the NPC responses.

## Understanding NPC Espionage Response

### What Happens
1. You send spy probes to an NPC planet
2. NPC detects espionage and sends "counter-espionage" 
3. This appears as an incoming fleet on your overview
4. Mission type typically shows as "Spionage" or "Spy"
5. Usually arrives within 1-5 minutes

### Why This is Safe
- NPC espionage is a normal game mechanic
- It's a standard counter-espionage response
- No actual combat occurs (just information gathering)
- NPC fleets are typically small (1-3 ships)
- Perfect for testing detection logic

## Testing Procedure

### Step 1: Find Nearby NPC Planets
1. Use the galaxy view in-game
2. Look for planets with NPC players (marked with bot icon)
3. Choose planets in the same or nearby system (e.g., 2:30:4 and 2:30:9 if you're at 2:30:3)
4. Note the coordinates (you can use multiple targets)

### Step 2: Run the Test Script
```bash
# Start with monitor mode to check current state
python test_fleet_protection.py --mode monitor --duration 60

# Then trigger espionage + monitor (single target)
python test_fleet_protection.py --mode both --target 2:30:4 --duration 600

# Or trigger espionage + monitor (multiple targets)
python test_fleet_protection.py --mode both --target 2:30:4 2:30:9 --duration 600
```

### Step 3: Analyze Results
The script will create files in the `errors/` directory:
- `fleet_event_YYYYMMDD_HHMMSS.html` - HTML snapshot of fleet event
- `fleet_events_log.json` - Detailed event data

### Step 4: Validate Detection Logic
Check the console output for:
- `[🚨 NEW FLEET DETECTED]` - Shows detection worked
- Mission type, ETA, hostile status
- Whether the event was properly classified

## Expected Output Examples

### Successful Detection
```
[🚨 NEW FLEET DETECTED]
    Mission: Spionage
    ETA: 180s (3.0m)
    Hostile: True
    Arrival: 2026-09-28 15:30:00
    HTML captured: errors/fleet_event_20260928_153000.html
```

### No Events
```
[FLEET MONITOR] Monitoring complete. Total events captured: 0
[ℹ️] No fleet events captured during monitoring period
```

## Advanced Options

### Longer Monitoring
```bash
python test_fleet_protection.py --mode monitor --duration 1800  # 30 minutes
```

### Multiple Probes
```bash
python test_fleet_protection.py --mode trigger-espionage --target 2:30:4 --probes 3
```

### Different Planet
```bash
python test_fleet_protection.py --mode both --coords 2:28:6 --target 2:28:7
```

### Disable HTML Capture (Faster)
```bash
python test_fleet_protection.py --mode monitor --no-html
```

## Integration with Main Bot

### Phase 1: Validate Detection
1. Use test script to confirm fleet detection works
2. Check that hostile missions are properly identified
3. Verify timing calculations are accurate

### Phase 2: Test with Main Bot
1. Enable fleet protection in main bot (still dry-run)
2. Trigger NPC espionage
3. Watch main bot logs for fleet protection activation
4. Verify dry-run simulation works correctly

### Phase 3: Live Testing
1. Disable dry-run mode
2. Test with minimal ships first
3. Monitor first live evacuation closely
4. Verify ships return correctly

## Troubleshooting

### NPC Doesn't Respond
- Try a different NPC planet
- Send more probes (2-3 instead of 1)
- Wait longer (up to 10 minutes)
- Some NPCs may not counter-espionage

### Detection Not Working
- Check console for fleet detection errors
- Review HTML snapshots in errors/ directory
- Verify selector classes (`.fleet-table-tr`, `.fleet-mission`)
- Check if mission type matches hostile keywords

### Script Errors
- Verify credentials in `.env` file
- Check internet connection
- Ensure auth.json exists from previous login
- Try running main bot first to establish session

## Safety Reminders

⚠️ **Always** start with monitor mode to check current state
⚠️ **Use nearby NPC planets** (same system preferred)
⚠️ **Start with 1 probe** (minimal trigger)
⚠️ **Keep monitoring duration reasonable** (5-10 minutes)
⚠️ **Review results before** testing with main bot
⚠️ **Never** test with real player attacks during development

## What This Validates

✅ Fleet detection logic works correctly
✅ Hostile mission identification is accurate
✅ Timing calculations are precise
✅ HTML parsing selectors are correct
✅ Integration with defense system works
✅ Discord notifications would fire properly
✅ Dry-run simulation behaves as expected

After successful testing with this script, you'll have confidence the fleet protection system will work correctly when real attacks occur.