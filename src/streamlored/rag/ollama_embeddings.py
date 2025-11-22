"""Ollama-based embedding provider for RAG."""

import httpx

from streamlored.rag import EmbeddingProvider


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Embedding provider using Ollama's embedding API."""

    def __init__(self, base_url: str, model: str, timeout: float = 60.0):
        """Initialize the Ollama embedding provider.

        Args:
            base_url: Base URL of the Ollama server
            model: Model name to use for embeddings (e.g., nomic-embed-text)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for the given texts.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors
        """
        embeddings = []

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for text in texts:
                response = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={
                        "model": self.model,
                        "prompt": text,
                    },
                )
                response.raise_for_status()
                data = response.json()
                embeddings.append(data["embedding"])

        return embeddings

    async def embed_single(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Text string to embed

        Returns:
            Embedding vector
        """
        result = await self.embed([text])
        return result[0]
