"""Ollama API client for LLM interactions."""

import httpx
from typing import Any


class OllamaClient:
    """HTTP client for Ollama API."""

    def __init__(self, base_url: str, model: str, timeout: float = 60.0):
        """Initialize the Ollama client.

        Args:
            base_url: Base URL of the Ollama server (e.g., http://localhost:11434)
            model: Model name to use for generation
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        context: dict[str, Any] | None = None,
        images: list[str] | None = None,
        model_override: str | None = None,
    ) -> str:
        """Generate a response from the LLM.

        Args:
            prompt: The user prompt to send
            system_prompt: Optional system prompt to set context
            context: Optional additional context (for future RAG integration)
            images: Optional list of base64 encoded images for vision models
            model_override: Optional model to use instead of default

        Returns:
            The generated text response
        """
        payload: dict[str, Any] = {
            "model": model_override or self.model,
            "prompt": prompt,
            "stream": False,
        }

        if system_prompt:
            payload["system"] = system_prompt

        if images:
            payload["images"] = images

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")

    async def health_check(self) -> bool:
        """Check if the Ollama server is accessible.

        Returns:
            True if server is healthy, False otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except Exception:
            return False
