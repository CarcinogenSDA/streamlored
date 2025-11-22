# StreamLored

Context-aware Twitch AI co-host with RAG support, powered by Ollama. Features LiveSplit integration for speedrun context, OBS screenshots for visual awareness, and automatic question detection.

## Features

- **Twitch Chat Bot** - Command system with auto-response to questions
- **RAG Knowledge Base** - Ingest markdown docs for contextual answers
- **LiveSplit Integration** - Timer, splits, and pace info for speedruns
- **OBS Screenshots** - Visual context for "what's happening" questions
- **Local Chat Mode** - Test without Twitch connection
- **Plugin Architecture** - Extensible functionality

## Quick Start with Docker (Recommended)

### Prerequisites

- Docker and Docker Compose
- Ollama running (locally or remotely)
- Twitch OAuth token ([get one here](https://twitchapps.com/tmi/))

### Setup

1. Clone the repository:
   ```bash
   git clone <repo-url>
   cd streamlored
   ```

2. Create your configuration:
   ```bash
   cp .env.example .env
   ```

3. Edit `.env` with your settings (see Configuration section)

4. Pull required Ollama models:
   ```bash
   ollama pull llama3.2
   ollama pull nomic-embed-text
   ollama pull llama3.2-vision  # Optional, for screenshots
   ```

5. Build and run:
   ```bash
   make build
   make ingest  # Ingest docs into knowledge base
   make bot     # Start Twitch bot
   ```

## Makefile Commands

```bash
make help    # Show all commands
make build   # Build Docker image
make ingest  # Ingest docs/ into knowledge base
make bot     # Run Twitch bot
make local   # Run local chat mode (no Twitch)
make update  # Git pull latest
make logs    # Show container logs
make shell   # Open shell in container
make clean   # Remove Docker resources
```

## Twitch Commands

| Command | Description |
|---------|-------------|
| `!ping` | Bot responds with "pong" |
| `!ask <question>` | Ask the AI directly (no KB) |
| `!lore <question>` | Ask using knowledge base (RAG) |
| `!time` | Show current timer, split, and pace |
| `!pb` | Show personal best time |
| `!pace` | Show current pace vs PB |
| `!screenshot [question]` | Analyze current screen |

### Auto-Response

The bot automatically responds to questions in chat when:
- Message contains a question mark
- KB has relevant content (similarity > 0.65)
- Includes screenshot for vague questions like "what's going on?"

## Knowledge Base

### Creating Documents

Place markdown files in `docs/` folder. See [KNOWLEDGE_BASE_GUIDE.md](KNOWLEDGE_BASE_GUIDE.md) for formatting best practices.

Structure documents with headers matching your content:

```markdown
# Game Speedrun Guide

## Area Name

### Split Name

Content about this split...
```

When LiveSplit reports the current split, the bot enhances KB queries with the split name for better matches.

### Ingesting

```bash
make ingest
```

This processes all `.md` and `.txt` files in `docs/` and creates vector embeddings.

## Configuration

### Required for Twitch Bot

| Variable | Description |
|----------|-------------|
| `TWITCH_BOT_NICK` | Bot's Twitch username |
| `TWITCH_OAUTH_TOKEN` | OAuth token (include `oauth:` prefix) |
| `TWITCH_CHANNEL` | Channel to join |
| `TWITCH_CLIENT_ID` | Twitch app client ID |
| `TWITCH_CLIENT_SECRET` | Twitch app client secret |
| `TWITCH_BOT_ID` | Bot's Twitch user ID |

### Ollama

| Variable | Description | Default |
|----------|-------------|---------|
| `OLLAMA_HOST` | Ollama server hostname | `localhost` |
| `OLLAMA_PORT` | Ollama server port | `11434` |
| `OLLAMA_MODEL` | Model for chat | `llama3.2` |
| `OLLAMA_EMBED_MODEL` | Model for embeddings | `nomic-embed-text` |
| `OLLAMA_VISION_MODEL` | Model for screenshots | `llama3.2-vision` |

### Knowledge Base

| Variable | Description | Default |
|----------|-------------|---------|
| `KB_PATH` | Knowledge base file path | `data/knowledge_base.json` |
| `KB_ENABLED` | Enable RAG | `true` |

### OBS WebSocket (Optional)

| Variable | Description | Default |
|----------|-------------|---------|
| `OBS_ENABLED` | Enable OBS integration | `true` |
| `OBS_HOST` | OBS WebSocket host | `localhost` |
| `OBS_PORT` | OBS WebSocket port | `4455` |
| `OBS_PASSWORD` | OBS WebSocket password | - |

### LiveSplit (Optional)

| Variable | Description | Default |
|----------|-------------|---------|
| `LIVESPLIT_ENABLED` | Enable LiveSplit integration | `true` |
| `LIVESPLIT_HOST` | LiveSplit Server host | `localhost` |
| `LIVESPLIT_PORT` | LiveSplit Server port | `16834` |

### Other

| Variable | Description | Default |
|----------|-------------|---------|
| `RUN_MODE` | `bot` or `local-chat` | `bot` |
| `BOT_PREFIX` | Command prefix | `!` |
| `PERSONALITY_SNARK_LEVEL` | Snarkiness (0-3) | `2` |
| `TWITCH_POLL_INTERVAL` | Game poll interval (seconds) | `60` |

## Local Development (Without Docker)

### Prerequisites

- Python 3.11+
- Ollama running locally

### Setup

```bash
cd streamlored
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

### Running

```bash
# Ingest documents
streamlored --ingest docs/

# Start Twitch bot
streamlored

# Local chat mode
streamlored --local-chat
```

## LiveSplit Setup

1. Install [LiveSplit Server](https://github.com/LiveSplit/LiveSplit.Server) component
2. Right-click LiveSplit → Control → Start Server
3. Default port is 16834

The bot will show timer info and use split names to enhance KB queries.

## OBS Setup

1. Enable WebSocket Server in OBS (Tools → WebSocket Server Settings)
2. Set a password and note the port (default 4455)
3. Configure in `.env`

Used for `!screenshot` command and automatic visual context.

## Project Structure

```
streamlored/
├── src/streamlored/
│   ├── main.py              # CLI entry point
│   ├── config.py            # Configuration
│   ├── twitch_bot.py        # Twitch bot
│   ├── obs_client.py        # OBS WebSocket client
│   ├── llm/
│   │   └── ollama_client.py # Ollama integration
│   ├── plugins/
│   │   ├── base.py          # Plugin base class
│   │   ├── example_plugin.py
│   │   └── livesplit_plugin.py
│   └── rag/
│       ├── chunking.py      # Document chunking
│       ├── json_store.py    # Vector store
│       └── ollama_embeddings.py
├── docs/                    # Knowledge base source docs
├── data/                    # Generated KB storage
├── Dockerfile
├── docker-compose.yml
├── Makefile
└── KNOWLEDGE_BASE_GUIDE.md  # Doc formatting guide
```

## License

MIT
