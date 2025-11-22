"""Main entry point for StreamLored."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from streamlored.config import Settings, get_settings
from streamlored.llm import OllamaClient
from streamlored.rag.ollama_embeddings import OllamaEmbeddingProvider
from streamlored.rag.json_store import JsonDocumentStore
from streamlored.rag.chunking import chunk_markdown, chunk_plain_text
from streamlored.persona import build_system_prompt


def setup_logging() -> None:
    """Configure logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


async def run_ingest(settings: Settings, docs_dir: str) -> None:
    """Ingest documents from a directory into the knowledge base.

    Args:
        settings: Application settings
        docs_dir: Path to directory containing .txt or .md files
    """
    logger = logging.getLogger(__name__)

    docs_path = Path(docs_dir)
    if not docs_path.exists():
        logger.error(f"Directory not found: {docs_dir}")
        sys.exit(1)

    if not docs_path.is_dir():
        logger.error(f"Not a directory: {docs_dir}")
        sys.exit(1)

    # Find all .txt and .md files
    files = list(docs_path.glob("**/*.txt")) + list(docs_path.glob("**/*.md"))

    if not files:
        logger.warning(f"No .txt or .md files found in {docs_dir}")
        return

    logger.info(f"Found {len(files)} documents to ingest")

    # Check if knowledge base exists and prompt for confirmation
    kb_path = Path(settings.kb_path)
    if kb_path.exists():
        print(f"\nWarning: Knowledge base already exists at {settings.kb_path}")
        print("Ingesting will REPLACE the existing knowledge base.\n")
        try:
            response = input("Do you want to continue? [y/N] ").strip().lower()
            if response != 'y':
                logger.info("Ingest cancelled by user")
                return
            # Delete the old knowledge base
            kb_path.unlink()
            logger.info(f"Deleted existing knowledge base: {settings.kb_path}")
        except (KeyboardInterrupt, EOFError):
            print("\nIngest cancelled")
            return

    # Initialize embedding provider and document store
    embedding_provider = OllamaEmbeddingProvider(
        base_url=settings.ollama_base_url,
        model=settings.ollama_embed_model,
    )

    doc_store = JsonDocumentStore(
        kb_path=settings.kb_path,
        embedding_provider=embedding_provider,
    )

    # Read and chunk documents
    all_chunks = []
    for file_path in files:
        try:
            content = file_path.read_text(encoding="utf-8")
            if not content.strip():
                continue

            # Chunk based on file type
            if file_path.suffix.lower() == ".md":
                chunks = chunk_markdown(content, file_path.name)
            else:
                chunks = chunk_plain_text(content, file_path.name)

            all_chunks.extend(chunks)
            logger.info(f"Read: {file_path.name} -> {len(chunks)} chunks")

        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")

    if not all_chunks:
        logger.warning("No documents to ingest")
        return

    # Ingest all chunks
    await doc_store.ingest_documents(all_chunks)
    logger.info(f"Successfully ingested {len(all_chunks)} chunks into {settings.kb_path}")


async def run_local_chat(settings: Settings) -> None:
    """Run an interactive local chat REPL for testing RAG + Ollama.

    Args:
        settings: Application settings
    """
    logger = logging.getLogger(__name__)

    # Initialize Ollama client
    ollama = OllamaClient(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
    )

    # Check Ollama health
    if not await ollama.health_check():
        logger.error(f"Ollama not available at {settings.ollama_base_url}")
        sys.exit(1)

    logger.info(f"Connected to Ollama at {settings.ollama_base_url}")

    # Initialize RAG components if enabled
    doc_store: JsonDocumentStore | None = None
    if settings.kb_enabled:
        embedding_provider = OllamaEmbeddingProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_embed_model,
        )
        doc_store = JsonDocumentStore(
            kb_path=settings.kb_path,
            embedding_provider=embedding_provider,
        )
        doc_count = doc_store.document_count()
        if doc_count > 0:
            logger.info(f"Knowledge base loaded: {doc_count} documents")
        else:
            logger.warning("Knowledge base is empty")
    else:
        logger.info("Knowledge base disabled")

    # Initialize OBS client if enabled
    obs_client = None
    if settings.obs_enabled:
        logger.info(f"OBS enabled, connecting to {settings.obs_host}:{settings.obs_port}")
        from streamlored.obs_client import OBSWebSocketClient
        obs_client = OBSWebSocketClient(
            host=settings.obs_host,
            port=settings.obs_port,
            password=settings.obs_password,
        )
        if await obs_client.connect():
            logger.info(f"OBS connected at {settings.obs_host}:{settings.obs_port}")
        else:
            logger.warning("OBS connection failed")
            obs_client = None
    else:
        logger.info("OBS disabled")

    # Initialize LiveSplit plugin if enabled
    livesplit = None
    if settings.livesplit_enabled:
        logger.info(f"LiveSplit enabled, connecting to {settings.livesplit_host}:{settings.livesplit_port}")
        from streamlored.plugins.livesplit_plugin import LiveSplitPlugin
        livesplit = LiveSplitPlugin(
            host=settings.livesplit_host,
            port=settings.livesplit_port,
        )
        if await livesplit.connect():
            logger.info(f"LiveSplit connected at {settings.livesplit_host}:{settings.livesplit_port}")
        else:
            logger.warning("LiveSplit connection failed")
            livesplit = None
    else:
        logger.info("LiveSplit disabled")

    print("\nStreamLored Local Chat")
    print("Type 'exit' or 'quit' to stop")
    print("Commands: !time, !pb, !pace, !screenshot, !look")
    print("-" * 40)

    while True:
        try:
            # Get user input
            user_input = input("\nuser> ").strip()

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit"):
                print("Goodbye!")
                break

            # Handle LiveSplit commands
            if user_input.lower().startswith("!time") or user_input.lower().startswith("!timer"):
                if livesplit:
                    time = await livesplit.get_current_time()
                    phase = await livesplit.get_timer_phase()
                    if time:
                        if phase == "NotRunning":
                            print("\nbot> Timer not running")
                        elif phase == "Ended":
                            print(f"\nbot> Final time: {livesplit._format_time(time)}")
                        else:
                            print(f"\nbot> Current time: {livesplit._format_time(time)}")
                    else:
                        print("\nbot> LiveSplit not connected")
                else:
                    print("\nbot> LiveSplit not enabled")
                continue

            if user_input.lower().startswith("!pb"):
                if livesplit:
                    pb = await livesplit.get_final_time()
                    if pb and pb != "-":
                        print(f"\nbot> PB: {livesplit._format_time(pb)}")
                    elif pb == "-":
                        print("\nbot> No PB set for this category")
                    else:
                        print("\nbot> LiveSplit not connected")
                else:
                    print("\nbot> LiveSplit not enabled")
                continue

            if user_input.lower().startswith("!pace"):
                if livesplit:
                    delta = await livesplit.get_delta()
                    bpt = await livesplit.get_best_possible_time()
                    if delta and delta != "-":
                        if delta.startswith("-"):
                            msg = f"Currently {delta} ahead"
                        else:
                            msg = f"Currently {delta.lstrip('+')} behind"
                        if bpt and bpt != "-":
                            msg += f" | Best possible: {livesplit._format_time(bpt)}"
                        print(f"\nbot> {msg}")
                    else:
                        print("\nbot> No pace data available")
                else:
                    print("\nbot> LiveSplit not enabled")
                continue

            # Handle OBS screenshot commands
            if user_input.lower().startswith("!screenshot") or user_input.lower().startswith("!look"):
                if obs_client:
                    screenshot = await obs_client.get_screenshot()
                    if screenshot:
                        # Get question from command
                        parts = user_input.split(maxsplit=1)
                        question = parts[1] if len(parts) > 1 else "What's happening on screen?"

                        # Build context with LiveSplit if available
                        game_context = ""
                        if livesplit:
                            timer_context = await livesplit.get_context_string()
                            if timer_context:
                                game_context = timer_context

                        system_prompt = build_system_prompt("local_chat", game_context=game_context)
                        system_prompt += "\n\nAnalyze the image and answer based on what you see."

                        response = await ollama.generate(
                            prompt=question,
                            system_prompt=system_prompt,
                            images=[screenshot],
                            model_override=settings.ollama_vision_model,
                        )
                        print(f"\nbot> {response}")
                    else:
                        print("\nbot> Failed to capture screenshot")
                else:
                    print("\nbot> OBS not enabled or connected")
                continue

            # Get LiveSplit context first (needed for KB query enhancement)
            game_context = ""
            current_split = None
            if livesplit:
                try:
                    timer_context = await livesplit.get_context_string()
                    if timer_context:
                        game_context = timer_context
                        logger.info(f"LiveSplit context: {timer_context}")
                    # Get current split name for KB query enhancement
                    current_split = await livesplit.get_current_split_name()
                except Exception as e:
                    logger.warning(f"LiveSplit context failed: {e}")

            # Query knowledge base if available
            logger.info(f"Processing message: {user_input[:50]}...")
            context = ""
            if doc_store and doc_store.document_count() > 0:
                try:
                    # Enhance query with split name for better KB matches
                    kb_query = user_input
                    if current_split:
                        kb_query = f"{current_split}: {user_input}"
                        logger.info(f"Enhanced KB query with split: {kb_query}")

                    results = await doc_store.query_knowledge_base(kb_query, top_k=5)
                    if results:
                        logger.info(f"KB returned {len(results)} results")
                        context_parts = []
                        for doc in results:
                            source = doc.get("metadata", {}).get("source", "unknown")
                            section = doc.get("metadata", {}).get("section_title", "")
                            score = doc.get("score", 0)
                            logger.debug(f"  - {source} ({score:.2f})")
                            if section:
                                context_parts.append(f"[{source} - {section}]:\n{doc['content']}")
                            else:
                                context_parts.append(f"[{source}]:\n{doc['content']}")
                        context = "\n\n---\n\n".join(context_parts)
                    else:
                        logger.info("KB returned no results")
                except Exception as e:
                    logger.warning(f"KB query failed: {e}")

            # Build prompt with persona
            system_prompt = build_system_prompt(
                "local_chat",
                extra_context=context if context else None,
                game_context=game_context if game_context else None,
            )

            # Generate response
            logger.info("Generating LLM response...")
            response = await ollama.generate(
                prompt=user_input,
                system_prompt=system_prompt,
            )
            logger.info(f"Response generated ({len(response)} chars)")

            print(f"\nbot> {response}")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except EOFError:
            print("\nGoodbye!")
            break
        except Exception as e:
            logger.error(f"Error: {e}")
            print(f"\nbot> Sorry, an error occurred: {e}")

    # Cleanup
    if obs_client:
        await obs_client.disconnect()
    if livesplit:
        await livesplit.disconnect()


def run_twitch_bot(settings: Settings) -> None:
    """Run the Twitch bot.

    Args:
        settings: Application settings
    """
    logger = logging.getLogger(__name__)

    # Import here to avoid loading Twitch dependencies in other modes
    from streamlored.twitch_bot import TwitchBot
    from streamlored.plugins.example_plugin import ExamplePlugin
    from streamlored.plugins.livesplit_plugin import LiveSplitPlugin

    logger.info("Starting StreamLored Twitch Bot...")
    logger.info(f"Channel: {settings.twitch_channel}")

    # Create and configure bot
    bot = TwitchBot(settings)

    # Register plugins
    bot.register_plugin(ExamplePlugin())

    # Register LiveSplit plugin if enabled
    if settings.livesplit_enabled:
        bot.register_plugin(LiveSplitPlugin(
            host=settings.livesplit_host,
            port=settings.livesplit_port,
        ))

    # Run the bot
    logger.info("Connecting to Twitch...")
    bot.run()


def main() -> None:
    """Main entry point with CLI argument parsing."""
    setup_logging()
    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(
        description="StreamLored - Context-aware Twitch AI co-host",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  streamlored                    Start the Twitch bot
  streamlored --ingest docs/     Ingest documents into knowledge base
  streamlored --local-chat       Start local chat REPL (no Twitch)
        """,
    )
    parser.add_argument(
        "--ingest",
        metavar="DIR",
        help="Ingest documents from directory into knowledge base",
    )
    parser.add_argument(
        "--local-chat",
        action="store_true",
        help="Start local interactive chat (no Twitch connection)",
    )

    args = parser.parse_args()

    try:
        # Load configuration
        settings = get_settings()

        # CLI args take precedence over RUN_MODE env var
        if args.ingest:
            # Ingest mode
            asyncio.run(run_ingest(settings, args.ingest))
        elif args.local_chat or settings.run_mode == "local-chat":
            # Local chat mode
            asyncio.run(run_local_chat(settings))
        elif settings.run_mode == "bot" or not args.local_chat:
            # Twitch bot mode (default)
            run_twitch_bot(settings)

    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
