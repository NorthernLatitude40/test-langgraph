
import os
import sys
# 🔥 核心關鍵：在載入 Flask 之前，強制關閉 Flask 所有的控制台 Banner 輸出
os.environ["WERKZEUG_RUN_MAIN"] = "true"
os.environ["FLASK_SKIP_DOTENV"] = "1"

import logging
import threading
import time
from mcp.server.fastmcp import FastMCP
import pymysql
from flask import Flask, request, jsonify


# 日誌配置
log_file = os.path.join(os.path.dirname(__file__), "mcp_server.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(log_file, encoding="utf-8")]
)

mcp = FastMCP("Agent-Core-Server")

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

# ==========================================
# 區塊 A：Flask 模擬網關（撈取真實 MySQL 訂單進行支付）
# ==========================================
app = Flask(__name__)
logging.getLogger('werkzeug').disabled = True

@app.route("/mock-pay-page", methods=["GET"])
def mock_pay_page():
    # 這裡我們傳入剛剛寫入 MySQL 的 order_id
    order_id = request.args.get("order_id")
    
    # 🌟 實作你說的：「支付時候撈取這個創建好的訂單支付」
    try:
        connection = pymysql.connect(**DB_CONFIG)
        with connection.cursor() as cursor:
            # 從資料庫聯查（JOIN）主表與明細表，撈出要支付的商品資訊
            sql = """
                SELECT o.order_id, o.total_amount, o.status, oi.product_id, oi.quantity 
                FROM orders o
                LEFT JOIN order_items oi ON o.order_id = oi.order_id
                WHERE o.order_id = %s
            """
            cursor.execute(sql, (order_id,))
            order_rows = cursor.fetchall()
            
            if not order_rows:
                return f"<h3>錯誤：在 MySQL 中找不到訂單 ID: {order_id} 的資訊</h3>", 404
                
            main_order = order_rows[0]
            
            # 如果已經付過錢了，防重複支付
            if main_order["status"] == "PAID":
                return "<h3>提示：該訂單已支付完成，請勿重複付款。</h3>"
                
    except Exception as e:
        return f"<h3>資料庫連線異常: {str(e)}</h3>", 500
    finally:
        if 'connection' in locals() and connection.open:
            connection.close()

    return f"""
    <html>
      <head><meta charset="utf-8"><title>微信支付模擬器</title></head>
      <body style="font-family: sans-serif; text-align: center; padding-top: 50px; background-color: #f5f5f5;">
        <div style="max-width: 400px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <h2 style="color: #07c160;">微信支付模擬器</h2>
            <p style="color: #666;">（成功從 MySQL 撈取訂單數據）</p>
            <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
            <p style="text-align: left;"><strong>MySQL 系統訂單 ID:</strong> {order_id}</p>
            <p style="text-align: left;"><strong>購買商品數量:</strong> {len(order_rows)} 項商品</p>
            <p style="text-align: left;"><strong>應付總金額:</strong> <span style="color: #ff4d4f; font-size: 22px; font-weight: bold;">￥{main_order['total_amount']}</span> 元</p>
            
            <button id="payBtn" style="width: 100%; margin-top: 20px; padding: 12px; font-size: 16px; background: #07c160; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold;">
              確認模擬付款 (修改 MySQL 狀態)
            </button>
        </div>
        <script>
          document.getElementById('payBtn').onclick = function() {{
            this.innerText = '正在處理支付...';
            this.disabled = true;
            
            fetch('/mock-wechat-webhook', {{
              method: 'POST',
              headers: {{ 'Content-Type': 'application/json' }},
              body: JSON.stringify({{ "order_id": "{order_id}", "result_code": "SUCCESS" }})
            }}).then(res => res.json()).then(data => {{
              alert('付款成功！MySQL 中的 orders 表狀態已更新為 PAID。');
              window.close();
            }});
          }}
        </script>
      </body>
    </html>
    """

# 微信 Webhook 回調：修改 MySQL orders 表的 status 欄位
@app.route("/mock-wechat-webhook", methods=["POST"])
def mock_wechat_webhook():
    data = request.json or {}
    order_id = data.get("order_id")
    result_code = data.get("result_code")
    
    if result_code == "SUCCESS":
        try:
            connection = pymysql.connect(**DB_CONFIG)
            with connection.cursor() as cursor:
                # 🌟 如果你的 orders 表沒有 status 欄位，請記得 ALTER TABLE orders ADD COLUMN status VARCHAR(20) DEFAULT 'PENDING';
                # 這裡我們假設主表有一個狀態欄位來控制訂單狀態
                sql = "UPDATE `orders` SET `status` = 'PAID' WHERE `order_id` = %s"
                cursor.execute(sql, (order_id,))
                connection.commit()
                logging.info(f"🎉 MySQL 狀態更新！訂單 ID {order_id} 已變更為 [PAID]")
                return jsonify({"return_code": "SUCCESS"}), 200
        except Exception as e:
            logging.error(f"Webhook 更新 MySQL 失敗: {e}")
        finally:
            if 'connection' in locals() and connection.open:
                connection.close()
                
    return jsonify({"return_code": "FAIL"}), 400


# ==========================================
# 區塊 B：為 AI 專門撰寫的 MCP 創建與寫入工具
# ==========================================

@mcp.tool()
def create_agent_order(user_id: int, product_id: int, quantity: int, price_per_unit: float) -> str:
    """
    當使用者想要購買某個商品時呼叫。
    此工具會自動計算總價，並同時寫入 MySQL 的 orders 主表與 order_items 明細表（主從表聯動），並返回付款連結。
    
    Args:
        user_id (int): 購買用戶的 ID（例如：1 代表張小明）。
        product_id (int): 商品的 ID（例如：4 代表保溫隨行杯）。
        quantity (int): 購買數量。
        price_per_unit (float): 商品單價。
    """
    logging.info(f"======== 收到 Agent 聯動創建訂單請求 ========")
    
    # 自動計算總金額
    total_amount = round(quantity * price_per_unit, 2)
    current_date = time.strftime('%Y-%m-%d')
    
    try:
        connection = pymysql.connect(**DB_CONFIG)
        with connection.cursor() as cursor:
            # 1. 寫入 orders 主表
            # 💡 注意：如果你的 orders 表還沒有 status 欄位，建議在 MySQL 執行：ALTER TABLE orders ADD COLUMN status VARCHAR(20) DEFAULT 'PENDING';
            sql_order = "INSERT INTO `orders` (`user_id`, `order_date`, `total_amount`, `status`) VALUES (%s, %s, %s, 'PENDING')"
            cursor.execute(sql_order, (user_id, current_date, total_amount))
            
            # 🌟 關鍵核心：獲取剛剛主表自增生成的 order_id！
            new_order_id = cursor.lastrowid
            
            # 2. 寫入 order_items 明細表
            sql_item = "INSERT INTO `order_items` (`order_id`, `product_id`, `quantity`, `price_per_unit`) VALUES (%s, %s, %s, %s)"
            cursor.execute(sql_item, (new_order_id, product_id, quantity, price_per_unit))
            
            # 3. 提交事務（保證主從表同時寫入成功）
            connection.commit()
            
        logging.info(f"成功聯動寫入 MySQL！主表訂單 ID: {new_order_id}, 明細表同步完成。")
        
        # 4. 生成支付網頁網址，把新生成的 order_id 傳過去
        base_url = "http://localhost:5000"
        mock_pay_url = f"{base_url}/mock-pay-page?order_id={new_order_id}&amount={total_amount}"
        
        return (
            f"【系統通知】訂單已成功同步寫入 MySQL 資料庫！\n"
            f"✨ 生成系統訂單 ID: {new_order_id}\n"
            f"👤 用戶 ID: {user_id}\n"
            f"💰 訂單總金額: {total_amount} 元\n\n"
            f"請引導使用者點擊以下連結，進入模擬支付網頁（該網頁將直接從 MySQL 撈取這筆新訂單進行支付）：\n{mock_pay_url}"
        )
        
    except Exception as e:
        logging.error(f"寫入資料庫失敗: {e}", exc_info=True)
        return f"建立訂單失敗，資料庫寫入異常: {str(e)}"
    finally:
        if 'connection' in locals() and connection.open:
            connection.close()


# 原有的 MySQL 查詢工具（保持不動，供 AI 隨時查驗）
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

def start_flask():
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    mcp.run()