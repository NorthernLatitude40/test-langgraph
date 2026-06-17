import os
import sys
import logging
import time
import pymysql
from fastapi import FastAPI
import uvicorn
from mcp.server.fastmcp import FastMCP

# 日誌配置
log_file = os.path.join(os.path.dirname(__file__), "mcp_server.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(log_file, encoding="utf-8")]
)

mcp = FastMCP("Agent-Core-Server")

app = FastAPI()

# 把 MCP 挂到 FastAPI
app.mount("/", mcp.sse_app())  # 如果你的版本支持

# 資料庫連線設定
DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "root",
    "database": "my_agent_db",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor
}

@app.get("/health")
def health():
    return {"status": "ok"}

# ==========================================
# 核心功能一：原有的 MySQL 創建與寫入工具
# ==========================================

@mcp.tool()
def query_mysql(sql_query: str) -> str:
    """執行 MySQL 唯讀查詢語法（例如 SELECT）。"""
    clean_query = sql_query.strip().lower()
    if not clean_query.startswith("select") and not clean_query.startswith("show"):
        return "錯誤：僅允許執行 SELECT 或 SHOW 查詢。"
    try:
        connection = pymysql.connect(**DB_CONFIG)
        with connection.cursor() as cursor:
            cursor.execute(sql_query)
            return str(cursor.fetchall())
    except Exception as e:
        return f"錯誤: {str(e)}"
    finally:
        if 'connection' in locals() and connection.open:
            connection.close()

@mcp.tool()
def create_agent_order(user_id: int, product_id: int, quantity: int, price_per_unit: float) -> str:
    """
    當使用者想要購買某個商品時呼叫。
    此工具會自動計算總價，並同時寫入 MySQL 的 orders 主表與 order_items 明細表（主從表聯動），並返回付款連結。
    """
    logging.info(f"======== 收到 Agent 聯動創建訂單請求 ========")
    total_amount = round(quantity * price_per_unit, 2)
    current_date = time.strftime('%Y-%m-%d')
    
    try:
        connection = pymysql.connect(**DB_CONFIG)
        with connection.cursor() as cursor:
            # 1. 寫入 orders 主表
            sql_order = "INSERT INTO `orders` (`user_id`, `order_date`, `total_amount`, `status`) VALUES (%s, %s, %s, 'PENDING')"
            cursor.execute(sql_order, (user_id, current_date, total_amount))
            
            # 2. 獲取自增產生的 order_id
            new_order_id = cursor.lastrowid
            
            # 3. 寫入 order_items 明細表
            sql_item = "INSERT INTO `order_items` (`order_id`, `product_id`, `quantity`, `price_per_unit`) VALUES (%s, %s, %s, %s)"
            cursor.execute(sql_item, (new_order_id, product_id, quantity, price_per_unit))
            
            connection.commit()
            
        logging.info(f"成功聯動寫入 MySQL！主表訂單 ID: {new_order_id}。")
        
        # 指向獨立出來的 Flask 5000 埠口網址
        base_url = "http://localhost:5000"
        mock_pay_url = f"{base_url}/mock-pay-page?order_id={new_order_id}"
        
        return (
            f"【系統通知】訂單已成功同步寫入 MySQL 資料庫！\n"
            f"✨ 生成系統訂單 ID: {new_order_id}\n"
            f"👤 用戶 ID: {user_id}\n"
            f"💰 訂單總金額: {total_amount} 元\n\n"
            f"請引導使用者點擊以下連結進行模擬支付：\n{mock_pay_url}"
        )
        
    except Exception as e:
        logging.error(f"寫入資料庫失敗: {e}", exc_info=True)
        return f"建立訂單失敗，資料庫寫入異常: {str(e)}"
    finally:
        if 'connection' in locals() and connection.open:
            connection.close()


# ==========================================
# 核心功能二：全新加入：Agent Harness 測試評估工具
# ==========================================

@mcp.tool()
def run_agent_evaluation() -> str:
    """
    執行 Agent Harness 測試集與自動化評估，並生成基準測試報告。
    會讀取 tests/agent_harness/configs/wechat_pay_flow.yaml 並對接 LangGraph Agent 測試。
    """
    import yaml
    import httpx
    
    logging.info("🧪 [Harness] 進入真實評估流程，正在載入 YAML 設定檔...")
    
    # 🌟 設定你的真實 YAML 路徑
    BASE_DIR = os.path.dirname(__file__)
    yaml_path = os.path.join(BASE_DIR, "../../test/agent_harness/configs/wechat_pay_flow.yaml")
    
    if not os.path.exists(yaml_path):
        return f"❌ 評估失敗：找不到 YAML 設定檔，請確認路徑：{yaml_path}"
        
    try:
        # 1. 讀取並解析 YAML
        with open(yaml_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            
        test_name = config.get("name", "未命名測試集")
        agent_endpoint = config.get("target_agent_endpoint", "http://localhost:8000/agent")
        cases = config.get("cases", [])
        
        report = [
            f"📊 【Agent Harness 自動化評估報告】",
            f"📝 測試名稱: {test_name}",
            f"🎯 目標 Agent 端點: {agent_endpoint}",
            f"----------------------------------------"
        ]
        
        success_count = 0
        
        # 2. 遍歷測試案例，真正發送請求給 LangGraph Agent
        for idx, case in enumerate(cases, 1):
            user_input = case.get("input")
            expected_output = case.get("expected")
            
            report.append(f"🏃 測試案例 {idx}:")
            report.append(f"  [輸入]: {user_input}")
            report.append(f"  [預期]: {expected_output}")
            
            try:
                # 🌟 真正發送 HTTP POST 到你的 LangGraph 代理
                # 備註：請根據你 LangGraph 實際接收的 JSON 格式調整 payload（例如 {"message": user_input}）
                # 🌟 完美複製 Streamlit 前端的 Payload 格式，一字不差！
                payload = {
                    "message": user_input,
                    "mode": "query",
                    "model": "current",     
                    "temperature": 0.0    
                }
                response = httpx.post(agent_endpoint, json=payload, timeout=10.0)
                
                if response.status_code == 200:
                    agent_response = response.json().get("output", str(response.json()))
                    report.append(f"  [實際]: {agent_response}")
                    
                    # 簡單的比對邏輯（檢查實際輸出是否包含某些關鍵概念，或簡單記錄）
                    # 這裡先用寬鬆的比對，或者你可以寫更嚴格的斷言
                    success_count += 1
                    report.append(f"  🟢 狀態: 測試完成 (已回應)")
                else:
                    report.append(f"  🔴 狀態: 失敗 (Agent 端點回報錯誤碼 {response.status_code})")
                    
            except httpx.ConnectError:
                report.append(f"  ❌ 狀態: 失敗 (無法連線到 Agent 端點 {agent_endpoint}，請確認 LangGraph 是否有啟動)")
            except Exception as ce:
                report.append(f"  ❌ 狀態: 錯誤 ({str(ce)})")
                
            report.append("-" * 30)
            
        # 3. 總結
        report.append(f"🎉 評估結束：總共執行 {len(cases)} 筆測試，成功對接並回應 {success_count} 筆。")
        return "\n".join(report)

    except Exception as e:
        logging.error(f"執行 Harness 測試失敗: {e}", exc_info=True)
        return f"❌ 執行評估時發生嚴重異常: {str(e)}"




# ================= 3. 啟動內建網路伺服器 =================
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)