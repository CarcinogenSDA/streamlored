"""Configuration management for StreamLored."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Twitch Configuration
    twitch_bot_nick: str
    twitch_oauth_token: str
    twitch_channel: str
    twitch_client_id: str = ""
    twitch_client_secret: str = ""
    twitch_bot_id: int = 0  # Bot's Twitch user ID
    twitch_poll_interval: int = 60  # seconds between game checks

    # Ollama Configuration
    ollama_host: str = "localhost"
    ollama_port: int = 11434
    ollama_model: str = "llama3.2"
    ollama_embed_model: str = "nomic-embed-text"

    # Bot Configuration
    bot_prefix: str = "!"

    # Knowledge Base Configuration
    kb_path: str = "data/knowledge_base.json"
    kb_enabled: bool = True

    # OBS WebSocket Configuration
    obs_host: str = "localhost"
    obs_port: int = 4455
    obs_password: str = ""
    obs_enabled: bool = False

    # Vision Model Configuration
    ollama_vision_model: str = "llava"

    # LiveSplit Configuration
    livesplit_enabled: bool = False
    livesplit_host: str = "localhost"
    livesplit_port: int = 16834

    # Run Mode
    run_mode: str = "bot"  # "bot", "local-chat", or "ingest"

    # Personality (for future tuning)
    personality_snark_level: int = 2  # 0-3 scale

    @property
    def ollama_base_url(self) -> str:
        """Get the full Ollama API base URL."""
        return f"http://{self.ollama_host}:{self.ollama_port}"


def get_settings() -> Settings:
    """Load and return application settings."""
    return Settings()
