"""Twitch Helix API client for stream information."""

import logging
from dataclasses import dataclass

import httpx


@dataclass
class GameContext:
    """Current game/stream context information."""

    game_name: str | None = None
    game_id: str | None = None
    title: str | None = None
    viewer_count: int | None = None
    tags: list[str] | None = None

    def to_context_string(self) -> str:
        """Build a context string for LLM prompts."""
        parts = []
        if self.game_name:
            parts.append(f"Current game: {self.game_name}")
        if self.title:
            parts.append(f"Stream title: {self.title}")
        if self.tags:
            parts.append(f"Tags: {', '.join(self.tags)}")
        if parts:
            return ". ".join(parts) + "."
        return ""


class TwitchAPIClient:
    """Client for Twitch Helix API with app access token management."""

    def __init__(self, client_id: str, client_secret: str) -> None:
        """Initialize the Twitch API client.

        Args:
            client_id: Twitch application client ID
            client_secret: Twitch application client secret
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token: str | None = None
        self._logger = logging.getLogger(__name__)

    async def _get_access_token(self) -> str:
        """Get or refresh the app access token.

        Returns:
            Valid access token string

        Raises:
            httpx.HTTPError: If token request fails
        """
        if self._access_token:
            return self._access_token

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://id.twitch.tv/oauth2/token",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials",
                },
            )
            response.raise_for_status()
            data = response.json()
            self._access_token = data["access_token"]
            self._logger.debug("Obtained Twitch app access token")
            return self._access_token

    async def _make_request(self, endpoint: str, params: dict | None = None) -> dict:
        """Make an authenticated request to the Helix API.

        Args:
            endpoint: API endpoint path
            params: Optional query parameters

        Returns:
            JSON response data

        Raises:
            httpx.HTTPError: If request fails
        """
        token = await self._get_access_token()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.twitch.tv/helix/{endpoint}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Client-Id": self.client_id,
                },
                params=params,
            )

            # If unauthorized, clear token and retry once
            if response.status_code == 401:
                self._access_token = None
                token = await self._get_access_token()
                response = await client.get(
                    f"https://api.twitch.tv/helix/{endpoint}",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Client-Id": self.client_id,
                    },
                    params=params,
                )

            response.raise_for_status()
            return response.json()

    async def get_stream_info(self, channel_login: str) -> GameContext | None:
        """Get current stream information for a channel.

        Args:
            channel_login: Channel username (login name)

        Returns:
            GameContext with stream info, or None if offline
        """
        try:
            data = await self._make_request(
                "streams",
                params={"user_login": channel_login},
            )

            streams = data.get("data", [])
            if not streams:
                return None

            stream = streams[0]
            return GameContext(
                game_name=stream.get("game_name"),
                game_id=stream.get("game_id"),
                title=stream.get("title"),
                viewer_count=stream.get("viewer_count"),
                tags=stream.get("tags"),
            )

        except httpx.HTTPError as e:
            self._logger.error(f"Failed to get stream info: {e}")
            return None
        except Exception as e:
            self._logger.error(f"Unexpected error getting stream info: {e}")
            return None
