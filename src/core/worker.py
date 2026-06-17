import asyncio
import threading
import traceback
from contextlib import AsyncExitStack
# 替换为你实际的 MCP 客户端导入路径
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession


from core.agent import Agent

class AgentWorker:
    """
    負責在獨立執行緒中管理所有 Async 生命週期與 MCP 網路連線。
    對外部暴露出純同步 (Synchronous) 的介面。
    """
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.exit_stack = AsyncExitStack()
        self.agent_core = None
        self.thread = None

    def start_background_loop(self):
        """啟動背景 Event Loop"""
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def start(self):
        """啟動 Worker 執行緒並建立環境"""
        self.thread = threading.Thread(target=self.start_background_loop, daemon=True)
        self.thread.start()
        
        # 透過背景 loop 執行初始化
        future = asyncio.run_coroutine_threadsafe(self._async_init(), self.loop)
        return future.result() # 同步等待初始化完成

    async def _async_init(self):
        """在背景 loop 執行的非同步網路初始化"""
        mcp_tools = []
        try:
            server_url = "http://localhost:8001/sse"
            print(f"🔄 [Network] 正在嘗試連接 MCP 伺服器端點: {server_url}")
            
            read, write = await self.exit_stack.enter_async_context(sse_client(server_url))
            session = await self.exit_stack.enter_async_context(ClientSession(read, write))
            
            await asyncio.wait_for(session.initialize(), timeout=5)
            print("✨ [Network] MCP 伺服器連線成功，網路管道已打通！")
            
            mcp_tools = await load_mcp_tools(session)
            print(f"✅ 成功託管並載入 {len(mcp_tools)} 個網路 MySQL MCP 工具")
        except Exception as e:
            print(f"🛑 MCP 網路工具載入失敗，僅啟用本地客服工具。原因: {e}")
            traceback.print_exc()

        # 实例化真正的核心大脑
        self.agent_core = Agent(mcp_tools=mcp_tools)

    def sync_invoke(self, inputs: dict, config: dict) -> dict:
        """同步桥接方法"""
        if not self.agent_core:
            raise RuntimeError("Agent 尚未完成初始化！")
            
        future = asyncio.run_coroutine_threadsafe(
            self.agent_core.app.ainvoke(inputs, config), 
            self.loop
        )
        return future.result()