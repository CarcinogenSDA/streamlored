"""Twitch bot implementation using TwitchIO."""

import asyncio
import logging
from collections import deque
from datetime import datetime
from twitchio.ext import commands

from streamlored.config import Settings
from streamlored.llm import OllamaClient
from streamlored.plugins import BasePlugin
from streamlored.rag.ollama_embeddings import OllamaEmbeddingProvider
from streamlored.rag.json_store import JsonDocumentStore
from streamlored.persona import build_system_prompt
from streamlored.twitch_api import TwitchAPIClient, GameContext
from streamlored.obs_client import OBSWebSocketClient

logger = logging.getLogger(__name__)

# Max characters for Twitch chat
MAX_RESPONSE_LENGTH = 500


class TwitchBot(commands.Bot):
    """StreamLored Twitch chat bot."""

    def __init__(self, settings: Settings):
        """Initialize the Twitch bot.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self.plugins: list[BasePlugin] = []

        # Initialize Ollama client
        self.ollama = OllamaClient(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
        )

        # Initialize RAG components if enabled
        self.doc_store: JsonDocumentStore | None = None
        if settings.kb_enabled:
            embedding_provider = OllamaEmbeddingProvider(
                base_url=settings.ollama_base_url,
                model=settings.ollama_embed_model,
            )
            self.doc_store = JsonDocumentStore(
                kb_path=settings.kb_path,
                embedding_provider=embedding_provider,
            )

        # Initialize Twitch API client for game context
        self.api_client = TwitchAPIClient(
            client_id=settings.twitch_client_id,
            client_secret=settings.twitch_client_secret,
        )
        self.current_game: GameContext | None = None
        self._game_poll_task: asyncio.Task | None = None

        # Initialize OBS WebSocket client for screenshots
        self.obs_client: OBSWebSocketClient | None = None
        if settings.obs_enabled:
            self.obs_client = OBSWebSocketClient(
                host=settings.obs_host,
                port=settings.obs_port,
                password=settings.obs_password,
            )

        # Chat history for context (last 10 messages)
        self.chat_history: deque = deque(maxlen=10)

        # Stream history - tracks games played during this session
        # Format: [{"game": "Game Name", "title": "Stream Title", "started": datetime, "ended": datetime|None}]
        self.stream_history: list[dict] = []
        self._stream_start_time: datetime | None = None

        # Initialize TwitchIO bot
        super().__init__(
            token=settings.twitch_oauth_token,
            prefix=settings.bot_prefix,
            initial_channels=[settings.twitch_channel],
        )

    async def event_ready(self) -> None:
        """Called when the bot is ready and connected."""
        logger.info(f"Bot connected as {self.settings.twitch_bot_nick}")
        logger.info(f"Joined channel: {self.settings.twitch_channel}")

        # Check Ollama health
        if await self.ollama.health_check():
            logger.info(f"Ollama connected at {self.settings.ollama_base_url}")
        else:
            logger.warning(f"Ollama not available at {self.settings.ollama_base_url}")

        # Initialize plugins
        for plugin in self.plugins:
            await plugin.setup(self)

        # Start game polling task
        if self.settings.twitch_client_id and self.settings.twitch_client_secret:
            self._game_poll_task = asyncio.create_task(self._poll_game_context())
            logger.info(f"Game polling started (every {self.settings.twitch_poll_interval}s)")
        else:
            logger.warning("Twitch client_id/secret not set - game context disabled")

        # Connect to OBS WebSocket
        if self.obs_client:
            if await self.obs_client.connect():
                logger.info(f"OBS WebSocket connected at {self.settings.obs_host}:{self.settings.obs_port}")
            else:
                logger.warning("Failed to connect to OBS WebSocket - screenshot feature disabled")
                self.obs_client = None

    async def _poll_game_context(self) -> None:
        """Periodically poll for current game context."""
        while True:
            try:
                new_context = await self.api_client.get_stream_info(
                    self.settings.twitch_channel
                )

                # Check if game changed
                old_game = self.current_game.game_name if self.current_game else None
                new_game = new_context.game_name if new_context else None

                if old_game != new_game:
                    now = datetime.now()

                    # End previous game session
                    if self.stream_history and self.stream_history[-1]["ended"] is None:
                        self.stream_history[-1]["ended"] = now

                    if new_game:
                        title = new_context.title if new_context else None
                        logger.info(f"Now playing: {new_game} | Title: {title}")

                        # Start new game session
                        self.stream_history.append({
                            "game": new_game,
                            "title": title,
                            "started": now,
                            "ended": None,
                        })

                        # Set stream start time on first game
                        if self._stream_start_time is None:
                            self._stream_start_time = now
                    elif old_game:
                        logger.info("Stream went offline or game cleared")

                # Clear old history if it gets too large (max 50 sessions)
                if len(self.stream_history) > 50:
                    removed = len(self.stream_history) - 50
                    self.stream_history = self.stream_history[-50:]
                    logger.info(f"Trimmed stream history (removed {removed} old sessions)")

                self.current_game = new_context

            except Exception as e:
                logger.error(f"Error polling game context: {e}")

            await asyncio.sleep(self.settings.twitch_poll_interval)

    async def event_message(self, message) -> None:
        """Handle incoming chat messages.

        Args:
            message: The chat message
        """
        # Ignore bot's own messages
        if message.echo:
            return

        # Log incoming messages
        logger.debug(f"[{message.author.name}]: {message.content}")

        # Add to chat history
        self.chat_history.append({
            "user": message.author.name,
            "content": message.content,
        })

        # Check if bot is directly mentioned
        if "streamlored" in message.content.lower():
            await self._handle_mention(message)
            return

        # Check if this looks like a question we can answer from KB
        if await self._should_auto_respond(message):
            await self._handle_auto_response(message)
            return

        # Process commands
        await self.handle_commands(message)

    async def _should_auto_respond(self, message) -> bool:
        """Check if we should auto-respond to this message.

        Args:
            message: The chat message

        Returns:
            True if we should respond
        """
        content = message.content.lower()
        logger.info(f"[AUTO] Checking: {content}")

        # Exclude common false positives (rhetorical, emote spam, etc.)
        exclusions = [
            "what the fuck", "what the hell", "wtf",
            "lul", "lol", "kekw", "omegalul",
            "gg", "pog", "pogchamp",
        ]
        if any(excl == content.strip() for excl in exclusions):
            logger.info(f"[AUTO] Excluded (false positive): {content}")
            return False

        # Question patterns (high priority)
        question_indicators = [
            "?",
            # Basic question words
            "what is", "what's", "whats", "what are",
            "who is", "who's", "whos",
            "how do", "how to", "how does", "how did",
            "why is", "why does", "why do", "why are",
            "when did", "when does", "when is",
            "where is", "where's", "wheres", "where are", "where do", "where can",
            "which one", "which should",
            # Request patterns
            "can you", "could you", "can i", "can someone",
            "tell me", "explain",
            "anyone know", "does anyone", "anybody know",
            "is there", "are there", "is this",
            "do you have", "does this",
            # Help-seeking patterns
            "need help", "stuck on", "trying to",
            "tips for", "any tips", "advice",
            "recommend", "suggestion",
            "best way", "fastest way", "easiest",
            "should i",
        ]

        # Gaming/speedrun specific keywords (respond if KB has info)
        gaming_keywords = [
            "strat", "strats", "strategy",
            "trick", "skip", "glitch",
            "world record", " wr ", "wr?",
            "pb", "pr", "personal best",
            "splits", "category",
            "any%", "100%",
            "boss", "enemy", "zombie",
            "item", "weapon", "ammo",
            "puzzle", "solution",
        ]

        # Stream history questions (can answer without KB)
        stream_history_patterns = [
            "did i miss", "did we miss", "have i missed",
            "what did i miss", "what'd i miss", "what have i missed",
            "what games", "what game did", "what was played",
            "played earlier", "playing earlier", "played before",
            "weren't you playing", "weren't we playing", "wasn't this",
            "thought you were playing", "thought we were playing",
            "switch games", "switched games", "change games", "changed games",
            "how long", "been playing",
        ]

        has_stream_history_question = any(pattern in content for pattern in stream_history_patterns)
        has_question = any(indicator in content for indicator in question_indicators)
        has_gaming_keyword = any(kw in content for kw in gaming_keywords)

        logger.info(f"[AUTO] Pattern match - question: {has_question}, gaming: {has_gaming_keyword}, stream_history: {has_stream_history_question}")

        # Stream history questions can be answered directly from stream history
        if has_stream_history_question and self.stream_history:
            logger.info(f"[AUTO] Stream history question detected - will respond")
            return True

        # Need at least a question pattern or gaming keyword
        if not has_question and not has_gaming_keyword:
            logger.info(f"[AUTO] No patterns matched for: {content}")
            return False

        # Check if we have relevant KB content
        if not self.doc_store or self.doc_store.document_count() == 0:
            logger.info("[AUTO] No KB available or empty")
            return False

        # Query KB to see if we have relevant content
        try:
            # Include game context and split name in the query for better relevance
            query = message.content

            # Get current split from LiveSplit plugin if available
            current_split = None
            for plugin in self.plugins:
                if plugin.name == "livesplit" and hasattr(plugin, 'get_current_split_name'):
                    current_split = await plugin.get_current_split_name()
                    if current_split:
                        logger.info(f"[AUTO] LiveSplit current split: {current_split}")
                    break

            if current_split:
                query = f"{current_split}: {message.content}"
                logger.info(f"[AUTO] Enhanced query: {query}")
            elif self.current_game and self.current_game.game_name:
                query = f"{self.current_game.game_name}: {message.content}"

            results = await self.doc_store.query_knowledge_base(query, top_k=3)
            if not results:
                logger.info(f"[AUTO] No KB results for: {message.content[:50]}")
                return False

            # Check similarity - only respond if we have good matches
            # Require minimum similarity threshold to avoid false positives
            top_result = results[0]
            similarity_score = top_result.get("score", 0)

            # Only auto-respond if similarity is above threshold
            # 0.65 allows split-enhanced queries to match, 0.75 was too strict
            if similarity_score < 0.65:
                logger.info(f"[AUTO] KB match too weak ({similarity_score:.2f} < 0.65) for: {message.content[:50]}")
                return False

            logger.info(f"[AUTO] KB match found ({similarity_score:.2f}) - will respond to: {message.content[:50]}")
            return True

        except Exception as e:
            logger.error(f"Error checking KB relevance: {e}")
            return False

    async def _handle_auto_response(self, message) -> None:
        """Handle automatic response to a question using KB.

        Args:
            message: The chat message to respond to
        """
        game_context = await self._get_game_context_string()
        chat_context = self._get_chat_history_string()

        try:
            # Include split name or game context in query for better matches
            query = message.content

            # Get current split from LiveSplit plugin if available
            current_split = None
            for plugin in self.plugins:
                if plugin.name == "livesplit" and hasattr(plugin, 'get_current_split_name'):
                    current_split = await plugin.get_current_split_name()
                    break

            if current_split:
                query = f"{current_split}: {message.content}"
            elif self.current_game and self.current_game.game_name:
                query = f"{self.current_game.game_name}: {message.content}"

            # Query knowledge base
            results = await self.doc_store.query_knowledge_base(query, top_k=5)

            if not results:
                return

            # Build context from results
            context_parts = []
            for doc in results:
                source = doc.get("metadata", {}).get("source", "unknown")
                section = doc.get("metadata", {}).get("section_title", "")
                if section:
                    context_parts.append(f"[{source} - {section}]:\n{doc['content']}")
                else:
                    context_parts.append(f"[{source}]:\n{doc['content']}")

            kb_context = "\n\n".join(context_parts)

            # Combine all context
            full_context = kb_context
            if chat_context:
                full_context = f"Recent chat:\n{chat_context}\n\nKnowledge base:\n{kb_context}"

            system_prompt = build_system_prompt(
                "lore",
                game_context=game_context,
                extra_context=full_context,
            )

            # Check if this is a vague question that would benefit from screenshot context
            content_lower = message.content.lower()
            vague_patterns = [
                "what's going on", "whats going on", "what is going on",
                "what are we doing", "what's happening", "whats happening",
                "where are we", "what is this", "what's this",
            ]
            use_screenshot = any(pattern in content_lower for pattern in vague_patterns)

            # Capture screenshot if OBS is available and question is vague
            screenshot = None
            if use_screenshot and self.obs_client:
                try:
                    screenshot = await self.obs_client.get_screenshot()
                    if screenshot:
                        logger.info("[AUTO] Including screenshot for vague question")
                        system_prompt += "\n\nYou can see a screenshot of what's on screen. Use it to give specific context about what's happening."
                except Exception as e:
                    logger.debug(f"Failed to capture screenshot for auto-response: {e}")

            response = await self.ollama.generate(
                prompt=message.content,
                system_prompt=system_prompt,
                images=[screenshot] if screenshot else None,
                model_override=self.settings.ollama_vision_model if screenshot else None,
            )

            # Enforce max length
            if len(response) > MAX_RESPONSE_LENGTH - 50:
                response = response[:MAX_RESPONSE_LENGTH - 53] + "..."

            await message.channel.send(f"@{message.author.name} {response}")

            # Log detailed context
            logger.info(f"Auto-responded to {message.author.name}: {message.content[:80]}")
            logger.info(f"  Game context: {game_context if game_context else 'None'}")
            logger.info(f"  KB sources: {[doc.get('metadata', {}).get('source', '?') for doc in results]}")
            logger.info(f"  Top score: {results[0].get('score', 0):.2f}")
            if chat_context:
                logger.info(f"  Chat history:\n{chat_context}")
            logger.info(f"  KB context preview: {kb_context[:300]}...")
            logger.info(f"  Response: {response[:100]}...")

        except Exception as e:
            logger.error(f"Error in auto-response: {e}")

    async def _handle_mention(self, message) -> None:
        """Handle when the bot is mentioned in chat.

        Args:
            message: The chat message mentioning the bot
        """
        game_context = await self._get_game_context_string()
        chat_context = self._get_chat_history_string()

        # Build the prompt with full context
        prompt = f"{message.author.name} said: '{message.content}'\n\nRespond naturally to what they said."

        try:
            # Combine game and chat context
            extra_context = ""
            if chat_context:
                extra_context = f"Recent chat history:\n{chat_context}"

            system_prompt = build_system_prompt(
                "ask",
                game_context=game_context,
                extra_context=extra_context if extra_context else None,
            )

            response = await self.ollama.generate(
                prompt=prompt,
                system_prompt=system_prompt,
            )

            # Enforce max length
            if len(response) > MAX_RESPONSE_LENGTH - 50:  # Leave room for @mention
                response = response[:MAX_RESPONSE_LENGTH - 53] + "..."

            await message.channel.send(f"@{message.author.name} {response}")

            # Log detailed context
            logger.info(f"Mention response to {message.author.name}: {message.content[:80]}")
            logger.info(f"  Game context: {game_context if game_context else 'None'}")
            if chat_context:
                logger.info(f"  Chat history:\n{chat_context}")
            logger.info(f"  Response: {response[:100]}...")

        except Exception as e:
            logger.error(f"Error responding to mention: {e}")

    def _get_chat_history_string(self) -> str:
        """Get formatted chat history for context.

        Returns:
            Formatted string of recent chat messages
        """
        if not self.chat_history:
            return ""

        lines = []
        for msg in self.chat_history:
            lines.append(f"{msg['user']}: {msg['content']}")

        return "\n".join(lines)

    def register_plugin(self, plugin: BasePlugin) -> None:
        """Register a plugin with the bot.

        Args:
            plugin: The plugin instance to register
        """
        self.plugins.append(plugin)
        logger.info(f"Registered plugin: {plugin.name}")

    async def close(self) -> None:
        """Clean up resources before shutdown."""
        # Cancel game polling task
        if self._game_poll_task:
            self._game_poll_task.cancel()
            try:
                await self._game_poll_task
            except asyncio.CancelledError:
                pass

        # Disconnect from OBS
        if self.obs_client:
            await self.obs_client.disconnect()

        # Teardown plugins
        for plugin in self.plugins:
            await plugin.teardown()

        await super().close()

    def _get_stream_history_string(self) -> str:
        """Get a formatted string describing games played during this stream.

        Returns:
            History string like "Tonight's stream: Dead Space (1hr), then RE2 (current)"
        """
        if not self.stream_history:
            return ""

        parts = []
        for i, session in enumerate(self.stream_history):
            game = session["game"]
            started = session["started"]
            ended = session["ended"]

            if ended:
                # Calculate duration
                duration = ended - started
                minutes = int(duration.total_seconds() / 60)
                if minutes >= 60:
                    hours = minutes // 60
                    mins = minutes % 60
                    duration_str = f"{hours}hr {mins}min" if mins else f"{hours}hr"
                else:
                    duration_str = f"{minutes}min"
                parts.append(f"{game} ({duration_str})")
            else:
                # Current game
                duration = datetime.now() - started
                minutes = int(duration.total_seconds() / 60)
                if minutes >= 60:
                    hours = minutes // 60
                    mins = minutes % 60
                    duration_str = f"{hours}hr {mins}min" if mins else f"{hours}hr"
                else:
                    duration_str = f"{minutes}min"
                parts.append(f"{game} ({duration_str}, current)")

        if not parts:
            return ""

        return "Tonight's stream: " + ", then ".join(parts)

    async def _get_game_context_string(self) -> str:
        """Get a formatted string describing the current game/stream context.

        Returns:
            Context string for system prompts, or empty string if no context
        """
        parts = []

        if self.current_game:
            context = self.current_game.to_context_string()
            if context:
                parts.append(context)

        history = self._get_stream_history_string()
        if history:
            parts.append(history)

        # Get plugin context (e.g., LiveSplit timer state)
        for plugin in self.plugins:
            if hasattr(plugin, 'get_context_string'):
                try:
                    plugin_context = await plugin.get_context_string()
                    if plugin_context:
                        parts.append(plugin_context)
                except Exception as e:
                    logger.debug(f"Error getting context from plugin {plugin.name}: {e}")

        if parts:
            return " ".join(parts) + " Focus your answer on this game/series first, but you can reference other games when useful."
        return ""

    @commands.command(name="ping")
    async def cmd_ping(self, ctx: commands.Context) -> None:
        """Respond to !ping command.

        Args:
            ctx: Command context
        """
        await ctx.send(f"pong @{ctx.author.name}")

    @commands.command(name="ask")
    async def cmd_ask(self, ctx: commands.Context) -> None:
        """Send a question to the LLM and reply with the answer.

        Args:
            ctx: Command context
        """
        # Get the question from the message (everything after !ask)
        question = ctx.message.content.split(maxsplit=1)
        if len(question) < 2:
            await ctx.send(f"@{ctx.author.name} Please provide a question! Usage: !ask <question>")
            return

        question_text = question[1]
        logger.info(f"User {ctx.author.name} asked: {question_text}")

        try:
            # Generate response from Ollama with persona and game context
            game_context = await self._get_game_context_string()
            system_prompt = build_system_prompt("ask", game_context=game_context)

            response = await self.ollama.generate(
                prompt=question_text,
                system_prompt=system_prompt,
            )

            # Truncate if too long for Twitch
            if len(response) > MAX_RESPONSE_LENGTH - 50:
                response = response[:MAX_RESPONSE_LENGTH - 53] + "..."

            await ctx.send(f"@{ctx.author.name} {response}")

        except Exception as e:
            logger.error(f"Error generating response: {e}")
            await ctx.send(f"@{ctx.author.name} Sorry, I couldn't process that request.")

    @commands.command(name="lore")
    async def cmd_lore(self, ctx: commands.Context) -> None:
        """Answer a question using the knowledge base (RAG).

        Args:
            ctx: Command context
        """
        # Check if RAG is available
        if not self.doc_store or not self.settings.kb_enabled:
            await ctx.send(f"@{ctx.author.name} Knowledge base is not enabled.")
            return

        if self.doc_store.document_count() == 0:
            await ctx.send(f"@{ctx.author.name} Knowledge base is empty. No lore available yet!")
            return

        # Get the question from the message
        question = ctx.message.content.split(maxsplit=1)
        if len(question) < 2:
            await ctx.send(f"@{ctx.author.name} Please provide a question! Usage: !lore <question>")
            return

        question_text = question[1]
        logger.info(f"User {ctx.author.name} asked lore: {question_text}")

        try:
            # Query knowledge base
            results = await self.doc_store.query_knowledge_base(question_text, top_k=5)

            if not results:
                await ctx.send(f"@{ctx.author.name} No relevant information found in the knowledge base.")
                return

            # Build context from results
            context_parts = []
            for doc in results:
                source = doc.get("metadata", {}).get("source", "unknown")
                section = doc.get("metadata", {}).get("section_title", "")
                if section:
                    context_parts.append(f"[{source} - {section}]:\n{doc['content']}")
                else:
                    context_parts.append(f"[{source}]:\n{doc['content']}")

            context = "\n\n".join(context_parts)

            # Generate response with RAG context, persona, and game context
            game_context = await self._get_game_context_string()
            system_prompt = build_system_prompt("lore", extra_context=context, game_context=game_context)

            response = await self.ollama.generate(
                prompt=question_text,
                system_prompt=system_prompt,
            )

            # Truncate if too long for Twitch
            if len(response) > MAX_RESPONSE_LENGTH - 50:
                response = response[:MAX_RESPONSE_LENGTH - 53] + "..."

            await ctx.send(f"@{ctx.author.name} {response}")

        except Exception as e:
            logger.error(f"Error in !lore command: {e}")
            await ctx.send(f"@{ctx.author.name} Sorry, I couldn't search the knowledge base.")

    @commands.command(name="screenshot")
    async def cmd_screenshot(self, ctx: commands.Context) -> None:
        """Capture a screenshot and describe what's happening using vision model.

        Args:
            ctx: Command context
        """
        # Check if OBS is connected
        if not self.obs_client:
            await ctx.send(f"@{ctx.author.name} Screenshot feature is not enabled or OBS is not connected.")
            return

        # Get optional question from message
        parts = ctx.message.content.split(maxsplit=1)
        question = parts[1] if len(parts) > 1 else "What's happening on screen right now?"

        logger.info(f"User {ctx.author.name} requested screenshot: {question}")

        try:
            # Capture screenshot (stays in memory as base64)
            screenshot = await self.obs_client.get_screenshot()

            if not screenshot:
                await ctx.send(f"@{ctx.author.name} Failed to capture screenshot from OBS.")
                return

            # Build strict vision prompt - prevent hallucination
            vision_system = """Analyze this stream screenshot.

RULES:
- Answer in 1 sentence MAX (under 150 characters)
- Only describe what you literally see
- Be direct and factual
- No speculation or predictions

If asked a question, answer it briefly. Otherwise, state the key visible element."""

            # Generate response using vision model
            response = await self.ollama.generate(
                prompt=question,
                system_prompt=vision_system,
                images=[screenshot],
                model_override=self.settings.ollama_vision_model,
            )

            # Truncate if too long for Twitch
            if len(response) > MAX_RESPONSE_LENGTH - 50:
                response = response[:MAX_RESPONSE_LENGTH - 53] + "..."

            await ctx.send(f"@{ctx.author.name} {response}")

            logger.info(f"Screenshot response to {ctx.author.name}: {response[:100]}...")

        except Exception as e:
            logger.error(f"Error in !screenshot command: {e}")
            await ctx.send(f"@{ctx.author.name} Sorry, I couldn't process the screenshot.")

    @commands.command(name="look")
    async def cmd_look(self, ctx: commands.Context) -> None:
        """Look at the screen and answer with persona + game context.

        Args:
            ctx: Command context
        """
        # Check if OBS is connected
        if not self.obs_client:
            await ctx.send(f"@{ctx.author.name} Screenshot feature is not enabled or OBS is not connected.")
            return

        # Get optional question from message
        parts = ctx.message.content.split(maxsplit=1)
        question = parts[1] if len(parts) > 1 else "What's happening on screen?"

        logger.info(f"User {ctx.author.name} requested look: {question}")

        try:
            # Capture screenshot
            screenshot = await self.obs_client.get_screenshot()

            if not screenshot:
                await ctx.send(f"@{ctx.author.name} Failed to capture screenshot from OBS.")
                return

            # Build persona prompt with game context
            game_context = await self._get_game_context_string()
            system_prompt = build_system_prompt("ask", game_context=game_context)

            # Add vision-specific guidance
            system_prompt += """

When analyzing the image:
- Base your answer on what you can see
- You can use your game knowledge to provide context
- Stay in character with your usual tone
- Don't make up things that aren't visible"""

            # Generate response using vision model
            response = await self.ollama.generate(
                prompt=question,
                system_prompt=system_prompt,
                images=[screenshot],
                model_override=self.settings.ollama_vision_model,
            )

            # Truncate if too long for Twitch
            if len(response) > MAX_RESPONSE_LENGTH - 50:
                response = response[:MAX_RESPONSE_LENGTH - 53] + "..."

            await ctx.send(f"@{ctx.author.name} {response}")

            logger.info(f"Look response to {ctx.author.name}: {response[:100]}...")

        except Exception as e:
            logger.error(f"Error in !look command: {e}")
            await ctx.send(f"@{ctx.author.name} Sorry, I couldn't process that.")
