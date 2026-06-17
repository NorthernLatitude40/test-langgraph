import asyncio
import traceback
from contextlib import AsyncExitStack

from langchain_mcp_adapters.tools import load_mcp_tools
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

from src.config import MCP_SERVER_URL


class MCPClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return

        self.tools = []
        self._connected = False

        self._initialized = True

    async def connect(self):

        if self._connected:
            return

        try:
            print(f"[MCP] connecting -> {MCP_SERVER_URL}")

            async with AsyncExitStack() as stack:

                read, write = await stack.enter_async_context(
                    sse_client(MCP_SERVER_URL)
                )

                session = await stack.enter_async_context(
                    ClientSession(read, write)
                )

                await asyncio.wait_for(
                    session.initialize(),
                    timeout=15,
                )

                self.tools = await load_mcp_tools(session)

            self._connected = True

            print(
                f"[MCP] loaded tools: {len(self.tools)}"
            )

        except Exception as e:
            print(f"[MCP ERROR] {e}")
            traceback.print_exc()

            self.tools = []
            self._connected = False

    async def get_tools(self):

        if not self._connected:
            await self.connect()

        return self.tools

    def is_connected(self):
        return self._connected


mcp_client = MCPClient()