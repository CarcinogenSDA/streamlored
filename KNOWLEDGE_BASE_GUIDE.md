# Knowledge Base Document Guide

This guide explains how to create documents for StreamLored's RAG (Retrieval Augmented Generation) knowledge base.

## Overview

Documents in the `docs/` folder are processed and indexed into the knowledge base when you run:

```bash
docker compose run --rm streamlored --ingest docs/
```

The bot uses these documents to answer questions during streams with relevant, accurate information.

## Document Format

### File Types
- **Markdown (`.md`)** - Recommended. Best chunking and section awareness.
- **Plain text (`.txt`)** - Supported. Chunked by paragraphs.

### Naming Convention
- Use lowercase with underscores: `game_name_topic.md`
- Be descriptive: `re2_remake_speedrun.md`, `resident_evil_lore.md`
- The filename becomes the `source` metadata in search results

## Markdown Structure

The chunking system splits documents by markdown headers, so structure matters:

### Headers Create Chunks

```markdown
# Main Title

Content here becomes one chunk (if under 1000 chars).

## Section Name

This section becomes its own chunk.
The section title is stored as metadata for better search relevance.

### Subsection

Subsections also create separate chunks.
```

### Best Practices

1. **Use headers for distinct topics**
   - Each `##` or `###` header starts a new chunk
   - The header text is stored as `section_title` in metadata
   - Good for KB queries: "Lion Medallion" header matches queries about Lion Medallion

2. **Keep sections focused**
   - ~500-1000 characters per section is ideal
   - Sections over 1000 chars get split by paragraphs

3. **Include context in section content**
   - Don't rely on the header alone
   - Bad: `### Solution` with just "Lion, Branch, Eagle"
   - Good: `### Lion Medallion` with "Solve the Lion Statue puzzle. Solution: Lion, Branch, Eagle"

4. **Use descriptive headers**
   - Headers are used to match search queries
   - Match split names if creating speedrun guides

## Speedrun Guide Format

For speedrun guides that integrate with LiveSplit, match your section headers to split names:

```markdown
# Game Name Speedrun Guide

## Area Name

### Splits
1. Split One
2. Split Two
3. Split Three

---

### Split One

Content about what happens during this split.

**Route:**
- Step 1
- Step 2

**Key Items:** Item Name

**Speedrun Note:** Quick tip for speedrunners.

---

### Split Two

...
```

When LiveSplit reports the current split as "Split One", the bot queries the KB with "Split One: [user question]" which matches your "### Split One" section.

## Chunk Metadata

Each chunk gets this metadata:
- `source` - Filename (e.g., `re2_remake_speedrun.md`)
- `section_title` - Header text without `#` symbols
- `chunk_index` - Position in document
- `total_chunks` - Total chunks from this file

## Example Document

```markdown
# Resident Evil 2 Remake Speedrun Guide

## Gas Station (Prologue)

### Splits
1. Meet First Zombie
2. Storage Room Key
3. Meet Claire/Leon

---

### Meet First Zombie

Your character investigates a gas station. A police officer is killed by a zombie in the storage room.

**Combat:**
- Leon starts with Matilda Handgun
- Three headshots down the zombie

**Speedrun Note:** Skip killing this zombie - just grab the key and run past.

---

### Storage Room Key

After downing (or passing) the zombie, find the key on the wall behind the shelves.

**Key Item:** Storage Room Key

**Speedrun Note:** Grab quickly without inspecting - having it in inventory is enough.

---

### Meet Claire/Leon

Escape the store using the Storage Room Key.

**Escape Route:**
- Loop around the back aisle
- One shot to stun center zombie
- Sprint to the door

**Speedrun Note:** Hug right wall, quick shot, don't stop moving.
```

## Ingesting Documents

After adding or modifying documents:

```bash
# Ingest all docs
docker compose run --rm streamlored --ingest docs/

# Ingest specific file
docker compose run --rm streamlored --ingest docs/my_new_guide.md
```

Note: Ingesting replaces existing KB entries from the same source file.

## Testing Your Documents

After ingestion, test with queries that should match your content:

1. Ask specific questions: "What's the Lion Medallion solution?"
2. Use split-context questions: "What are we doing?" (while on that split)
3. Check logs for KB sources and similarity scores

If queries aren't matching:
- Make headers more specific
- Include more context keywords in section content
- Check that the section isn't too long (gets split into paragraphs)

## Tips

- **Frontload important info** - First 1000 chars of a section stay together
- **Use markdown formatting** - Bold, lists, etc. are preserved in chunks
- **Be consistent** - Same header format across similar documents
- **Test incrementally** - Ingest and test one doc at a time
