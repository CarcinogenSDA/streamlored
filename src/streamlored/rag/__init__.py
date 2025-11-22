"""RAG (Retrieval-Augmented Generation) module stubs.

This module will be implemented in a future phase to provide:
- Document ingestion and chunking
- Embedding generation
- Vector store management
- Knowledge base querying
"""

from abc import ABC, abstractmethod
from typing import Any


class DocumentStore(ABC):
    """Abstract base class for document storage."""

    @abstractmethod
    async def ingest_documents(self, documents: list[dict[str, Any]]) -> None:
        """Ingest documents into the store.

        Args:
            documents: List of documents with 'content' and 'metadata' keys
        """
        pass

    @abstractmethod
    async def query_knowledge_base(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Query the knowledge base for relevant documents.

        Args:
            query: The search query
            top_k: Number of results to return

        Returns:
            List of relevant document chunks with scores
        """
        pass


class EmbeddingProvider(ABC):
    """Abstract base class for embedding generation."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for the given texts.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors
        """
        pass


# Placeholder implementations for future development
class PlaceholderDocumentStore(DocumentStore):
    """Placeholder document store - to be replaced with actual implementation."""

    async def ingest_documents(self, documents: list[dict[str, Any]]) -> None:
        raise NotImplementedError("RAG document store not yet implemented")

    async def query_knowledge_base(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError("RAG query not yet implemented")


from streamlored.rag.ollama_embeddings import OllamaEmbeddingProvider
from streamlored.rag.json_store import JsonDocumentStore

__all__ = [
    "DocumentStore",
    "EmbeddingProvider",
    "PlaceholderDocumentStore",
    "OllamaEmbeddingProvider",
    "JsonDocumentStore",
]
