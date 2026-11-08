"""
Hybrid LLM Router Subsystem for SovereignDot.
Routes user voice queries between fast local Ollama and OpenRouter / Gemini streaming with MCP tool-calling.
"""
import os
import re
import json
import logging
import asyncio
from typing import Optional, List, AsyncGenerator
import requests
from openai import OpenAI, AsyncOpenAI
from core_server import config
from core_server.obsidian_memory import ObsidianMemory
from core_server.mcp_client import McpManager
from core_server.resilience import CircuitBreaker, global_circuit_breaker
from core_server.voice_id import SpeakerProfile

logger = logging.getLogger("llm")

COMPLEX_TRIGGERS = [
    "cherche", "recherche", "suricate", "suricata", "proxmox", "opensense", "opnsense",
    "notion", "firewall", "internet", "pourquoi", "explique", "détaille", "compare",
    "météo de demain", "homelab", "serveur", "serveurs", "vm", "conteneur", "docker",
]


class LLMRouterEngine:
    """Orchestrates Hybrid LLM execution: Local Ollama (simple queries) & Cloud OpenRouter (deep reasoning & tools)."""

    def __init__(
        self,
        obsidian: Optional[ObsidianMemory] = None,
        mcp: Optional[McpManager] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
    ):
        self.obsidian = obsidian or ObsidianMemory()
        self.mcp = mcp or McpManager()
        self.circuit_breaker = circuit_breaker or global_circuit_breaker

        # OpenRouter Clients
        self.llm_client: Optional[OpenAI] = None
        self.async_llm_client: Optional[AsyncOpenAI] = None
        if config.OPENROUTER_API_KEY:
            try:
                self.llm_client = OpenAI(
                    api_key=config.OPENROUTER_API_KEY,
                    base_url="https://openrouter.ai/api/v1",
                )
                self.async_llm_client = AsyncOpenAI(
                    api_key=config.OPENROUTER_API_KEY,
                    base_url="https://openrouter.ai/api/v1",
                )
                logger.info("OpenRouter client initialized (Router: typesafe/jev-router, Model: %s)", config.OPENROUTER_MODEL)
            except Exception as e:
                logger.warning("Failed to initialize OpenRouter client: %s", e)

        # Local Ollama Settings
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:latest")
        self.router_model = os.getenv("OPENROUTER_ROUTER_MODEL", "typesafe/jev-router")

        # In-memory conversational context history
        self.history: List[dict] = []

    def _query_ollama(self, messages: list) -> Optional[str]:
        """Calls local Ollama instance (e.g. Qwen 2.5). 100% private and offline-capable."""
        try:
            r = requests.post(
                self.ollama_url,
                json={
                    "model": self.ollama_model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": 0.7, "num_predict": 128},
                },
                timeout=4.0,
            )
            if r.status_code == 200:
                reply = r.json().get("message", {}).get("content", "").strip()
                if reply:
                    logger.info("Ollama (%s) replied: %s", self.ollama_model, reply)
                    return reply
        except Exception as e:
            logger.warning("Local Ollama query failed: %s", e)
        return None

    def _split_into_sentences(self, text: str) -> List[str]:
        """Splits full text into natural sentences for progressive audio playback."""
        raw_chunks = re.split(r"(?<=[.!?])\s+", text.strip())
        return [c.strip() for c in raw_chunks if c.strip()]

    async def generate_response_stream(
        self,
        prompt: str,
        speaker: SpeakerProfile,
    ) -> AsyncGenerator[str, None]:
        """
        Routes and streams response tokens as complete spoken sentences:
        1. Simple/routine prompt -> Local Ollama (<500ms).
        2. Complex reasoning / Tools -> OpenRouter Gemini streaming.
        3. Fallback on network errors -> Local Ollama.
        """
        p_lower = prompt.lower()
        from datetime import datetime

        now = datetime.now()
        now_str = now.strftime("%A %d %B %Y à %H:%M")

        # Inject dynamic context (Obsidian notes + speaker metadata)
        obsidian_context = self.obsidian.get_relevant_context(prompt)
        dynamic_system_prompt = (
            f"{config.SYSTEM_PROMPT}\n"
            f"Date et heure courantes: {now_str}\n"
            f"Locuteur identifié: {speaker.name} (Rôle: {speaker.role.value})\n\n"
            f"Contexte et mémoire connus:\n{obsidian_context}"
        )

        messages = [{"role": "system", "content": dynamic_system_prompt}]
        messages.extend(self.history[-6:])
        messages.append({"role": "user", "content": prompt})

        # Router Classifier
        is_complex = any(k in p_lower for k in COMPLEX_TRIGGERS) or len(prompt.split()) > 14

        # A. Route simple/routine query to Local Ollama first
        if not is_complex:
            logger.info("Routing simple/routine prompt to Local Ollama (%s)...", self.ollama_model)
            loop = asyncio.get_running_loop()
            ollama_reply = await loop.run_in_executor(None, self._query_ollama, messages)
            if ollama_reply:
                self.history.append({"role": "user", "content": prompt})
                self.history.append({"role": "assistant", "content": ollama_reply})
                for s in self._split_into_sentences(ollama_reply):
                    yield s
                return

        # B. Route complex prompt to OpenRouter / Gemini with tool calling & native streaming
        if self.async_llm_client and self.circuit_breaker.is_cloud_available():
            try:
                logger.info("Routing to OpenRouter JEV / Gemini (%s)...", config.OPENROUTER_MODEL)
                tools = self.mcp.get_openai_tools()

                # Tool-calling turn if query references homelab or tools
                if tools and any(k in p_lower for k in ["proxmox", "docker", "suricata", "serveur", "vm", "conteneur", "opnsense", "status"]):
                    response = await self.async_llm_client.chat.completions.create(
                        model=self.router_model,
                        messages=messages,
                        tools=tools,
                        max_tokens=256,
                        temperature=0.7,
                    )
                    message = response.choices[0].message
                    if hasattr(message, "tool_calls") and message.tool_calls:
                        for tc in message.tool_calls:
                            func_name = tc.function.name
                            try:
                                args = json.loads(tc.function.arguments)
                            except Exception:
                                args = {}
                            logger.info("LLM triggered tool: %s with args: %s", func_name, args)
                            tool_res = await self.mcp.call_tool(func_name, args)
                            messages.append(message)
                            messages.append({"role": "tool", "tool_call_id": tc.id, "content": tool_res})

                # Stream final formulated response tokens
                stream = await self.async_llm_client.chat.completions.create(
                    model=config.OPENROUTER_MODEL,
                    messages=messages,
                    max_tokens=256,
                    temperature=0.7,
                    stream=True,
                )

                full_reply = ""
                token_buffer = ""
                async for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    if not delta:
                        continue
                    full_reply += delta
                    token_buffer += delta

                    match = re.search(r"([.!?]+(\s+|$))", token_buffer)
                    if match:
                        end_pos = match.end()
                        sentence = token_buffer[:end_pos].strip()
                        if not re.search(r"\d\.\d$", sentence) and len(sentence) >= 5:
                            yield sentence
                            token_buffer = token_buffer[end_pos:]

                if token_buffer.strip():
                    yield token_buffer.strip()

                if full_reply.strip():
                    self.circuit_breaker.record_success()
                    self.history.append({"role": "user", "content": prompt})
                    self.history.append({"role": "assistant", "content": full_reply.strip()})
                    return

            except Exception as e:
                self.circuit_breaker.record_failure(e)
                logger.error("OpenRouter streaming call failed, falling back to local Ollama: %s", e)

        # C. Fallback to Local Ollama
        loop = asyncio.get_running_loop()
        ollama_reply = await loop.run_in_executor(None, self._query_ollama, messages)
        if ollama_reply:
            for s in self._split_into_sentences(ollama_reply):
                yield s
            return

        # D. Ultimate Offline Fallbacks
        if "heure" in p_lower:
            yield f"Il est actuellement {now.strftime('%H heures %M')}."
            return
        yield "J'ai bien entendu votre demande, mais je n'ai pas pu joindre mes moteurs de réflexion."
