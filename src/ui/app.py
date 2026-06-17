import streamlit as st
import traceback

def run_ui(worker):
    """
    負責 Streamlit 介面渲染。
    接收重構後的 AgentWorker 實例，透過純同步流程（sync_invoke）
    將使用者請求安全地投遞到背景獨立執行緒的 Event Loop 中執行。
    """
    st.set_page_config(page_title="官方智慧售票 Agent (RAG+MCP網路版)", page_icon="🎫")
    st.title("🎫 官方智慧售票 Agent")
    st.caption("🚀 實戰：外掛 AnythingLLM RAG ＋ 本地 MySQL MCP (雙 Uvicorn 連線版)")

    # ================= 1. 初始化 Streamlit 內建的聊天歷史記憶庫 =================
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {
                "role": "assistant", 
                "content": "您好！我已經成功外掛了 AnythingLLM 知識庫與網路版 MySQL 資料庫。請隨時提問客服問題或要求我跑評估測試集。"
            }
        ]

    # ================= 2. 渲染歷史對話訊息 =================
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # ================= 3. 處理使用者輸入與同步調用流程 =================
    if user_query := st.chat_input("請輸入您的問題..."):
        # 立即將使用者的輸入渲染在網頁上，並寫入歷史紀錄
        with st.chat_message("user"):
            st.write(user_query)
        st.session_state.chat_history.append({"role": "user", "content": user_query})
        
        # 建立 AI 的對話氣泡
        with st.chat_message("assistant"):
            # 引入 st.spinner 動畫，提供良好的使用者體驗
            with st.spinner("Agent 決策中..."):
                config = {"configurable": {"thread_id": "ticket_agent_stream_network"}}
                inputs = {"messages": [("user", user_query)]}
                
                try:
                    # 🌟 核心：調用傳入的 worker 實例進行同步橋接
                    result = worker.sync_invoke(inputs, config)
                    
                    # 解析 AgentCore 返回的最後一則模型回覆
                    final_reply = result["messages"][-1].content
                    
                    # 將結果呈現在 UI 上，並寫入歷史紀錄
                    st.write(final_reply)
                    st.session_state.chat_history.append({"role": "assistant", "content": final_reply})
                    
                except Exception as final_error:
                    # 在後台控制台列印詳細的錯誤軌跡（Traceback），方便開發者 Debug
                    print("❌ [Agent 執行階段崩潰] 詳細錯誤軌跡如下：")
                    traceback.print_exc() 
                    
                    # 同時在網頁前端彈出醒目的紅框錯誤提示，防止介面卡死死白
                    st.error(f"🛑 系統錯誤詳細資訊：{str(final_error)}")