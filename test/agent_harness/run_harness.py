import subprocess
import json
import os

def execute_harness_test(test_suite: str) -> str:
    """
    執行 Agent Harness 測試集，並返回 Markdown 格式的報告
    """
    # 1. 定義設定檔路徑與輸出路徑
    config_path = f"tests/agent_harness/configs/{test_suite}.yaml"
    output_path = f"tests/agent_harness/results/{test_suite}_result.json"
    
    if not os.path.exists(config_path):
        return f"❌ 找不到指定的測試集設定檔: {config_path}"
    
    # 確保輸出目錄存在
    os.makedirs("tests/agent_harness/results", exist_ok=True)
    
    try:
        # 2. 呼叫 Agent Harness CLI (依據你使用的 Agent Harness 實際指令調整)
        # 這裡假設指令為: agent-harness run --config <path> --output <path>
        cmd = ["agent-harness", "run", "--config", config_path, "--output", output_path]
        
        # 執行命令並等待結束
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        # 3. 解析生成的 JSON 報告並轉成 Markdown
        if os.path.exists(output_path):
            with open(output_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 建立給 LLM 閱讀的 Markdown 摘要
            summary = f"### 📊 Agent Harness 測試報告: {test_suite}\n"
            summary += f"- **總測試案例數**: {data.get('total_cases', 0)}\n"
            summary += f"- **成功率**: {data.get('success_rate', 0)}%\n"
            summary += f"- **平均耗時**: {data.get('avg_latency_seconds', 0)}s\n\n"
            
            summary += "#### ❌ 失敗案例詳情:\n"
            failures = data.get("failures", [])
            if not failures:
                summary += "🎉 所有測試案例全部通過！\n"
            else:
                for fail in failures:
                    summary += f"- **Case**: {fail.get('input')}\n"
                    summary += f"  - *預期結果*: {fail.get('expected')}\n"
                    summary += f"  - *實際結果*: {fail.get('actual')}\n"
                    summary += f"  - *錯誤原因*: {fail.get('reason')}\n"
            
            return summary
        else:
            return "❌ 測試執行完成，但未找到報告檔案。"
            
    except subprocess.CalledProcessError as e:
        return f"💥 執行 Agent Harness 時發生錯誤:\nExit Code: {e.returncode}\nError: {e.stderr}"
    except Exception as e:
        return f"🚨 發生未知錯誤: {str(e)}"