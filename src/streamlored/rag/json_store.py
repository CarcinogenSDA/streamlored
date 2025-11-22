"""JSON-backed document store for RAG."""

import json
import logging
import math
import uuid
from pathlib import Path
from typing import Any

from streamlored.rag import DocumentStore
from streamlored.rag.ollama_embeddings import OllamaEmbeddingProvider

logger = logging.getLogger(__name__)


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Args:
        vec_a: First vector
        vec_b: Second vector

    Returns:
        Cosine similarity score between -1 and 1
    """
    if len(vec_a) != len(vec_b):
        raise ValueError("Vectors must have same length")

    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


class JsonDocumentStore(DocumentStore):
    """Document store that persists to a JSON file."""

    def __init__(self, kb_path: str, embedding_provider: OllamaEmbeddingProvider):
        """Initialize the JSON document store.

        Args:
            kb_path: Path to the knowledge base JSON file
            embedding_provider: Provider for generating embeddings
        """
        self.kb_path = Path(kb_path)
        self.embedding_provider = embedding_provider
        self.documents: list[dict[str, Any]] = []

        # Load existing data if file exists
        self._load()

    def _load(self) -> None:
        """Load documents from the JSON file."""
        if self.kb_path.exists():
            try:
                with open(self.kb_path, "r", encoding="utf-8") as f:
                    self.documents = json.load(f)
                logger.info(f"Loaded {len(self.documents)} documents from {self.kb_path}")
            except Exception as e:
                logger.error(f"Failed to load knowledge base: {e}")
                self.documents = []
        else:
            self.documents = []

    def _save(self) -> None:
        """Save documents to the JSON file."""
        # Ensure parent directory exists
        self.kb_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.kb_path, "w", encoding="utf-8") as f:
            json.dump(self.documents, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved {len(self.documents)} documents to {self.kb_path}")

    async def ingest_documents(self, documents: list[dict[str, Any]]) -> None:
        """Ingest documents into the store.

        Args:
            documents: List of documents with 'content' and optional 'metadata' keys
        """
        if not documents:
            return

        # Extract content for embedding
        contents = [doc.get("content", "") for doc in documents]

        # Generate embeddings
        logger.info(f"Generating embeddings for {len(documents)} documents...")
        embeddings = await self.embedding_provider.embed(contents)

        # Create document entries
        for doc, embedding in zip(documents, embeddings):
            entry = {
                "id": str(uuid.uuid4()),
                "content": doc.get("content", ""),
                "metadata": doc.get("metadata", {}),
                "embedding": embedding,
            }
            self.documents.append(entry)

        # Persist to disk
        self._save()
        logger.info(f"Ingested {len(documents)} documents")

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
        if not self.documents:
            return []

        # Embed the query
        query_embedding = await self.embedding_provider.embed_single(query)

        # Compute similarities
        scored_docs = []
        for doc in self.documents:
            score = cosine_similarity(query_embedding, doc["embedding"])
            scored_docs.append({
                "id": doc["id"],
                "content": doc["content"],
                "metadata": doc["metadata"],
                "score": score,
            })

        # Sort by score descending and return top_k
        scored_docs.sort(key=lambda x: x["score"], reverse=True)
        return scored_docs[:top_k]

    def document_count(self) -> int:
        """Return the number of documents in the store."""
        return len(self.documents)

    def clear(self) -> None:
        """Clear all documents from the store."""
        self.documents = []
        self._save()
