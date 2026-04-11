from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
import time
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from typing import Optional

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

from .config import ALLOWED_ORIGINS, REDIS_URL
from .auth import get_user_email_from_token
from .models import ChatRequest, ChatResponse
from .agent import builder
from .database import get_db_connection
from .tools import all_tool_funcs
from .sessions import router as sessions_router

agent = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent
    async with AsyncRedisSaver.from_conn_string(REDIS_URL) as checkpointer:
        agent = builder.compile(checkpointer=checkpointer)
        print("✅ LangGraph agent 已初始化，Redis checkpointer 已启动")
        yield
    print("✅ 应用关闭，Redis checkpointer 已退出")

app = FastAPI(title='电商助手agent', description='电商智能客服助手API服务', lifespan=lifespan)

app.include_router(sessions_router)
app.mount("/static", StaticFiles(directory="static"), name="static")

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=["*"]
)

@app.get('/')
async def root():
    return {'message': '电商助手API服务已启动', 'status': "running"}

@app.post('/chat', response_model=ChatResponse)
async def chat(request: ChatRequest, authorization: Optional[str] = Header(None)):
    global agent
    start_total = time.time()
    try:
        if agent is None:
            raise HTTPException(status_code=500, detail="Agent 尚未初始化")

        print(f"收到聊天请求: {request.message[:50]}...")
        t1 = time.time()

        token_to_use = None
        if request.token:
            token_to_use = request.token
        elif authorization:
            token_to_use = authorization

        user_email = None
        if token_to_use:
            user_email = get_user_email_from_token(token_to_use)
        elif request.user_email:
            user_email = request.user_email

        t2 = time.time()
        print(f"token处理耗时: {t2 - t1:.3f}s")

        messages_for_agent = []
        if request.history:
            for msg in request.history:
                role = msg.get('role')
                content = msg.get('content')
                if not content:
                    continue
                if role == 'user':
                    messages_for_agent.append(HumanMessage(content=content))
                elif role == 'assistant':
                    messages_for_agent.append(AIMessage(content=content))

        if user_email:
            user_context = f"当前登录用户: {user_email}\n用户问题: {request.message}"
        else:
            user_context = f"注意：用户尚未登录。\n用户问题: {request.message}"
        messages_for_agent.append(HumanMessage(content=user_context))

        t3 = time.time()
        print(f"构建上下文耗时: {t3 - t2:.3f}s")

        if request.session_id:
            thread_id = request.session_id
        elif user_email:
            thread_id = f"user_{user_email}"
        else:
            thread_id = f"anon_{int(time.time())}"
        print(f"使用的 thread_id: {thread_id}")

        invoke_start = time.time()
        result = await agent.ainvoke(
            {"messages": messages_for_agent},
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "user_email": user_email,
                    "use_rag": request.use_rag
                }
            }
        )
        invoke_end = time.time()
        print(f"agent.invoke 耗时: {invoke_end - invoke_start:.3f}s")

        response_message = result["messages"][-1]
        response_text = response_message.content

        source = "llm"
        if response_text.endswith("[source=retrieval]"):
            source = "retrieval"
            response_text = response_text.replace("\n[source=retrieval]", "")

        t4 = time.time()
        print(f"提取响应耗时: {t4 - invoke_end:.3f}s")
        print(f"总耗时: {t4 - start_total:.3f}s")
        print(f"回复来源: {source}")

        return ChatResponse(
            response=response_text,
            session_id=thread_id,
            timestamp=datetime.now().isoformat(),
            source=source
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"处理请求时出错: {str(e)}")

@app.get('/health')
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "agent_initialized": agent is not None
    }

@app.get('/tools')
async def list_tools():
    tool_list = [{
        "name": tool.name,
        "description": tool.description,
        "args": str(tool.args)
    } for tool in all_tool_funcs]

    return {
        "tools": tool_list,
        "count": len(tool_list)
    }

@app.get("/debug/token")
async def debug_token(authorization: Optional[str] = Header(None)):
    if not authorization:
        return {"error": "没有提供token", "note": "你的token应该放在Authorization头部，没有'Bearer '前缀"}

    try:
        token_preview = authorization[:50] + "..." if len(authorization) > 50 else authorization
        from .auth import verify_jwt_token
        payload = verify_jwt_token(authorization)

        if payload:
            exp_time = payload.get("exp")
            if exp_time:
                exp_datetime = datetime.fromtimestamp(exp_time)
                is_expired = datetime.now() > exp_datetime
            else:
                is_expired = False
                exp_datetime = None

            return {
                "status": "valid",
                "token_preview": token_preview,
                "payload": payload,
                "user_email": payload.get("username"),
                "expired": is_expired,
                "exp_time": exp_time,
                "exp_datetime": exp_datetime.isoformat() if exp_datetime else None
            }
        else:
            return {
                "status": "invalid",
                "token_preview": token_preview,
                "error": "无法验证token"
            }
    except Exception as e:
        return {
            "status": "error",
            "token_preview": token_preview,
            "error": str(e)
        }

@app.get("/test/connection")
async def test_connection():
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM user")
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            return {
                "status": "success",
                "database": "connected",
                "user_count": result['count']
            }
        else:
            return {
                "status": "error",
                "database": "disconnected"
            }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }