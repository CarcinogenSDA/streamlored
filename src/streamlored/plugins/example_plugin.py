"""Example plugin demonstrating the plugin interface."""

import logging
from typing import Any

from streamlored.plugins import BasePlugin

logger = logging.getLogger(__name__)


class ExamplePlugin(BasePlugin):
    """A simple example plugin that logs messages."""

    @property
    def name(self) -> str:
        return "example"

    async def setup(self, bot: Any) -> None:
        """Initialize the plugin.

        Args:
            bot: The TwitchBot instance
        """
        self.bot = bot
        logger.info(f"ExamplePlugin '{self.name}' initialized")

    async def teardown(self) -> None:
        """Clean up plugin resources."""
        logger.info(f"ExamplePlugin '{self.name}' shutting down")
