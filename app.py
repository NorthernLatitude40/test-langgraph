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

# 🛠️ 手動填入你的環境變數進行測試
ANYTHINGLLM_BASE_URL = "http://localhost:3001/api/v1"
ANYTHINGLLM_API_KEY = "5CWGCCF-QZMMSTT-HA2ESKA-DG24WBH"  # 👈 記得換成你在後台生成的 Key
WORKSPACE_SLUG = "ticketrules"                  # 👈 換成你建立的工作區名稱 (通常是英文小寫底線)

# ================= 2. 定義 Agent 的技能 (新增 AnythingLLM RAG 工具) =================

@tool
def search_official_knowledge_base(query: str) -> str:
    """當使用者詢問關於售票規則、退換票政策、實名制驗證、場館攜帶規定等官方政策時，呼叫此工具進行知識庫檢索。"""
    
    # 這是 AnythingLLM 官方文件提供的對話/檢索 API 接口
    url = f"{ANYTHINGLLM_BASE_URL}/workspace/{WORKSPACE_SLUG}/chat"
    
    headers = {
        "Authorization": f"Bearer {ANYTHINGLLM_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # 我們這裡使用 "query" 模式，意思是只撈取最相關的文檔片段，不讓 AnythingLLM 內部的大模型幫我們組織語言
    # 這樣可以把撈出來的原汁原味官方規定，交給我們 LangGraph 裡的 Gemini 來做最精準的判斷
    payload = {
        "message": query,
        "mode": "query" ,
        "model": "current",     # 👈 強制指定使用當前工作區設定的模型
        "temperature": 0.0    
    }

    print(f"正在請求 URL: {url}")
    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=15)
        print(f"狀態碼: {response.status_code}")
        print("原始回應內容：")
        print(response.text) # 觀察這裏，看 AnythingLLM 到底回傳了什麼
        if response.status_code == 200:
            result = response.json()
            # 撈出 AnythingLLM 幫我們從 PDF/文件中找到的官方段落
            text_response = result.get("textResponse", "")
            return f"【官方知識庫檢索結果】如下：\n{text_response}"
        else:
            return f"知識庫連線異常，錯誤碼: {response.status_code}，請檢查 API Key 是否正確。"
    except Exception as e:
        print(f"連線失敗: {e}")
        return f"無法讀取官方知識庫，原因: {str(e)}。請確認 AnythingLLM 軟體是否有開啟並在運行中。"

@tool
def get_weather(city: str) -> str:
    """獲取指定城市的即時天氣資訊。"""
    city_lower = city.lower()
    if "東京" in city_lower or "tokyo" in city_lower:
        return "東京目前天氣：晴朗，氣溫 18 度，非常適合看戶外演唱會。"
    elif "台北" in city_lower or "taipei" in city_lower:
        return "台北目前天氣：陰天，氣溫 22 度，體感舒適。"
    return f"暫時找不到 {city} 的天氣資訊。"

# ================= 3. 組裝 LangGraph 工作流 =================
@st.cache_resource
def init_langgraph_agent_with_rag():
    # 🌟 核心：把我們剛寫好的 AnythingLLM 技能，跟天氣工具一起放進技能包！
    tools = [get_weather, search_official_knowledge_base]
    tool_node = ToolNode(tools)

    class State(TypedDict):
        messages: Annotated[list, add_messages]

    # --- 💡 初始化兩個模型實例 ---
    # 1. 主要模型：Gemini
    gemini_model = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash", 
        api_key=GEMINI_API_KEY, 
        temperature=0
    ).bind_tools(tools)

    # 2. 備用模型：OpenRouter (使用 OpenAI 相容格式對接)
    openrouter_model = ChatOpenAI(
        model="google/gemini-2.5-flash",  # 👈 可自由更換 OpenRouter 支援的模型代碼
        openai_api_key=OPENROUTER_API_KEY,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0
    ).bind_tools(tools)

    # 我們可以使用更強的系統提示詞 (System Prompt) 來綁定人設
    # model = ChatGoogleGenerativeAI(model="gemini-3.5-flash", temperature=0)
    
    # 讓模型知道他有這兩個工具可以用
    # model_with_tools = model.bind_tools(tools)

    def call_model(state: State):
        # 悄悄注入一個系統提示詞，規定它必須遵守知識庫的規定
        system_message = (
            "你現在是官方售票網站的智慧客服。當使用者詢問退票、規定等問題時，"
            "你必須優先呼叫 `search_official_knowledge_base` 工具來查閱官方政策，"
            "並嚴格根據工具返回的內容來回答，不可以自己瞎編退票規定。"
        )
        messages_with_system = [("system", system_message)] + state["messages"]
     #   return {"messages": [model_with_tools.invoke(messages_with_system)]}

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
        with st.spinner("Agent 正在翻閱 AnythingLLM 知識庫中..."):
            config = {"configurable": {"thread_id": "rag_room_1"}}
            inputs = {"messages": [("user", user_query)]}
            
            result = app.invoke(inputs, config)
            final_reply = result["messages"][-1].content
            
            st.write(final_reply)
            st.session_state.chat_history.append({"role": "assistant", "content": final_reply})