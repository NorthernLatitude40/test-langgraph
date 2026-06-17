from fastapi import FastAPI

def create_api(worker) -> FastAPI:
    """依赖注入 worker 实例，解耦全局变量"""
    api_app = FastAPI()

    @api_app.post("/agent")
    def agent_api_endpoint(payload: dict):
        user_query = payload.get("message")
        config = {"configurable": {"thread_id": "harness_test_thread"}}
        inputs = {"messages": [("user", user_query)]}
        
        # 直接使用传入的 worker，非常安全干净
        result = worker.sync_invoke(inputs, config)
        final_reply = result["messages"][-1].content
        return {"output": final_reply}

    return api_app