"""Markdown-aware document chunking for RAG ingestion."""

import re
from typing import Any


def chunk_markdown(
    content: str,
    source: str,
    max_chars: int = 1000,
) -> list[dict[str, Any]]:
    """Split markdown content into smaller, semantically coherent chunks.

    Splits by markdown headers first, then by paragraphs if sections are too long.

    Args:
        content: Full markdown text
        source: File path or logical name for metadata
        max_chars: Soft character limit per chunk

    Returns:
        List of document dicts with 'content' and 'metadata' keys
    """
    # Split content into sections based on markdown headers
    sections = _split_by_headers(content)

    chunks = []
    chunk_index = 0

    for section_title, section_content in sections:
        # Get the full section text (title + content)
        if section_title:
            full_section = f"{section_title}\n{section_content}".strip()
        else:
            full_section = section_content.strip()

        if not full_section:
            continue

        # If section is small enough, keep it as one chunk
        if len(full_section) <= max_chars:
            chunks.append({
                "content": full_section,
                "metadata": {
                    "source": source,
                    "section_title": _extract_title_text(section_title),
                    "chunk_index": chunk_index,
                },
            })
            chunk_index += 1
        else:
            # Split large sections by paragraphs
            section_chunks = _split_by_paragraphs(
                full_section,
                section_title,
                max_chars,
            )
            for chunk_content in section_chunks:
                chunks.append({
                    "content": chunk_content,
                    "metadata": {
                        "source": source,
                        "section_title": _extract_title_text(section_title),
                        "chunk_index": chunk_index,
                    },
                })
                chunk_index += 1

    # Add total_chunks to all metadata
    total_chunks = len(chunks)
    for chunk in chunks:
        chunk["metadata"]["total_chunks"] = total_chunks

    return chunks


def _split_by_headers(content: str) -> list[tuple[str, str]]:
    """Split markdown content by headers (# ## ###).

    Args:
        content: Full markdown text

    Returns:
        List of (header_line, section_content) tuples.
        First section may have empty header if content starts without one.
    """
    # Pattern matches lines starting with 1-6 # characters followed by space
    header_pattern = re.compile(r'^(#{1,6}\s+.+)$', re.MULTILINE)

    sections = []
    last_end = 0
    last_header = ""

    for match in header_pattern.finditer(content):
        # Get content before this header
        if match.start() > last_end:
            section_content = content[last_end:match.start()].strip()
            if section_content or last_header:
                sections.append((last_header, section_content))

        last_header = match.group(1)
        last_end = match.end()

    # Get remaining content after last header
    remaining = content[last_end:].strip()
    if remaining or last_header:
        sections.append((last_header, remaining))

    # Handle case where content has no headers
    if not sections and content.strip():
        sections.append(("", content.strip()))

    return sections


def _split_by_paragraphs(
    content: str,
    section_title: str,
    max_chars: int,
) -> list[str]:
    """Split content by paragraphs to stay under max_chars.

    Args:
        content: Section content (may include title)
        section_title: Original section title for context
        max_chars: Soft character limit per chunk

    Returns:
        List of chunk strings
    """
    # Split on blank lines (paragraph boundaries)
    paragraphs = re.split(r'\n\s*\n', content)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    if not paragraphs:
        return [content] if content.strip() else []

    chunks = []
    current_chunk = ""

    for para in paragraphs:
        # If adding this paragraph would exceed limit
        if current_chunk and len(current_chunk) + len(para) + 2 > max_chars:
            # Save current chunk
            chunks.append(current_chunk)
            # Start new chunk with section title for context
            title_text = _extract_title_text(section_title)
            if title_text:
                current_chunk = f"[{title_text}]\n{para}"
            else:
                current_chunk = para
        else:
            # Add to current chunk
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para

    # Don't forget the last chunk
    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def _extract_title_text(header_line: str) -> str:
    """Extract plain text from a markdown header line.

    Args:
        header_line: Line like "## Section Title"

    Returns:
        Plain text like "Section Title"
    """
    if not header_line:
        return ""

    # Remove leading # characters and whitespace
    return re.sub(r'^#+\s*', '', header_line).strip()


def chunk_plain_text(
    content: str,
    source: str,
    max_chars: int = 1000,
) -> list[dict[str, Any]]:
    """Chunk plain text files by paragraphs.

    Args:
        content: Full text content
        source: File path or logical name
        max_chars: Soft character limit per chunk

    Returns:
        List of document dicts
    """
    # Reuse paragraph splitting logic
    chunks_content = _split_by_paragraphs(content, "", max_chars)

    chunks = []
    for i, chunk_content in enumerate(chunks_content):
        chunks.append({
            "content": chunk_content,
            "metadata": {
                "source": source,
                "section_title": "",
                "chunk_index": i,
            },
        })

    # Add total_chunks
    total = len(chunks)
    for chunk in chunks:
        chunk["metadata"]["total_chunks"] = total

    return chunks
