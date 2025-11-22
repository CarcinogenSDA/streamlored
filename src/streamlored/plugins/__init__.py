"""Plugin system for StreamLored."""

from abc import ABC, abstractmethod
from typing import Any


class BasePlugin(ABC):
    """Base class for all StreamLored plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the plugin name."""
        pass

    @abstractmethod
    async def setup(self, bot: Any) -> None:
        """Initialize the plugin with the bot instance.

        Args:
            bot: The TwitchBot instance
        """
        pass

    @abstractmethod
    async def teardown(self) -> None:
        """Clean up plugin resources."""
        pass


__all__ = ["BasePlugin"]
