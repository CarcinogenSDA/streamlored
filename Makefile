.PHONY: build ingest bot local update clean logs shell help

# Default target
help:
	@echo "StreamLored Commands:"
	@echo "  make build   - Build Docker image"
	@echo "  make ingest  - Ingest docs into knowledge base"
	@echo "  make bot     - Run Twitch bot"
	@echo "  make local   - Run local chat mode"
	@echo "  make update  - Pull latest from repo"
	@echo "  make logs    - Show container logs"
	@echo "  make shell   - Open shell in container"
	@echo "  make clean   - Remove Docker containers and images"

# Build the Docker image
build:
	docker compose build

# Ingest documents into knowledge base
ingest:
	docker compose run --rm streamlored streamlored --ingest docs/

# Run Twitch bot
bot:
	docker compose run --rm -e RUN_MODE=bot streamlored

# Run local chat mode
local:
	docker compose run --rm -e RUN_MODE=local-chat streamlored

# Pull latest changes
update:
	git pull

# Show logs
logs:
	docker compose logs -f

# Open shell in container
shell:
	docker compose run --rm streamlored /bin/bash

# Clean up Docker resources
clean:
	docker compose down --rmi local -v
