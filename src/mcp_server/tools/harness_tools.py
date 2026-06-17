from mcp.server.fastmcp import FastMCP  # 假設你使用 fastmcp，若用基礎 mcp-sdk 邏輯類似
from tests.agent_harness.run_harness import execute_harness_test

# 假設你在 server.py 中初始化 mcp，這裡可以寫成註冊函數或直接匯入
def register_harness_tools(mcp: FastMCP):
    
    @mcp.tool()
    def run_agent_evaluation(test_suite: str) -> str:
        """
        運行 Agent Harness 評估測試集。
        
        Args:
            test_suite (str): 測試集名稱，例如 'wechat_pay_flow' 或 'refund_suites'。
        """
        # 呼叫剛剛寫好的測試封裝
        report_markdown = execute_harness_test(test_suite)
        return report_markdown