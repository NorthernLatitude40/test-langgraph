# core/harness.py
import asyncio
import threading
import traceback
from contextlib import AsyncExitStack

# 🌟 官方最新 SDK 标准导入路径
from mcp import ClientSession
from mcp.client.sse import sse_client

from core.agent import Agent


class AgentHarness:
    """
    Agent Harness (駕馭層 / 運行殼)
    """

    def __init__(self, mcp_server_url: str = "http://localhost:8001/sse"):
        self.mcp_server_url = mcp_server_url
        self.loop = asyncio.new_event_loop()
        self.exit_stack = AsyncExitStack()
        self.agent_core = None  # 存放核心大腦
        self._thread = None

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def _async_init(self):
        """在背景 Loop 中打通網路管道，裝載內核(代理模式)"""
        lc_tools = []  # 儲存轉換成 LangChain 格式的工具
        try:
            print(f"🔄 [Harness] 正在建立連接至 MCP 伺服器: {self.mcp_server_url}")
            read, write = await self.exit_stack.enter_async_context(
                sse_client(self.mcp_server_url)
            )

            # 注意：這裡將 session 提升為類別屬性 self.mcp_session，方便後續遠端調用
            self.mcp_session = await self.exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await asyncio.wait_for(self.mcp_session.initialize(), timeout=5)
            print("✨ [Harness] MCP 網路管道打通成功！")

            tools_response = await self.mcp_session.list_tools()
            mcp_tools = tools_response.tools

            # 🌟 核心修正：改用 StructuredTool 显式绑定遠端 MCP 工具的 JSON Schema 结构
            from langchain_core.tools import StructuredTool

            for remote_tool in mcp_tools:
                # 這裡使用動態閉包，讓 LangChain 呼叫該工具時，Harness 自動發送 RPC 請求給遠端 MCP Server
                def make_mcp_wrapper(tool_name):
                    async def mcp_wrapper(**kwargs):
                        # ====== 💡 核心修复代码开始 ======
                        # 如果发现参数被错误地包在了一个叫 'kwargs' 的键里，直接把它提出来
                        actual_args = (
                            kwargs.get("kwargs", kwargs)
                            if "kwargs" in kwargs and len(kwargs) == 1
                            else kwargs
                        )
                        # ====== 💡 核心修复代码结束 ======

                        # 調用常駐於 Harness 內部的會話發送請求
                        res = await self.mcp_session.call_tool(
                            tool_name, arguments=actual_args
                        )
                        # 回傳遠端資料庫或服務的純文字結果
                        return "".join(
                            [
                                content.text
                                for content in res.content
                                if hasattr(content, "text")
                            ]
                        )

                    return mcp_wrapper

                # 🎯 从远端 MCP 传入的工具定义中取出参数结构 input_schema
                # 有些 SDK 为字典，有些为对象，这里做一层鲁棒兼容
                raw_schema = getattr(remote_tool, "input_schema", None)
                if isinstance(
                    raw_schema, os if "os" in locals() else object
                ) or hasattr(raw_schema, "model_json_schema"):
                    tool_schema = raw_schema
                else:
                    tool_schema = None

                # 🎯 使用 StructuredTool 替代普通的 lc_tool
                constructed_tool = StructuredTool.from_function(
                    name=remote_tool.name,
                    description=remote_tool.description or "MCP Remote Tool",
                    coroutine=make_mcp_wrapper(remote_tool.name),
                    # 将遠端工具所需要的真实参数结构注册进来，彻底终结模型识别出 'kwargs' 的情况
                    args_schema=tool_schema,
                )
                lc_tools.append(constructed_tool)

            print(f"✅ [Harness] 成功動態轉換並裝載 {len(lc_tools)} 個網路生態工具")

        except Exception as e:
            print(f"🛑 [Harness Warning] MCP 管道建立失敗，降級為純本地運行。原因: {e}")
            traceback.print_exc()

        # 🌟 傳入轉換完成的 lc_tools，而不是原始的 mcp_tools
        self.agent_core = Agent(mcp_tools=lc_tools)

    def bootstrap(self):
        """啟動 Harness 背景殼環境"""
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        future = asyncio.run_coroutine_threadsafe(self._async_init(), self.loop)
        return future.result(timeout=60)

    def interact(self, user_message: str, thread_id: str) -> str:
        """多端復用的標準同步交互接口（门面模式）"""
        if not self.agent_core:
            raise RuntimeError("Harness 運行殼尚未就緒！")

        inputs = {"messages": [("user", user_message)]}
        config = {"configurable": {"thread_id": thread_id}}

        future = asyncio.run_coroutine_threadsafe(
            self.agent_core.app.ainvoke(inputs, config), self.loop
        )
        result = future.result()
        return result["messages"][-1].content
