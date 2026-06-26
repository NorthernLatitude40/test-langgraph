import os
import sys
import logging
import time
import pymysql
from fastapi import FastAPI
import uvicorn
from mcp.server.fastmcp import FastMCP
from src.mcp_server.graph_data import graph
from neo4j import GraphDatabase
from typing import List
from src.ingestion.interface.ontology.output_contract import MappingRule

# 引入剛才抽離出來的獨立工具類別與參數契約
from src.mcp_server.tools.graph_ingestion_tools import (
    GraphIngestionTools,
    IngestionInput,
)

# 日誌配置
log_file = os.path.join(os.path.dirname(__file__), "mcp_server.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(log_file, encoding="utf-8")],
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
    "cursorclass": pymysql.cursors.DictCursor,
}

# 1. 在模块全局加载时，初始化 Driver
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")

# 全局唯一的 driver 实例
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# ==========================================
# 實例化抽離出來的圖匯入工具箱，共享全局唯一的 driver
# ==========================================
ingestion_toolbox = GraphIngestionTools(neo4j_driver=driver)


@app.get("/health")
def health():
    return {"status": "ok"}


# ==========================================
# 新增核心功能：大數據圖譜構建雙工具（優雅橋接至類別方法）
# ==========================================


@mcp.tool()
def inspect_excel_schema(file_path: str) -> str:
    """
    當使用者提供一個 Excel 檔案路徑時，優先使用此工具。
    它會掃描 Excel 並回傳所有工作表(Sheets)的名稱、欄位名稱與系統標準型態。
    """
    return ingestion_toolbox.inspect_dataset_schema(file_path)


@mcp.tool()
def execute_excel_to_graph(file_path: str, mapping_rules: List[MappingRule]) -> str:
    """
    在分析完 Schema 並決定好圖對應規則(Mapping Rules)後，使用此工具將 rows 全量寫入 Neo4j。
    Args:
        mapping_rules: 格式必須嚴格遵守以下範例：
        [
            {
                "source_sheet": "Orders",
                "map_to_node": [{"concept_id": "ns0__VIPCustomer", "primary_key": "customer_id"}],
                "map_to_edge": [{"source_key": "customer_id", "target_key": "product_id", "relationship_id": "ns0__bought"}]
            }
        ]
    """
    # 這裡可以直接調用，FastMCP 會自動依據 args_schema 將傳入的 json 轉為對應的 MappingRule 結構
    return ingestion_toolbox.execute_graph_ingestion(file_path, mapping_rules)


# ==========================================
# 核心功能一：原有的 MySQL 創建與寫入工具
# ==========================================


@mcp.tool()
def query_mysql(sql_query: str) -> str:
    """
    僅用於常規快捷工具無法覆蓋的、極度複雜的後台數據庫管理、財務報表統計或系統維護。
    絕對不能用於查詢客戶與商品的購買歷史或名下資產。
    """
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
        if "connection" in locals() and connection.open:
            connection.close()


@mcp.tool()
def create_agent_order(
    user_id: int, product_id: int, quantity: int, price_per_unit: float
) -> str:
    """
    當使用者想要購買某個商品時呼叫。
    此工具會自動計算總價，並同時寫入 MySQL 的 orders 主表與 order_items 明細表（主從表聯動），並返回付款連結。
    """
    logging.info(f"======== 收到 Agent 聯動創建訂單請求 ========")
    total_amount = round(quantity * price_per_unit, 2)
    current_date = time.strftime("%Y-%m-%d")

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
            cursor.execute(
                sql_item, (new_order_id, product_id, quantity, price_per_unit)
            )

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
        if "connection" in locals() and connection.open:
            connection.close()


@mcp.tool()
def get_tour_deals_by_city(city_name: str) -> list:
    """
    利用 n10s 本體推理，查詢指定城市出發或全局的紐西蘭旅遊特惠行程（Deals）。
    核心業務工具：查詢城市（City）與巴士旅遊行程（TourDeal/HopOnHopOffDeal）之間的關聯。
    支持傳入具體城市名（如 Auckland, Queenstown, Anywhere），也支持傳入全局概念名稱（如 City 或 TourDeal）。
    只要用戶提問涉及“從哪裡出發有什麼行程”、“某城市的旅遊套裝”、“特惠行程查詢”，必須且只能調用此工具。
    """
    print("\n" + "=" * 50)
    print(f"[LOG] 工具進入 - 目標城市/概念: '{city_name}'")

    search_name = city_name.strip()

    # 轉換為小寫判斷是否為全局本體概念查詢
    is_global_query = search_name.lower() in ["city", "tourdeal", "hoponhopoffdeal"]

    if is_global_query:
        print("[LOG] 判定結果: 全局本體概念推理 (撈取所有行程與城市的關聯)")
        query = """
        // 1. 鎖成本體中的基類 TourDeal 和 City
        MATCH (dealClass:owl__Class) WHERE dealClass.uri ENDS WITH "TourDeal"
        MATCH (cityClass:owl__Class) WHERE cityClass.uri ENDS WITH "City"
        
        // 2. 找到它們所有的特化子類（相容未來擴展的其他旅遊類型）
        MATCH (subDealClass:owl__Class)-[:rdfs__subClassOf*0..]->(dealClass)
        MATCH (subCityClass:owl__Class)-[:rdfs__subClassOf*0..]->(cityClass)
        
        // 3. 提取末尾標籤名
        WITH split(subDealClass.uri, "/")[-1] AS subDealLabel, 
             split(subCityClass.uri, "/")[-1] AS subCityLabel
        
        // 4. 反推實例並匹配出發關係，同時拉出價格、天數與折扣
        MATCH (d:Resource)-[r]->(c:Resource)
        WHERE type(r) ENDS WITH "startsFrom"
          AND any(lbl IN labels(d) WHERE lbl ENDS WITH subDealLabel)
          AND any(lbl IN labels(c) WHERE lbl ENDS WITH subCityLabel)
          
        RETURN DISTINCT d.rdfs__label AS deal_name, 
                        c.rdfs__label AS city_name, 
                        d.ns0__priceNZD AS price, 
                        d.ns0__durationDays AS days,
                        d.ns0__discountPercent AS discount
        """
        params = {}
    else:
        print(f"[LOG] 判定结果: 具體城市精準查詢 -> {search_name}")
        query = """
        MATCH (dealClass:owl__Class) WHERE dealClass.uri ENDS WITH "TourDeal"
        MATCH (cityClass:owl__Class) WHERE cityClass.uri ENDS WITH "City"
        
        MATCH (subDealClass:owl__Class)-[:rdfs__subClassOf*0..]->(dealClass)
        MATCH (subCityClass:owl__Class)-[:rdfs__subClassOf*0..]->(cityClass)
        
        WITH split(subDealClass.uri, "/")[-1] AS subDealLabel, 
             split(subCityClass.uri, "/")[-1] AS subCityLabel
        
        // 精準過濾出發城市名稱 (相容 URI 結尾或 rdfs__label)
        MATCH (d:Resource)-[r]->(c:Resource)
        WHERE type(r) ENDS WITH "startsFrom"
          AND (c.uri ENDS WITH $city_name OR c.rdfs__label = $city_name)
          AND any(lbl IN labels(d) WHERE lbl ENDS WITH subDealLabel)
          AND any(lbl IN labels(c) WHERE lbl ENDS WITH subCityLabel)
          
        RETURN DISTINCT d.rdfs__label AS deal_name, 
                        c.rdfs__label AS city_name, 
                        d.ns0__priceNZD AS price, 
                        d.ns0__durationDays AS days,
                        d.ns0__discountPercent AS discount
        """
        params = {"city_name": search_name}

    try:
        with driver.session() as session:
            result = session.run(query, **params)
            records_list = []

            for record in result:
                d_name = record["deal_name"]
                c_name = record["city_name"]
                price = record["price"]
                days = record["days"]
                discount = record["discount"]

                print(
                    f"[LOG] 成功推理召回數據 -> 行程: {d_name}, 出發地: {c_name}, 價格: {price} NZD"
                )

                # 組裝豐富的業務字串回傳給 Agent，讓 Agent 可以做進一步的答覆或篩選
                if is_global_query:
                    records_list.append(
                        f"行程:{d_name}(出發自:{c_name}) | 天數:{days}天 | 價格:{price}NZD | 折扣:{discount}%"
                    )
                else:
                    records_list.append(
                        f"行程:{d_name} | 天數:{days}天 | 價格:{price}NZD | 折扣:{discount}%"
                    )

            print(f"[LOG] 最終返回給 Agent 的數據: {records_list}")
            print("=" * 50 + "\n")
            return records_list

    except Exception as e:
        print(f"[ERROR] 執行失敗: {str(e)}")
        print("=" * 50 + "\n")
        return [f"ERROR: {str(e)}"]


# ================= 3. 啟動內建網路伺服器 =================
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)
