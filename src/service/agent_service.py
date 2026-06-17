from fastapi import FastAPI
import asyncio

from src.mcp_client import MCPClient
from src.core.agent import Agent

app = FastAPI()

mcp_client = MCPClient()
agent = None


@app.on_event("startup")
async def startup():
    global agent

    await mcp_client.connect()

    agent = Agent(mcp_client.get_tools())

    print("✅ Agent Service started")


@app.post("/chat")
async def chat(payload: dict):
    user_query = payload["message"]

    result = agent.app.invoke(
        {"messages": [("user", user_query)]},
        {"configurable": {"thread_id": "api"}}
    )

    return {
        "output": result["messages"][-1].content
    }