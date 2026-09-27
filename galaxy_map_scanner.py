import json

MAP_FILE = "universe_map.json"

with open(MAP_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

g2_systems = data.get("galaxies", {}).get("2", {})

print("==================================================")
print("   3-Planet & 4-Planet Empty Systems (Galaxy 2)   ")
print("==================================================")
for sys_id, sys_data in sorted(g2_systems.items(), key=lambda x: int(x[0])):
    free = sys_data.get("free_slots", 0)
    if free in (3, 4):
        print(
            f" -> System 2:{int(sys_id):03d} | Free Slots: {free}/{sys_data.get('total_slots')}")

print("\n==================================================")
print("   2-4 Empty Slots + EXCLUSIVELY NPC Occupants    ")
print("==================================================")
for sys_id, sys_data in sorted(g2_systems.items(), key=lambda x: int(x[0])):
    planets = sys_data.get("planets", [])
    free = sum(1 for p in planets if p.get("status") == "empty")
    occupied = [p for p in planets if p.get("status") == "occupied"]

    if 2 <= free <= 4 and occupied:
        # Verify no human player is present in the system
        has_human = any(p.get("type") == "player" for p in occupied)
        if not has_human:
            npc_count = len(occupied)
            print(
                f" -> System 2:{int(sys_id):03d} | Free Slots: {free} | NPCs: {npc_count} (Safe Colony Cluster)")
