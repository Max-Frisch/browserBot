import os
import json
import time
import asyncio
import threading
from typing import Optional, Callable
import discord
from discord.ext import commands

from config import (
    DISCORD_BOT_TOKEN,
    DISCORD_ADMIN_USER_ID,
    DISCORD_CHANNEL_FLEET_ALERTS,
    DISCORD_CHANNEL_BOT_LOGS,
    DISCORD_CHANNEL_COMMANDS,
    DISCORD_CHANNEL_UNIVERSE_MAPPING,
    BUILD_QUEUE_FILE,
)

# Global pause flag accessible by both Playwright and Discord
BOT_PAUSED = False


class DiscordManager:
    """
    Manages Discord bot communication, notifications, and remote commands.
    Runs asynchronously on a background daemon thread to coexist with synchronous Playwright.
    """

    def __init__(self, telemetry_getter: Optional[Callable[[], dict]] = None, snapshot_callback: Optional[Callable[[], Optional[str]]] = None):
        self.telemetry_getter = telemetry_getter
        self.snapshot_callback = snapshot_callback

        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None
        self.ready_event = threading.Event()

        intents = discord.Intents.default()
        intents.message_content = True
        self.bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

        self._setup_events_and_commands()

    def _setup_events_and_commands(self):
        @self.bot.event
        async def on_ready():
            print(f"[Discord] Logged in as {self.bot.user.name} ({self.bot.user.id})")
            self.ready_event.set()
            await self.send_bot_log(
                title="🟢 GWBot Online",
                description="GigraWars remote management engine connected and operational.",
                color=0x2ECC71,
            )

        def is_admin(ctx):
            if not DISCORD_ADMIN_USER_ID:
                return True
            return ctx.author.id == DISCORD_ADMIN_USER_ID

        @self.bot.command(name="help")
        async def help_cmd(ctx):
            embed = discord.Embed(
                title="🤖 GWBot Remote Control - Help",
                description="Available management commands for your GigraWars empire:",
                color=0x3498DB,
            )
            embed.add_field(name="!status", value="Displays live resources and queues from `/app/empire`", inline=False)
            embed.add_field(name="!queue", value="Shows the active `build_queue.json`", inline=False)
            embed.add_field(name="!add <coords> <building> <level>", value="Queue a building (e.g. `!add 2:109:1 Iron Mine 18`)", inline=False)
            embed.add_field(name="!addship <coords> <ship> <amount>", value="Queue ships (e.g. `!addship 3:7:1 Jackal 10`)", inline=False)
            embed.add_field(name="!remove <coords> <name>", value="Removes a queued goal", inline=False)
            embed.add_field(name="!snapshot", value="Captures and uploads live browser screenshot", inline=False)
            embed.add_field(name="!pause / !resume", value="Temporarily pauses or resumes bot automation", inline=False)
            await ctx.send(embed=embed)

        @self.bot.command(name="status")
        async def status_cmd(ctx):
            if not is_admin(ctx):
                await ctx.send("⛔ Unauthorized user.")
                return

            if not self.telemetry_getter:
                await ctx.send("⚠️ Telemetry service is currently initializing...")
                return

            await ctx.send("🛰️ Fetching live empire telemetry...")
            try:
                data = self.telemetry_getter()
                planets = data.get("planets", [])
                resources = data.get("resources", {})
                b_queues = data.get("building_queues", {})
                s_queues = data.get("ship_queues", {})

                embed = discord.Embed(
                    title="🌌 Empire Overview Status",
                    description=f"Active Planets: **{len(planets)}** | Mode: **{'⏸️ PAUSED' if BOT_PAUSED else '▶️ RUNNING'}**",
                    color=0x9B59B6,
                )

                for p in planets:
                    p_res = resources.get(p, {})
                    res_line = f"⛏️ Fe: `{p_res.get('iron', 0):,}` | 💎 Lu: `{p_res.get('lutinum', 0):,}`\n💧 H2O: `{p_res.get('water', 0):,}` | ⚡ H2: `{p_res.get('hydrogen', 0):,}`"

                    queue_parts = []
                    if p in b_queues:
                        queue_parts.append(f"🏗️ {b_queues[p]['name']} ({b_queues[p]['remaining_seconds']}s)")
                    if p in s_queues:
                        queue_parts.append(f"🚀 {s_queues[p].get('detail', 'Shipyard')} ({s_queues[p]['remaining_seconds']}s)")

                    queue_line = " | ".join(queue_parts) if queue_parts else "Idle"
                    embed.add_field(name=f"🪐 Planet [{p}]", value=f"{res_line}\n*Queue:* {queue_line}", inline=False)

                await ctx.send(embed=embed)
            except Exception as exc:
                await ctx.send(f"❌ Error fetching status: `{exc}`")

        @self.bot.command(name="queue")
        async def queue_cmd(ctx):
            if not is_admin(ctx):
                return
            try:
                with open(BUILD_QUEUE_FILE, "r", encoding="utf-8") as f:
                    q_data = json.load(f)

                embed = discord.Embed(
                    title="📋 Current Build Queue",
                    description=f"Capital: **{q_data.get('main_planet', '3:7:1')}**",
                    color=0x3498DB,
                )

                r_goals = q_data.get("research_goals", [])
                if r_goals:
                    r_text = "\n".join([f"• {g.get('name')} (Target: Lvl {g.get('level')})" for g in r_goals])
                    embed.add_field(name="🔬 Capital Research", value=r_text, inline=False)

                for p, goals in q_data.get("planets", {}).items():
                    if goals:
                        p_lines = []
                        for g in goals:
                            if g.get("type") == "building":
                                p_lines.append(f"• 🏗️ {g.get('name')} -> Lvl {g.get('level')}")
                            elif g.get("type") == "ship":
                                p_lines.append(f"• 🚀 {g.get('name')} x{g.get('amount')}")
                            elif g.get("type") == "defense":
                                p_lines.append(f"• 🛡️ {g.get('name')} x{g.get('amount')}")
                        embed.add_field(name=f"🪐 [{p}]", value="\n".join(p_lines), inline=False)

                await ctx.send(embed=embed)
            except Exception as exc:
                await ctx.send(f"❌ Error reading queue: `{exc}`")

        @self.bot.command(name="add")
        async def add_goal_cmd(ctx, coords: str, *args):
            """Usage: !add 2:109:1 Iron Mine 18"""
            if not is_admin(ctx):
                return
            if len(args) < 2:
                await ctx.send("Usage: `!add <coords> <Building Name> <Level>`\nExample: `!add 2:109:1 Iron Mine 18`")
                return

            try:
                target_lvl = int(args[-1])
                building_name = " ".join(args[:-1])

                with open(BUILD_QUEUE_FILE, "r", encoding="utf-8") as f:
                    q_data = json.load(f)

                if "planets" not in q_data:
                    q_data["planets"] = {}
                if coords not in q_data["planets"]:
                    q_data["planets"][coords] = []

                new_goal = {
                    "type": "building",
                    "name": building_name,
                    "level": target_lvl
                }
                q_data["planets"][coords].append(new_goal)

                with open(BUILD_QUEUE_FILE, "w", encoding="utf-8") as f:
                    json.dump(q_data, f, indent=2)

                await ctx.send(f"✅ Added to queue: **{building_name} Lvl {target_lvl}** on planet **[{coords}]**.")
            except Exception as exc:
                await ctx.send(f"❌ Error adding goal: `{exc}`")

        @self.bot.command(name="addship")
        async def add_ship_cmd(ctx, coords: str, *args):
            """Usage: !addship 3:7:1 Jackal 10"""
            if not is_admin(ctx):
                return
            if len(args) < 2:
                await ctx.send("Usage: `!addship <coords> <Ship Name> <Amount>`\nExample: `!addship 3:7:1 Jackal 10`")
                return

            try:
                amount = int(args[-1])
                ship_name = " ".join(args[:-1])

                with open(BUILD_QUEUE_FILE, "r", encoding="utf-8") as f:
                    q_data = json.load(f)

                if "planets" not in q_data:
                    q_data["planets"] = {}
                if coords not in q_data["planets"]:
                    q_data["planets"][coords] = []

                new_goal = {
                    "type": "ship",
                    "name": ship_name,
                    "amount": amount
                }
                q_data["planets"][coords].append(new_goal)

                with open(BUILD_QUEUE_FILE, "w", encoding="utf-8") as f:
                    json.dump(q_data, f, indent=2)

                await ctx.send(f"✅ Added to queue: **{ship_name} x{amount}** on planet **[{coords}]**.")
            except Exception as exc:
                await ctx.send(f"❌ Error adding ship goal: `{exc}`")

        @self.bot.command(name="remove")
        async def remove_goal_cmd(ctx, coords: str, *, name: str):
            """Usage: !remove 2:109:1 Iron Mine"""
            if not is_admin(ctx):
                return
            try:
                with open(BUILD_QUEUE_FILE, "r", encoding="utf-8") as f:
                    q_data = json.load(f)

                goals = q_data.get("planets", {}).get(coords, [])
                initial_count = len(goals)
                q_data["planets"][coords] = [g for g in goals if g.get("name", "").lower() != name.strip().lower()]

                if len(q_data["planets"][coords]) < initial_count:
                    with open(BUILD_QUEUE_FILE, "w", encoding="utf-8") as f:
                        json.dump(q_data, f, indent=2)
                    await ctx.send(f"🗑️ Removed **{name}** from planet **[{coords}]**.")
                else:
                    await ctx.send(f"⚠️ Goal '{name}' not found on planet [{coords}].")
            except Exception as exc:
                await ctx.send(f"❌ Error removing goal: `{exc}`")

        @self.bot.command(name="snapshot")
        async def snapshot_cmd(ctx):
            if not is_admin(ctx):
                return
            if not self.snapshot_callback:
                await ctx.send("⚠️ Snapshot callback not registered.")
                return

            await ctx.send("📸 Capturing browser snapshot...")
            try:
                img_path = self.snapshot_callback()
                if img_path and os.path.exists(img_path):
                    file = discord.File(img_path, filename="snapshot.png")
                    await ctx.send(content="📸 **Live Browser State:**", file=file)
                else:
                    await ctx.send("❌ Failed to capture screenshot.")
            except Exception as exc:
                await ctx.send(f"❌ Snapshot error: `{exc}`")

        @self.bot.command(name="pause")
        async def pause_cmd(ctx):
            global BOT_PAUSED
            if not is_admin(ctx):
                return
            BOT_PAUSED = True
            await ctx.send("⏸️ **Bot automation PAUSED.** Play manually without interference. Use `!resume` when ready.")

        @self.bot.command(name="resume")
        async def resume_cmd(ctx):
            global BOT_PAUSED
            if not is_admin(ctx):
                return
            BOT_PAUSED = False
            await ctx.send("▶️ **Bot automation RESUMED.** Normal cycles and queue processing active.")

    def start(self):
        """Starts the Discord bot event loop in a dedicated background thread."""
        if not DISCORD_BOT_TOKEN:
            print("[Discord] DISCORD_BOT_TOKEN not configured. Discord bot disabled.")
            return

        def run():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.bot.start(DISCORD_BOT_TOKEN))

        self.thread = threading.Thread(target=run, daemon=True, name="DiscordBotThread")
        self.thread.start()
        print("[Discord] Background bot thread launched.")

    # ---------------- Thread-Safe Outgoing Notifications ----------------

    def send_fleet_alert(self, title: str, description: str, fields: Optional[dict] = None, urgent: bool = True):
        """Dispatches an urgent attack alert to #fleet-alerts and pings admin."""
        if not self.loop or not self.bot.is_ready() or not DISCORD_CHANNEL_FLEET_ALERTS:
            return

        async def _coro():
            channel = self.bot.get_channel(DISCORD_CHANNEL_FLEET_ALERTS)
            if not channel:
                return

            mention = f"<@{DISCORD_ADMIN_USER_ID}> " if (urgent and DISCORD_ADMIN_USER_ID) else ""
            embed = discord.Embed(
                title=f"🚨 {title}",
                description=description,
                color=0xE74C3C,  # Bright Red
                timestamp=discord.utils.utcnow()
            )
            if fields:
                for k, v in fields.items():
                    embed.add_field(name=k, value=str(v), inline=True)

            await channel.send(content=f"{mention}**CRITICAL FLEET ALERT**" if mention else None, embed=embed)

        asyncio.run_coroutine_threadsafe(_coro(), self.loop)

    def send_bot_log(self, title: str, description: str, color: int = 0x3498DB, fields: Optional[dict] = None):
        """Dispatches heartbeat and build logs to #bot-logs."""
        if not self.loop or not self.bot.is_ready() or not DISCORD_CHANNEL_BOT_LOGS:
            return

        async def _coro():
            channel = self.bot.get_channel(DISCORD_CHANNEL_BOT_LOGS)
            if not channel:
                return

            embed = discord.Embed(
                title=title,
                description=description,
                color=color,
                timestamp=discord.utils.utcnow()
            )
            if fields:
                for k, v in fields.items():
                    embed.add_field(name=k, value=str(v), inline=True)

            await channel.send(embed=embed)

        asyncio.run_coroutine_threadsafe(_coro(), self.loop)

    def send_universe_report(self, title: str, description: str, file_path: Optional[str] = None):
        """Dispatches universe scanner reports to #universe-mapping."""
        if not self.loop or not self.bot.is_ready() or not DISCORD_CHANNEL_UNIVERSE_MAPPING:
            return

        async def _coro():
            channel = self.bot.get_channel(DISCORD_CHANNEL_UNIVERSE_MAPPING)
            if not channel:
                return

            embed = discord.Embed(
                title=title,
                description=description,
                color=0x1ABC9C,
                timestamp=discord.utils.utcnow()
            )
            file = discord.File(file_path) if file_path and os.path.exists(file_path) else None
            await channel.send(embed=embed, file=file)

        asyncio.run_coroutine_threadsafe(_coro(), self.loop)


if __name__ == "__main__":
    print("[+] Launching DiscordManager in standalone mode...")
    mgr = DiscordManager()
    mgr.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping DiscordManager...")
