"""
TAD MCP Client Module.
Manages connections to external Model Context Protocol (MCP) servers (Firecrawl, Notion, etc.).
Translates MCP tools to OpenAI/OpenRouter function signatures for LLM tool calling.
"""
import os
import json
import logging
import asyncio
from typing import Dict, List, Any, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger("mcp_client")

class McpManager:
    def __init__(self, config_path: str = "mcp_config.json"):
        self.config_path = config_path
        self.tools: List[Dict[str, Any]] = []
        self.tool_to_server: Dict[str, str] = {}
        self.sessions: Dict[str, ClientSession] = {}
        self._exit_stack = None

    async def initialize(self):
        """Reads mcp_config.json and establishes sessions with active MCP servers."""
        if not os.path.exists(self.config_path):
            logger.info("No %s found. Creating template configuration.", self.config_path)
            self._create_default_config()

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except Exception as e:
            logger.error("Failed to parse %s: %s", self.config_path, e)
            return

        servers = config_data.get("mcpServers", {})
        logger.info("Found %d configured MCP server(s) in %s", len(servers), self.config_path)

        for name, srv in servers.items():
            if not srv.get("enabled", True):
                logger.info("MCP server '%s' is disabled, skipping.", name)
                continue
            await self._connect_server(name, srv)

    def _create_default_config(self):
        default_cfg = {
            "mcpServers": {
                "firecrawl": {
                    "enabled": False,
                    "command": "npx",
                    "args": ["-y", "firecrawl-mcp"],
                    "env": {
                        "FIRECRAWL_API_KEY": os.getenv("FIRECRAWL_API_KEY", "")
                    }
                },
                "notion": {
                    "enabled": False,
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-notion"],
                    "env": {
                        "NOTION_API_KEY": os.getenv("NOTION_API_KEY", "")
                    }
                }
            }
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(default_cfg, f, indent=2)

    async def _connect_server(self, name: str, srv: Dict[str, Any]):
        cmd = srv.get("command")
        args = srv.get("args", [])
        env = {**os.environ, **srv.get("env", {})}

        logger.info("Connecting to MCP server '%s' (%s %s)...", name, cmd, " ".join(args))
        server_params = StdioServerParameters(command=cmd, args=args, env=env)

        try:
            # We start stdio client in background
            read, write = await stdio_client(server_params).__aenter__()
            session = ClientSession(read, write)
            await session.__aenter__()
            await session.initialize()
            
            # Query tool list
            tools_result = await session.list_tools()
            self.sessions[name] = session

            count = 0
            for t in tools_result.tools:
                # Convert to OpenAI tool format
                tool_def = {
                    "type": "function",
                    "function": {
                        "name": f"{name}_{t.name}",
                        "description": t.description or f"Tool from {name}",
                        "parameters": t.inputSchema or {"type": "object", "properties": {}}
                    }
                }
                self.tools.append(tool_def)
                self.tool_to_server[f"{name}_{t.name}"] = (name, t.name)
                count += 1

            logger.info("MCP server '%s' connected successfully with %d tool(s).", name, count)
        except Exception as e:
            logger.warning("Could not connect to MCP server '%s': %s", name, e)

    def get_openai_tools(self) -> List[Dict[str, Any]]:
        """Returns the list of loaded MCP tools formatted for OpenAI / OpenRouter function calling."""
        return self.tools

    async def call_tool(self, namespaced_name: str, arguments: Dict[str, Any]) -> str:
        """Executes a tool on the designated MCP server."""
        if namespaced_name not in self.tool_to_server:
            return f"Error: Tool '{namespaced_name}' not found."

        server_name, actual_name = self.tool_to_server[namespaced_name]
        session = self.sessions.get(server_name)
        if not session:
            return f"Error: Session for server '{server_name}' is not active."

        logger.info("Executing MCP tool '%s' on server '%s' with args: %s", actual_name, server_name, arguments)
        try:
            result = await session.call_tool(actual_name, arguments=arguments)
            # Combine text content from tool result
            output_parts = []
            for c in result.content:
                if hasattr(c, "text"):
                    output_parts.append(c.text)
                else:
                    output_parts.append(str(c))
            return "\n".join(output_parts)
        except Exception as e:
            logger.error("Error executing MCP tool '%s': %s", namespaced_name, e)
            return f"Error executing tool {namespaced_name}: {e}"
