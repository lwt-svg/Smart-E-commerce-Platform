from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
import re
import json
import time
import uuid
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from datetime import datetime
from typing import Optional

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

from my_llm import llm
from .config import ALLOWED_ORIGINS, REDIS_URL, LANGFUSE_ENABLED, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
from .auth import get_user_email_from_token
from .models import ChatRequest, ChatResponse
from .agent import builder, detect_intent
from .database import get_db_connection
from .tools import all_tool_funcs
from .sessions import router as sessions_router
from .token_tracker import token_tracker

agent = None
langfuse_handler = None

# ======================= LangFuse 初始化 =======================
# langfuse 4.x: 需要先创建 Langfuse client，CallbackHandler 会自动使用
if LANGFUSE_ENABLED and LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY:
    try:
        from langfuse import Langfuse
        from langfuse.langchain import CallbackHandler
        # 1. 初始化 Langfuse client
        Langfuse(
            public_key=LANGFUSE_PUBLIC_KEY,
            secret_key=LANGFUSE_SECRET_KEY,
            host=LANGFUSE_HOST,
        )
        # 2. 创建 CallbackHandler（自动使用已初始化的 client）
        langfuse_handler = CallbackHandler()
        print(f"✅ LangFuse 已启用，host: {LANGFUSE_HOST}")
    except ImportError:
        print("⚠️ langfuse 包未安装，请运行: pip install langfuse")
        langfuse_handler = None
    except Exception as e:
        print(f"⚠️ LangFuse 初始化失败: {e}")
        langfuse_handler = None
else:
    print("ℹ️ LangFuse 未启用（设置 LANGFUSE_ENABLED=true 开启）")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：初始化Redis checkpointer（连不上则降级到内存模式）"""
    global agent
    try:
        async with AsyncRedisSaver.from_conn_string(REDIS_URL) as checkpointer:
            agent = builder.compile(checkpointer=checkpointer)
            print("✅ LangGraph agent 已初始化，Redis checkpointer 已启动")
            if langfuse_handler:
                print("✅ LangFuse 回调处理器已注入 Agent 链路")
            yield
        print("✅ 应用关闭，Redis checkpointer 已退出")
    except Exception as e:
        print(f"⚠️ Redis 连接失败: {e}")
        print("⚠️ 降级到内存模式（MemorySaver），会话状态不会持久化！")
        from langgraph.checkpoint.memory import MemorySaver
        agent = builder.compile(checkpointer=MemorySaver())
        print("✅ LangGraph agent 已初始化（内存模式）")
        if langfuse_handler:
            print("✅ LangFuse 回调处理器已注入 Agent 链路")
        yield
        print("✅ 应用关闭")

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

        # 构建 Agent 调用配置
        agent_config = {
            "configurable": {
                "thread_id": thread_id,
                "user_email": user_email,
                "use_rag": request.use_rag
            }
        }

        # 构建callbacks列表
        callbacks = []

        # 注入 LangFuse 回调处理器，实现全链路追踪
        if langfuse_handler:
            callbacks.append(langfuse_handler)

        # 注入 Token 追踪器，记录每次LLM调用的token消耗
        user_intent = detect_intent(request.message)
        token_tracker.set_trace_info(trace_id=thread_id, intent=user_intent)
        callbacks.append(token_tracker)

        if callbacks:
            agent_config["callbacks"] = callbacks

        result = await agent.ainvoke(
            {"messages": messages_for_agent},
            config=agent_config
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

        # 打印本次请求的Token消耗摘要
        token_tracker.print_summary()

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


# ======================= SSE 流式输出 =======================

# 工具名称友好化映射
TOOL_DISPLAY_NAMES = {
    "search_products_by_category": "搜索商品",
    "recommend_products_by_budget": "推荐商品",
    "get_product_comments": "查询评论",
    "get_product_score_summary": "汇总评分",
    "get_product_price": "查询价格",
    "check_user_cart": "查询购物车",
    "check_user_orders": "查询订单",
    "get_order_details": "查询订单详情",
    "generate_purchase_recommendation": "生成购买建议",
    "analyze_product_sentiment": "分析商品口碑",
    "search_positive_points": "汇总优点",
    "search_negative_points": "汇总缺点",
    "compare_product_sentiments": "对比商品口碑",
    "checkout_cart": "结算购物车",
}

# 结构化数据类型集合（这些类型的JSON会作为structured_data单独传给前端）
STRUCTURED_TYPES = {
    "product_list", "score_summary", "comment_list",
    "purchase_recommendation", "sentiment_analysis",
    "positive_points", "negative_points", "sentiment_comparison"
}


def _sse_format(data: dict) -> str:
    """格式化为SSE事件"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _build_intro_prompt(structured_data: dict, intent: str, user_query: str) -> str:
    """根据结构化数据类型构建引导文本生成提示，用于SSE流式输出"""
    data_type = structured_data.get("type", "")
    n = len(structured_data.get("products", []))

    if data_type == "product_list":
        return f"用户查询'{user_query}'，找到了{n}款商品。请用中文一句话简短回复（不超过25字），直接说结果。例如：为您找到以下{n}款商品："
    elif data_type == "score_summary":
        return f"用户查询商品评分，找到了{n}款商品的评分。请用中文一句话简短回复（不超过25字）。例如：以下是商品评分摘要："
    elif data_type == "comment_list":
        name = structured_data.get("product_name", "")
        total = structured_data.get("total_comments", 0)
        return f"用户查询{name}的评论，共{total}条。请用中文一句话简短回复（不超过25字）。"
    elif data_type == "purchase_recommendation":
        return "用户查询购买建议。请用中文一句话简短回复（不超过25字）。例如：以下是综合购买建议："
    elif data_type == "sentiment_analysis":
        return "用户查询口碑分析。请用中文一句话简短回复（不超过25字）。例如：以下是口碑分析结果："
    elif data_type == "positive_points":
        return "用户查询商品优点。请用中文一句话简短回复（不超过25字）。例如：以下是商品主要优点："
    elif data_type == "negative_points":
        return "用户查询商品缺点。请用中文一句话简短回复（不超过25字）。例如：以下是商品主要缺点："
    elif data_type == "sentiment_comparison":
        return "用户查询商品对比。请用中文一句话简短回复（不超过25字）。例如：以下是商品口碑对比："
    return ""


def _build_fallback_intro(structured_data: dict, user_query: str) -> str:
    """LLM生成失败时的降级引导文本"""
    data_type = structured_data.get("type", "")
    n = len(structured_data.get("products", []))
    if data_type == "product_list":
        return f"为您找到以下 {n} 款商品："
    elif data_type == "score_summary":
        return f"以下是 {n} 款商品的评分摘要："
    elif data_type == "comment_list":
        name = structured_data.get("product_name", "")
        total = structured_data.get("total_comments", 0)
        return f"以下是 {name} 的 {total} 条评论："
    elif data_type == "purchase_recommendation":
        return "以下是综合购买建议："
    elif data_type == "sentiment_analysis":
        return "以下是口碑分析结果："
    elif data_type == "positive_points":
        return "以下是商品主要优点："
    elif data_type == "negative_points":
        return "以下是商品主要缺点："
    elif data_type == "sentiment_comparison":
        return "以下是商品口碑对比："
    return "查询结果如下："


def _extract_structured_response(text: str) -> dict:
    """
    从响应文本中提取结构化数据。
    电商Agent的工具返回JSON字符串，需要分离为：
    - intro: JSON前的文本说明（可能为空）
    - structured_data: 解析后的JSON对象
    - is_structured: 是否包含结构化数据
    
    返回: {"intro": str, "structured_data": dict|None, "is_structured": bool}
    """
    if not text:
        return {"intro": "", "structured_data": None, "is_structured": False}

    text = text.strip()

    # 尝试直接解析为JSON（工具返回的纯JSON）
    try:
        data = json.loads(text)
        if isinstance(data, dict) and data.get("type") in STRUCTURED_TYPES:
            return {"intro": "", "structured_data": data, "is_structured": True}
    except:
        pass

    # 尝试提取文本中最后一个JSON对象（可能有前缀文本）
    # 用栈匹配找最外层 {...}
    stack = []
    start = -1
    last_valid_json = None
    last_json_start = -1
    last_json_end = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if not stack:
                start = i
            stack.append(ch)
        elif ch == '}':
            if stack:
                stack.pop()
                if not stack and start != -1:
                    candidate = text[start:i + 1]
                    try:
                        parsed = json.loads(candidate)
                        if isinstance(parsed, dict) and parsed.get("type") in STRUCTURED_TYPES:
                            last_valid_json = parsed
                            last_json_start = start
                            last_json_end = i + 1
                    except:
                        pass
                    start = -1

    if last_valid_json is not None:
        intro = text[:last_json_start].strip()
        # 清理intro中的代码块标记
        intro = re.sub(r'```json\s*', '', intro).strip()
        intro = re.sub(r'```\s*$', '', intro).strip()
        return {"intro": intro, "structured_data": last_valid_json, "is_structured": True}

    # 纯文本响应
    # 清理可能的代码块
    cleaned = re.sub(r'```json\s*[\s\S]*?```', '', text).strip()
    cleaned = re.sub(r'```\s*[\s\S]*?```', '', cleaned).strip()
    return {"intro": cleaned, "structured_data": None, "is_structured": False}


@app.post('/chat/stream')
async def chat_stream(request: ChatRequest, authorization: Optional[str] = Header(None)):
    """
    SSE流式聊天接口
    事件类型:
    - start: 开始处理
    - intent: 意图识别结果
    - tool_start: 工具开始执行
    - tool_end: 工具执行完成
    - chunk: LLM输出片段（普通对话）
    - done: 处理完成（含完整结果）
    - error: 出错
    """
    global agent

    async def event_generator():
        try:
            if agent is None:
                yield _sse_format({"type": "error", "message": "Agent 尚未初始化"})
                return

            print(f"\n========== SSE 电商请求 ==========")
            print(f"用户问题: {request.message[:80]}...")

            # 1. 处理token
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

            # 2. 构造上下文
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

            # 3. 生成session_id（用UUID避免状态污染）
            if request.session_id:
                thread_id = request.session_id
            else:
                thread_id = f"ecom_{uuid.uuid4().hex[:12]}"

            # 4. 识别意图
            user_intent = detect_intent(request.message)

            yield _sse_format({
                "type": "start",
                "message": "正在处理您的请求..."
            })
            yield _sse_format({
                "type": "intent",
                "message": user_intent,
                "intent": user_intent
            })

            # 5. 构建Agent配置
            agent_config = {
                "configurable": {
                    "thread_id": thread_id,
                    "user_email": user_email,
                    "use_rag": request.use_rag
                }
            }

            callbacks = []
            if langfuse_handler:
                callbacks.append(langfuse_handler)
            token_tracker.set_trace_info(trace_id=thread_id, intent=user_intent)
            callbacks.append(token_tracker)
            if callbacks:
                agent_config["callbacks"] = callbacks

            # 6. 流式执行Agent
            final_response = ""
            source = "llm"
            in_code_block = False

            async for event in agent.astream_events(
                {"messages": messages_for_agent},
                config=agent_config,
                version="v2"
            ):
                kind = event["event"]
                name = event.get("name", "")
                data = event.get("data", {})

                # 链路错误（LLM调用失败、429限速等）
                if kind == "on_chain_error":
                    error_msg = str(data.get("error", "未知错误"))
                    print(f"[SSE错误] on_chain_error: {error_msg}")
                    if "429" in error_msg or "速率限制" in error_msg:
                        friendly_msg = "AI模型调用频率过高，请稍等1分钟后重试"
                    else:
                        friendly_msg = f"处理过程出错: {error_msg[:200]}"
                    yield _sse_format({"type": "error", "message": friendly_msg})
                    return

                # 工具开始
                elif kind == "on_tool_start":
                    source = "tool"
                    display_name = TOOL_DISPLAY_NAMES.get(name, name)
                    yield _sse_format({
                        "type": "tool_start",
                        "message": f"正在{display_name}...",
                        "tool": name
                    })

                # 工具结束
                elif kind == "on_tool_end":
                    display_name = TOOL_DISPLAY_NAMES.get(name, name)
                    yield _sse_format({
                        "type": "tool_end",
                        "message": f"{display_name}完成",
                        "tool": name
                    })

                # LLM流式输出（普通对话部分）
                elif kind == "on_chat_model_stream":
                    chunk = data.get("chunk", "")
                    if hasattr(chunk, "content") and chunk.content:
                        content = chunk.content
                        if isinstance(content, list):
                            text_part = ""
                            for part in content:
                                if isinstance(part, dict) and "text" in part:
                                    text_part += part["text"]
                                elif isinstance(part, str):
                                    text_part += part
                            content = text_part
                        if content and isinstance(content, str):
                            # 过滤JSON代码块
                            if "```" in content:
                                if not in_code_block:
                                    parts = content.split("```")
                                    for i, part in enumerate(parts):
                                        if i % 2 == 0:
                                            if part.strip():
                                                final_response += part
                                                yield _sse_format({"type": "chunk", "message": part})
                                        else:
                                            in_code_block = True
                                else:
                                    if "```" in content:
                                        in_code_block = False
                            elif in_code_block:
                                pass
                            else:
                                final_response += content
                                yield _sse_format({"type": "chunk", "message": content})

            # 清理最终响应中的JSON代码块
            final_response = re.sub(r'```json\s*[\s\S]*?```', '', final_response).strip()
            final_response = re.sub(r'```\s*[\s\S]*?```', '', final_response).strip()

            # 如果流式没收集到内容（工具调用场景，LLM不分片输出），从最终状态获取
            if not final_response:
                try:
                    final_state = await agent.aget_state(agent_config)
                    if final_state and final_state.values:
                        msgs = final_state.values.get("messages", [])
                        if msgs:
                            last_msg = msgs[-1]
                            if hasattr(last_msg, "content"):
                                final_response = last_msg.content or ""
                except:
                    pass

            # 提取结构化数据
            extracted = _extract_structured_response(final_response)
            intro_text = extracted["intro"]
            structured_data = extracted["structured_data"]

            # 如果是结构化数据，source设为tool
            if structured_data:
                source = "tool"
                # 如果没有引导文本，用LLM流式生成（让前端有逐字输出体验）
                if not intro_text:
                    intro_prompt = _build_intro_prompt(structured_data, user_intent, request.message)
                    if intro_prompt:
                        try:
                            async for chunk in llm.astream([
                                SystemMessage(content="你是电商客服助手，请用中文一句话简短回复。"),
                                HumanMessage(content=intro_prompt)
                            ]):
                                if chunk.content:
                                    intro_text += chunk.content
                                    yield _sse_format({"type": "chunk", "message": chunk.content})
                        except Exception as e:
                            print(f"[SSE] 引导文本生成失败: {e}")
                            # 降级：用固定模板
                            intro_text = _build_fallback_intro(structured_data, request.message)
                response_text = intro_text
            else:
                response_text = final_response

            # 如果还是没有内容，给友好默认回复
            if not response_text and not structured_data:
                response_text = "抱歉，处理过程中遇到了一些问题，请稍后重试。如果持续出现此问题，可能是AI模型调用频率受限，请等待1-2分钟后再试。"

            print(f"\n流式输出完成，回复长度: {len(response_text)}, structured: {'有' if structured_data else '无'}")
            print(f"回复来源: {source}, 意图: {user_intent}")

            token_tracker.print_summary()

            yield _sse_format({
                "type": "done",
                "response": response_text,
                "structured_data": structured_data,
                "source": source,
                "intent": user_intent,
                "session_id": thread_id
            })

        except Exception as e:
            import traceback
            traceback.print_exc()
            error_str = str(e)
            if "429" in error_str or "速率限制" in error_str:
                friendly_msg = "AI模型调用频率过高（429限速），请等待1-2分钟后重试"
            elif "timeout" in error_str.lower() or "超时" in error_str:
                friendly_msg = "请求超时，AI模型响应时间过长，请稍后重试"
            else:
                friendly_msg = f"处理过程出错: {error_str[:200]}"
            yield _sse_format({"type": "error", "message": friendly_msg})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get('/health')
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "agent_initialized": agent is not None
    }

@app.get('/token-usage')
async def token_usage_report():
    """获取Token消耗统计报告"""
    summary = token_tracker.get_summary()
    # 同时保存到文件
    token_tracker.save_report()
    return summary

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