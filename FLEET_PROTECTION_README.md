# Fleet Protection Feature

## Overview
The Fleet Protection feature automatically evacuates your ships from planets under attack to safe destinations, ensuring your fleet survives hostile attacks while your resources are protected by the existing bunker system.

## How It Works

### 1. Attack Detection
- The bot continuously monitors all your planets for incoming hostile fleets
- When an attack is detected, the system evaluates whether to evacuate ships

### 2. Safe Destination Selection
- Automatically finds the closest safe planet (not under attack)
- Uses distance calculation to minimize travel time
- Ensures destination is within your empire (from fleet target list)

### 3. Fleet Evacuation
- Sends all stationed ships to the safe destination
- Uses "Station" mission (one-way trip) for safety
- Calculates speed to ensure arrival AFTER the attack
- Configurable safety buffer (default: 5 minutes after attack)

### 4. Automatic Return
- After attack clears and sufficient time passes, ships automatically return
- Uses "Transport" mission (round trip) for return
- Configurable return buffer (default: 10 minutes after arrival)

## Configuration

### Environment Variables
Add these to your `.env` file:

```bash
# Enable/disable fleet protection
FLEET_PROTECTION_ENABLED=true

# SAFETY: Dry-run mode (simulates without actual fleet movements)
FLEET_PROTECTION_DRY_RUN=true

# Minimum ships to trigger evacuation
FLEET_EVACUATION_MIN_SHIPS=1

# Safety buffer: seconds to arrive AFTER attack
FLEET_EVACUATION_SAFETY_BUFFER=300

# Return buffer: seconds to wait after arrival before return
FLEET_RETURN_BUFFER=600
```

### Safety Features

#### 1. Dry-Run Mode (DEFAULT: ENABLED)
- **CRITICAL**: Fleet protection starts in dry-run mode by default
- Simulates all fleet movements without actual game requests
- Logs exactly what would happen for verification
- Set `FLEET_PROTECTION_DRY_RUN=false` ONLY after thorough testing

#### 2. Rate Limiting & Human Behavior
- Uses existing `human_delay()` and `human_click()` functions
- Respects anti-detection measures from the main bot
- No rapid successive requests to game servers
- Follows existing timing patterns and safety measures

#### 3. State Persistence
- Tracks active evacuations in `fleet_evacuation_state.json`
- Prevents duplicate evacuations for same planet
- Survives bot restarts without losing evacuation state

#### 4. Intelligent Destination Selection
- Only uses planets from your own empire (target list)
- Never sends to unknown or hostile destinations
- Respects current attack status of all planets

## Testing Procedure

### Phase 1: Validate Detection with Test Script (RECOMMENDED FIRST)
Use the dedicated testing script to validate fleet detection works:

```bash
# Option 1: Monitor only (safest)
python test_fleet_protection.py --mode monitor --duration 300

# Option 2: Trigger NPC espionage response (for realistic testing)
python test_fleet_protection.py --mode both --target 2:30:4 --duration 600
```

See `TESTING_GUIDE.md` for detailed testing instructions using NPC espionage responses.

### Phase 2: Dry-Run Testing with Main Bot
1. Keep `FLEET_PROTECTION_DRY_RUN=true` (default)
2. Run the bot normally
3. Monitor logs for `[DRY-RUN 🛡️]` messages
4. Verify destination selection logic
5. Check timing calculations are reasonable
6. Ensure no actual game requests are made

### Phase 3: Manual Testing
1. Disable dry-run: `FLEET_PROTECTION_DRY_RUN=false`
2. Have only 1-2 ships on a test planet
3. Use test script to trigger NPC espionage response
4. Monitor Discord alerts and bot logs
5. Verify ships evacuate to correct destination
6. Verify ships return after attack clears

### Phase 4: Production Deployment
1. Only after successful manual testing
2. Set appropriate `FLEET_EVACUATION_MIN_SHIPS` threshold
3. Monitor first few evacuations closely
4. Keep dry-run available for troubleshooting

## Integration with Existing Systems

### Resource Protection (shipyard.py)
- **Complementary**: Fleet protection works alongside resource bunkering
- **Priority**: Resource protection activates first (faster response)
- **Coordination**: Both systems use same attack detection

### Defense System (defense.py)
- **Shared Detection**: Both use `check_incoming_fleets()`
- **Coordinated Timing**: Fleet evacuation considers attack ETA
- **Discord Alerts**: Both send notifications to same channels

### Build Queue (planner.py)
- **Independent**: Fleet protection doesn't interfere with construction
- **Resource Awareness**: Respects resource needs for construction
- **Priority**: Construction continues during evacuation

## Discord Notifications

### Evacuation Alert
```
🚀 Fleet Evacuation: [2:30:3]
Ships evacuated to safe destination due to incoming attack (ETA: 180s)
Travel Time: 420s
Destination: Safe Planet
```

### Return Alert
```
🏠 Fleet Returned: [2:30:3]
Evacuated ships have returned to home planet after attack cleared
```

## Troubleshooting

### Ships Not Evacuating
- Check `FLEET_EVACUATION_MIN_SHIPS` threshold
- Verify fleet protection is enabled
- Check if evacuation already in progress (state file)
- Ensure destination planets are available

### Ships Not Returning
- Check `FLEET_RETURN_BUFFER` setting
- Verify source planet is no longer under attack
- Check if destination is under attack
- Review evacuation state file

### Dry-Run Still Active
- Verify `FLEET_PROTECTION_DRY_RUN=false` in `.env`
- Restart bot after changing environment variables
- Check logs for dry-run confirmation message

## Safety Reminders

⚠️ **ALWAYS** test in dry-run mode first
⚠️ **NEVER** deploy to production without manual testing
⚠️ **MONITOR** first few evacuations closely
⚠️ **KEEP** dry-run mode available for troubleshooting
⚠️ **RESPECT** game server rate limits and anti-detection

## Future Enhancements

- Configurable ship type filtering (evacuate only combat ships)
- Multiple destination options (not just closest)
- Fleet composition-based evacuation logic
- Integration with galaxy scanner for strategic destination selection
- Manual evacuation commands via Discord
- Fleet status monitoring dashboard