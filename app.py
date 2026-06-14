import os
from dotenv import load_dotenv
from typing import Annotated
from typing_extensions import TypedDict

import httpx
from bs4 import BeautifulSoup
import streamlit as st

from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI  # 💡 引入 ChatOpenAI 來對接 OpenRouter
from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver

# ================= 1. 初始化與環境設定 =================
load_dotenv()

# 💡 從環境變數讀取兩組不同的金鑰
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

st.set_page_config(page_title="官方智慧售票 Agent (RAG自動切換版)", page_icon="🎫")
st.title("🎫 官方智慧售票 Agent")
st.caption("🚀 實戰：外掛 AnythingLLM RAG 技能 ＋ 雙模型智慧雙活切換")

ANYTHINGLLM_BASE_URL = "http://localhost:3001/api/v1"
ANYTHINGLLM_API_KEY = "5CWGCCF-QZMMSTT-HA2ESKA-DG24WBH"  
WORKSPACE_SLUG = "ticketrules"                  

# ================= 2. 定義 Agent 的技能 =================

@tool
def search_official_knowledge_base(query: str) -> str:
    """當使用者詢問關於售票規則、退換票政策、實名制驗證、場館攜帶規定等官方政策時，呼叫此工具進行知識庫檢索。"""
    url = f"{ANYTHINGLLM_BASE_URL}/workspace/{WORKSPACE_SLUG}/chat"
    headers = {
        "Authorization": f"Bearer {ANYTHINGLLM_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "message": query,
        "mode": "query" ,
        "model": "current",     
        "temperature": 0.0    
    }

    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=15)
        if response.status_code == 200:
            result = response.json()
            sources = result.get("sources", [])
            
            # 優先從 sources 陣列撈出原汁原味的文件段落，不依賴 AnythingLLM 大模型
            if sources:
                retrieved_texts = []
                for i, src in enumerate(sources, 1):
                    text_chunk = src.get("text", "").strip()
                    if text_chunk:
                        retrieved_texts.append(f"[文件片段 {i}] {text_chunk}")
                return "【官方知識庫檢索結果】如下：\n\n" + "\n\n".join(retrieved_texts)
            
            text_response = result.get("textResponse", "")
            return f"【官方知識庫檢索結果】如下：\n{text_response}"
        else:
            return f"知識庫連線異常，錯誤碼: {response.status_code}"
    except Exception as e:
        return f"無法讀取官方知識庫，原因: {str(e)}"

@tool
def get_weather(city: str) -> str:
    """獲取指定城市的即時天氣資訊。"""
    city_lower = city.lower()
    if "東京" in city_lower or "tokyo" in city_lower:
        return "東京目前天氣：晴朗，氣溫 18 度，非常適合看戶外演唱會。"
    elif "台北" in city_lower or "taipei" in city_lower:
        return "台北目前天氣：陰天，氣溫 22 度，體感舒適。"
    return f"暫時找不到 {city} 的天氣資訊。"

# ================= 3. 組裝 LangGraph 工作流 (含自動切換邏輯) =================
@st.cache_resource
def init_langgraph_agent_with_rag():
    tools = [get_weather, search_official_knowledge_base]
    tool_node = ToolNode(tools)

    class State(TypedDict):
        messages: Annotated[list, add_messages]

    # --- 💡 初始化兩個模型實例 ---
    # 1. 主要模型：Gemini
    gemini_model = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash", 
        api_key=GEMINI_API_KEY, 
        max_tokens=512,
        temperature=0
    ).bind_tools(tools)
    
    # 2. 備用模型：OpenRouter (使用 OpenAI 相容格式對接)
    openrouter_model = ChatOpenAI(
        model="google/gemma-4-31b-it:free",  # 👈 可自由更換 OpenRouter 支援的模型代碼
        openai_api_key=OPENROUTER_API_KEY,
        openai_api_base="https://openrouter.ai/api/v1",
        max_tokens=512,
        temperature=0
    ).bind_tools(tools)

    def call_model(state: State):
        system_message = (
            "你現在是官方售票網站的智慧客服。當使用者詢問退票、規定等問題時，"
            "你必須優先呼叫 `search_official_knowledge_base` 工具來查閱官方政策，"
            "並嚴格根據工具返回的內容來回答，不可以自己瞎編退票規定。"
        )
        messages_with_system = [("system", system_message)] + state["messages"]
        
        # --- 💡 核心：Try-Except 智慧切換容錯機制 ---
        try:
            print("🔄 正在嘗試使用 [主要模型: Gemini] 處理請求...")
            response = gemini_model.invoke(messages_with_system)
            print("🎉 [Gemini] 請求成功！")
            return {"messages": [response]}
            
        except Exception as gemini_error:
            print(f"⚠️ [Gemini] 發生異常或額度用盡: {gemini_error}")
            
            if OPENROUTER_API_KEY:
                try:
                    print("🚀 啟動備援機制，切換至 [備用模型: OpenRouter]...")
                    response = openrouter_model.invoke(messages_with_system)
                    print("🎉 [OpenRouter] 備援請求成功！")
                    return {"messages": [response]}
                except Exception as router_error:
                    print(f"🛑 [OpenRouter] 備用模型也失敗: {router_error}")
                    raise RuntimeError("所有配置的 AI 模型金鑰均已失效或發生錯誤。")
            else:
                print("❌ 未偵測到備用的 OPENROUTER_API_KEY 配置。")
                raise gemini_error

    workflow = StateGraph(State)
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node)
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", tools_condition)
    workflow.add_edge("tools", "agent")
    
    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)

app = init_langgraph_agent_with_rag()

# ================= 4. Streamlit 介面渲染 =================
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [
        {"role": "assistant", "content": "您好！我已經成功外掛了 AnythingLLM 的官方知識庫。具備「雙 Key 自動降級切換機制」，當主要 API Token 額度用完時會自動切換，請放心提問！"}
    ]

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

if user_query := st.chat_input("請輸入您的問題..."):
    with st.chat_message("user"):
        st.write(user_query)
    st.session_state.chat_history.append({"role": "user", "content": user_query})
    
    with st.chat_message("assistant"):
        with st.spinner("Agent 正在翻閱知識庫並組織回答中..."):
            config = {"configurable": {"thread_id": "rag_room_1"}}
            inputs = {"messages": [("user", user_query)]}
            
            try:
                result = app.invoke(inputs, config)
                final_reply = result["messages"][-1].content
                st.write(final_reply)
                st.session_state.chat_history.append({"role": "assistant", "content": final_reply})
            except Exception as final_error:
                error_msg = f"🛑 系統崩潰：{str(final_error)}，請聯絡管理員檢查 API 額度。"
                st.error(error_msg)