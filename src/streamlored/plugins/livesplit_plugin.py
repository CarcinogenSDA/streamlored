"""LiveSplit integration plugin for speedrun timer data."""

import asyncio
import logging
from typing import Any

from twitchio.ext import commands

from streamlored.plugins import BasePlugin

logger = logging.getLogger(__name__)


class LiveSplitPlugin(BasePlugin):
    """Plugin for LiveSplit Server TCP integration."""

    def __init__(self, host: str = "localhost", port: int = 16834) -> None:
        """Initialize the LiveSplit plugin.

        Args:
            host: LiveSplit Server host
            port: LiveSplit Server port (default 16834)
        """
        self.host = host
        self.port = port
        self.bot = None
        self._reader = None
        self._writer = None
        self._connected = False
        # Cached state for context
        self._cached_time: str | None = None
        self._cached_phase: str | None = None
        self._cached_delta: str | None = None
        self._cached_split: str | None = None

    @property
    def name(self) -> str:
        return "livesplit"

    async def setup(self, bot: Any) -> None:
        """Initialize the plugin and connect to LiveSplit.

        Args:
            bot: The TwitchBot instance
        """
        self.bot = bot

        # Register commands
        bot.add_command(commands.Command(name="time", func=self.cmd_time))
        bot.add_command(commands.Command(name="timer", func=self.cmd_time))
        bot.add_command(commands.Command(name="pb", func=self.cmd_pb))
        bot.add_command(commands.Command(name="splits", func=self.cmd_splits))
        bot.add_command(commands.Command(name="pace", func=self.cmd_pace))

        # Try to connect
        if await self.connect():
            logger.info(f"LiveSplit plugin connected to {self.host}:{self.port}")
        else:
            logger.warning(f"LiveSplit plugin failed to connect to {self.host}:{self.port}")

    async def teardown(self) -> None:
        """Clean up plugin resources."""
        await self.disconnect()
        logger.info("LiveSplit plugin shut down")

    async def connect(self) -> bool:
        """Connect to LiveSplit Server.

        Returns:
            True if connected successfully
        """
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=5.0
            )
            self._connected = True
            return True
        except Exception as e:
            logger.debug(f"LiveSplit connection failed: {e}")
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from LiveSplit Server."""
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
            self._writer = None
            self._reader = None
        self._connected = False

    async def _send_command(self, command: str) -> str | None:
        """Send a command to LiveSplit Server and get response.

        Args:
            command: The command to send (e.g., "getcurrenttime")

        Returns:
            Response string, or None on failure
        """
        if not self._connected:
            # Try to reconnect
            if not await self.connect():
                return None

        try:
            # LiveSplit Server uses newline-terminated commands
            self._writer.write(f"{command}\r\n".encode())
            await self._writer.drain()

            # Read response (terminated by newline)
            response = await asyncio.wait_for(
                self._reader.readline(),
                timeout=5.0
            )
            return response.decode().strip()
        except Exception as e:
            logger.error(f"LiveSplit command failed: {e}")
            self._connected = False
            return None

    def _format_time(self, time_str: str) -> str:
        """Format a time string for display.

        Args:
            time_str: Time in format like "1:23:45.67" or "12:34.56"

        Returns:
            Formatted time string
        """
        if not time_str or time_str == "-":
            return "-"

        # Clean up the time string
        time_str = time_str.strip()

        # If it has milliseconds, truncate to 2 decimal places
        if "." in time_str:
            parts = time_str.rsplit(".", 1)
            if len(parts) == 2:
                time_str = f"{parts[0]}.{parts[1][:2]}"

        return time_str

    async def get_current_time(self) -> str | None:
        """Get current timer value.

        Returns:
            Current time string, or None
        """
        return await self._send_command("getcurrenttime")

    async def get_final_time(self) -> str | None:
        """Get final time (PB) for current category.

        Returns:
            Final time string, or None
        """
        return await self._send_command("getfinaltime")

    async def get_best_possible_time(self) -> str | None:
        """Get best possible time based on best segments.

        Returns:
            Best possible time string, or None
        """
        return await self._send_command("getbestpossibletime")

    async def get_comparison_split_time(self) -> str | None:
        """Get comparison split time for current split.

        Returns:
            Comparison time string, or None
        """
        return await self._send_command("getcomparisonsplittime")

    async def get_current_split_name(self) -> str | None:
        """Get name of current split.

        Returns:
            Split name string, or None
        """
        return await self._send_command("getcurrentsplitname")

    async def get_previous_split_name(self) -> str | None:
        """Get name of previous split.

        Returns:
            Split name string, or None
        """
        return await self._send_command("getprevioussplitname")

    async def get_delta(self) -> str | None:
        """Get current delta (ahead/behind).

        Returns:
            Delta string like "+1:23.45" or "-0:30.12", or None
        """
        return await self._send_command("getdelta")

    async def get_timer_phase(self) -> str | None:
        """Get timer phase (NotRunning, Running, Ended, Paused).

        Returns:
            Phase string, or None
        """
        return await self._send_command("getcurrenttimerphase")

    async def cmd_time(self, ctx: commands.Context) -> None:
        """Show current timer value with split info.

        Args:
            ctx: Command context
        """
        time = await self.get_current_time()
        if time:
            phase = await self.get_timer_phase()
            if phase == "NotRunning":
                await ctx.send(f"@{ctx.author.name} Timer not running")
            elif phase == "Ended":
                await ctx.send(f"@{ctx.author.name} Final time: {self._format_time(time)}")
            else:
                # Get additional split info
                split_name = await self.get_current_split_name()
                delta = await self.get_delta()

                # Build response with split context
                parts = [f"Current time: {self._format_time(time)}"]

                if split_name:
                    parts.append(f"on '{split_name}'")

                if delta and delta != "-":
                    if delta.startswith("-"):
                        parts.append(f"({delta} ahead)")
                    else:
                        parts.append(f"({delta.lstrip('+')} behind)")

                await ctx.send(f"@{ctx.author.name} {' '.join(parts)}")
        else:
            await ctx.send(f"@{ctx.author.name} LiveSplit not connected")

    async def cmd_pb(self, ctx: commands.Context) -> None:
        """Show personal best time.

        Args:
            ctx: Command context
        """
        pb = await self.get_final_time()
        if pb and pb != "-":
            await ctx.send(f"@{ctx.author.name} PB: {self._format_time(pb)}")
        elif pb == "-":
            await ctx.send(f"@{ctx.author.name} No PB set for this category")
        else:
            await ctx.send(f"@{ctx.author.name} LiveSplit not connected")

    async def cmd_splits(self, ctx: commands.Context) -> None:
        """Show current split info.

        Args:
            ctx: Command context
        """
        split_name = await self.get_current_split_name()
        if split_name:
            delta = await self.get_delta()
            if delta and delta != "-":
                # Format delta nicely
                if delta.startswith("-"):
                    status = f"ahead by {delta[1:]}"
                else:
                    status = f"behind by {delta.lstrip('+')}"
                await ctx.send(f"@{ctx.author.name} Current split: {split_name} ({status})")
            else:
                await ctx.send(f"@{ctx.author.name} Current split: {split_name}")
        else:
            phase = await self.get_timer_phase()
            if phase == "NotRunning":
                await ctx.send(f"@{ctx.author.name} Timer not running")
            else:
                await ctx.send(f"@{ctx.author.name} LiveSplit not connected")

    async def cmd_pace(self, ctx: commands.Context) -> None:
        """Show current pace vs PB.

        Args:
            ctx: Command context
        """
        delta = await self.get_delta()
        bpt = await self.get_best_possible_time()

        if delta and delta != "-":
            if delta.startswith("-"):
                pace_msg = f"Currently {delta} ahead"
            else:
                pace_msg = f"Currently {delta.lstrip('+')} behind"

            if bpt and bpt != "-":
                pace_msg += f" | Best possible: {self._format_time(bpt)}"

            await ctx.send(f"@{ctx.author.name} {pace_msg}")
        else:
            phase = await self.get_timer_phase()
            if phase == "NotRunning":
                await ctx.send(f"@{ctx.author.name} Timer not running")
            elif phase == "Ended":
                time = await self.get_current_time()
                await ctx.send(f"@{ctx.author.name} Run finished: {self._format_time(time)}")
            else:
                await ctx.send(f"@{ctx.author.name} No pace data available")

    async def update_cached_state(self) -> None:
        """Update cached timer state for context."""
        self._cached_phase = await self.get_timer_phase()
        self._cached_time = await self.get_current_time()
        self._cached_delta = await self.get_delta()
        self._cached_split = await self.get_current_split_name()

    async def get_context_string(self) -> str:
        """Get timer context for LLM prompts.

        Returns:
            Context string describing current timer state
        """
        # Update cache
        await self.update_cached_state()

        if not self._cached_phase or self._cached_phase == "NotRunning":
            return ""

        parts = []

        if self._cached_phase == "Ended":
            if self._cached_time:
                parts.append(f"Run finished with time {self._format_time(self._cached_time)}")
        else:
            # Running or paused
            if self._cached_time:
                parts.append(f"Current run time: {self._format_time(self._cached_time)}")

            if self._cached_split:
                parts.append(f"on split '{self._cached_split}'")

            if self._cached_delta and self._cached_delta != "-":
                if self._cached_delta.startswith("-"):
                    parts.append(f"({self._cached_delta} ahead of PB)")
                else:
                    parts.append(f"({self._cached_delta.lstrip('+')} behind PB)")

        if not parts:
            return ""

        return "Speedrun timer: " + " ".join(parts) + "."
