import re
import json
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
import uuid

import redis.asyncio as redis
from langgraph.graph import StateGraph, MessagesState, START, END
from langchain_core.messages import SystemMessage, AIMessage, ToolMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from my_llm import llm
from .tools import all_tool_funcs
from .schema import get_database_schema
from .config import REDIS_URL
from .profile import profile_manager


# ================== 配置 ==================
SESSION_TTL = 1800
MAX_RECENT_MESSAGES = 5
MAX_CONTEXT_MESSAGES = 6
MAX_RECOMMENDED_PRODUCTS = 10

tools = all_tool_funcs
llm_with_tools = llm.bind_tools(tools)
SCHEMA_INFO = get_database_schema()
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

print("当前 tools:", [getattr(t, "name", str(t)) for t in tools])


# ================== Redis 会话 ==================
async def get_session_cache(session_id: str) -> Optional[Dict[str, Any]]:
    key = f"session:{session_id}"
    data = await redis_client.get(key)
    return json.loads(data) if data else None


async def update_session_cache(session_id: str, messages: List[Any], metadata: Dict[str, Any] = None):
    serializable_msgs = []
    for msg in messages[-MAX_RECENT_MESSAGES * 2:]:
        if isinstance(msg, (SystemMessage, AIMessage, ToolMessage, HumanMessage)):
            role = "system" if isinstance(msg, SystemMessage) else \
                   "assistant" if isinstance(msg, AIMessage) else \
                   "tool" if isinstance(msg, ToolMessage) else "user"
            serializable_msgs.append({"role": role, "content": msg.content})
        else:
            serializable_msgs.append({"role": "unknown", "content": str(msg)})

    cache_data = {
        "recent_messages": serializable_msgs,
        "metadata": metadata or {},
        "last_updated": datetime.now().isoformat()
    }
    await redis_client.setex(f"session:{session_id}", SESSION_TTL, json.dumps(cache_data, ensure_ascii=False))


def convert_redis_messages_to_langchain(msgs: List[Dict[str, str]]) -> List:
    result = []
    for m in msgs:
        role = m.get("role")
        content = m.get("content", "")
        if role == "user":
            result.append(HumanMessage(content=content))
        elif role == "assistant":
            result.append(AIMessage(content=content))
        elif role == "tool":
            result.append(ToolMessage(content=content, tool_call_id=""))
        elif role == "system":
            result.append(SystemMessage(content=content))
        else:
            result.append(HumanMessage(content=str(m)))
    return result


# ================== 系统提示词 ==================
def build_system_prompt(email: Optional[str] = None, user_profile_section: str = "") -> str:
    profile_prompt = ""
    if user_profile_section:
        profile_prompt = f"""
{user_profile_section}
"""

    return f"""你是一个专业的电商客服助手。
{profile_prompt}
【强规则】
- 用户说"华为平板"，必须识别为 brand=华为, category=平板，不能误判成华为手机。
- 用户说"苹果平板 / iPad"，必须识别为 brand=苹果, category=平板。
- 用户问"8000左右的苹果手机 / 5000左右的华为手机"，必须走预算推荐，不要走单品价格查询。
- 用户问"第二款商品评价咋样 / 第三个怎么样 / 第一款价格呢"，必须优先绑定上一轮推荐列表。
- 用户问评论/评分/价格时，优先使用当前选中的商品；如果有"第几款"，必须按推荐列表定位。
- 评论、评分、价格查询时，优先用 sku_id 精准查，禁止模糊查错商品。
- 不要把华为、荣耀、小米等别的品牌串到苹果查询里。
- 如果用户追问"评论呢 / 评分呢 / 价格呢 / 它呢 / 这个呢"，默认指向当前选中的商品。
- 查询购物车、订单、结算、支付、取消订单时，必须走对应订单/购物车工具，不要走商品搜索。
- 只用用户真实问题，不要把登录信息、历史消息拼进去作为查询条件。
- 如果用户画像中有明确的品牌偏好，在推荐时可以优先考虑该品牌，但仍需满足用户当前需求。

【意图】
1. 查商品 -> search_products_by_category
2. 查价格 -> get_product_price
3. 查评分 -> get_product_score_summary
4. 查评论 -> get_product_comments
5. 预算推荐 -> recommend_products_by_budget
6. 查询购物车 -> check_user_cart
7. 查询订单 -> check_user_orders
8. 查询订单详情 -> get_order_details
9. 结算购物车 -> checkout_cart
10. 查优点 -> search_positive_points
11. 查缺点 -> search_negative_points
12. 综合评价 -> analyze_product_sentiment
13. 购买建议 -> generate_purchase_recommendation

数据库结构：
{SCHEMA_INFO}

请始终用中文，简洁专业地回复。
"""


# ================== State ==================
class AgentState(MessagesState):
    last_recommendations: List[Dict[str, Any]]
    current_selected_product: Optional[Dict[str, Any]]
    intent: Optional[str]


# ================== 工具函数 ==================
def get_last_user_text(state: AgentState) -> str:
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            return msg.content or ""
    return ""


def extract_user_query(text: str) -> str:
    if not text:
        return ""
    text = str(text).strip()
    m = re.search(r"用户问题[:：]\s*(.*)", text, re.S)
    if m:
        return m.group(1).strip()

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned = []
    for line in lines:
        if line.startswith("当前登录用户"):
            continue
        if line.startswith("用户问题"):
            line = re.sub(r"^用户问题[:：]\s*", "", line).strip()
        cleaned.append(line)
    return " ".join(cleaned).strip()


def extract_trade_no(text: str) -> Optional[str]:
    if not text:
        return None
    m = re.search(r"(ORD\d{10,})", text, re.I)
    return m.group(1) if m else None


def parse_category(text: str) -> Optional[str]:
    if not text:
        return None
    t = text.lower()
    if any(k in t for k in ["平板", "pad", "tablet", "matepad", "ipad"]):
        return "平板"
    if any(k in t for k in ["手机", "phone", "iphone"]):
        return "手机"
    if any(k in t for k in ["电脑", "笔记本", "laptop", "notebook"]):
        return "电脑"
    if any(k in t for k in ["耳机", "耳麦"]):
        return "耳机"
    if any(k in t for k in ["手表", "watch"]):
        return "手表"
    if any(k in t for k in ["手环", "band"]):
        return "手环"
    if any(k in t for k in ["音箱", "speaker"]):
        return "音箱"
    if any(k in t for k in ["路由器", "router"]):
        return "路由器"
    if any(k in t for k in ["显示器", "monitor"]):
        return "显示器"
    return None


def parse_brand(text: str) -> Optional[str]:
    if not text:
        return None
    t = text.lower()
    if any(k in t for k in ["苹果", "iphone", "ipad"]):
        return "苹果"
    if any(k in t for k in ["华为", "huawei"]):
        return "华为"
    if any(k in t for k in ["小米", "redmi", "mi "]):
        return "小米"
    if any(k in t for k in ["荣耀", "honor"]):
        return "荣耀"
    if "oppo" in t:
        return "OPPO"
    if "vivo" in t:
        return "vivo"
    if any(k in t for k in ["三星", "samsung"]):
        return "三星"
    if any(k in t for k in ["联想", "lenovo"]):
        return "联想"
    if any(k in t for k in ["华硕", "asus"]):
        return "华硕"
    if any(k in t for k in ["惠普", "hp"]):
        return "惠普"
    if any(k in t for k in ["戴尔", "dell"]):
        return "戴尔"
    if any(k in t for k in ["微软", "surface"]):
        return "微软"
    return None


def parse_budget(text: str) -> Optional[float]:
    if not text:
        return None
    t = str(text)
    patterns = [
        r"(\d+(?:\.\d+)?)\s*(?:元|块|rmb|人民币)?\s*(?:左右|上下|以内|以下|不超过|别超过)?",
        r"预算\s*(\d+(?:\.\d+)?)",
        r"(\d+(?:\.\d+)?)\s*以内",
    ]
    for pat in patterns:
        m = re.search(pat, t, re.I)
        if m:
            try:
                return float(m.group(1))
            except:
                pass
    if any(k in t for k in ["学生用", "学生", "便宜点", "性价比", "预算", "价位"]):
        return 3000.0
    return None


def is_review_query(text: str) -> bool:
    return any(k in text for k in ["评论", "评价", "口碑", "用户怎么说"])


def is_score_query(text: str) -> bool:
    return any(k in text for k in ["评分", "星级", "几星", "好评率"])


def is_sentiment_analysis_query(text: str) -> bool:
    patterns = [
        "情感分析", "评论分析", "口碑分析", "综合评价", "优缺点", "分析一下", "深度分析",
        "咋样", "怎么样", "你感觉", "你觉得", "好不好", "评价一下"
    ]
    return any(k in text for k in patterns)


def is_purchase_recommendation_query(text: str) -> bool:
    patterns = [
        "推荐买吗", "建议买吗", "买不买", "值得买吗", "值得入手吗", "值得购买吗", "可以买吗",
        "推荐购买吗", "推荐买这款", "建议购买吗", "这款值得买", "买这款吗", "推荐入手吗",
        "推荐购买不", "推荐买不", "建议购买不", "建议买不", "值得买不", "值得购买不",
        "入手不", "购买不推荐", "推荐不"
    ]
    return any(k in text for k in patterns)


def is_positive_query(text: str) -> bool:
    return any(k in text for k in ["好评", "优点", "好的地方", "正面评价", "值得买", "推荐理由"])


def is_negative_query(text: str) -> bool:
    return any(k in text for k in ["差评", "缺点", "不好的地方", "负面评价", "槽点", "问题", "避坑"])


def is_comparison_query(text: str) -> bool:
    return any(k in text for k in ["对比", "比较", "哪个好", "哪个值得买", "区别", "选哪个"])


def is_price_query(text: str) -> bool:
    return any(k in text for k in ["价格", "多少钱", "多少元", "价钱", "报价"])


def is_cart_query(text: str) -> bool:
    return any(k in text for k in ["购物车", "我的购物车", "查购物车", "查看购物车"])


def is_order_query(text: str) -> bool:
    return any(k in text for k in ["订单", "我的订单", "查订单", "查看订单", "订单详情", "结算", "支付", "取消订单", "所有订单"])


def is_checkout_query(text: str) -> bool:
    return any(k in text for k in ["结算", "下单", "提交订单", "去支付"])


def is_search_query(text: str) -> bool:
    search_keywords = ["找", "查", "看看", "有没有", "买什么"]
    if any(k in text for k in search_keywords):
        return True
    if "推荐" in text:
        exclude_patterns = [
            "推荐买吗", "推荐不买", "推荐买不", "推荐购买吗",
            "推荐买这款", "推荐买不买", "推荐入手吗", "推荐购买不",
            "建议买吗", "建议购买吗", "建议买不", "建议购买不",
            "值得买吗", "值得买不", "值得购买吗", "值得购买不"
        ]
        if not any(p in text for p in exclude_patterns):
            return True
    return False


def detect_intent(text: str) -> str:
    text = text or ""
    if is_cart_query(text):
        return "cart"
    if is_checkout_query(text):
        return "checkout"
    if is_order_query(text):
        return "order"
    if is_comparison_query(text):
        return "comparison"
    if is_purchase_recommendation_query(text):
        return "purchase_recommendation"
    if is_sentiment_analysis_query(text):
        return "sentiment_analysis"
    if is_positive_query(text):
        return "positive"
    if is_negative_query(text):
        return "negative"
    if is_review_query(text):
        return "review"
    if is_score_query(text):
        return "score"

    budget = parse_budget(text)
    if budget is not None:
        return "budget"

    if is_price_query(text):
        return "price"

    if is_search_query(text):
        return "search"

    return "general"


def normalize_search_query(query: str) -> str:
    if not query:
        return ""
    q = str(query).strip()
    q = re.sub(
        r"^(给我|帮我|麻烦|请)?(查查|查一下|查下|找一下|找下|找|推荐一下|推荐下|推荐|看看|搜索一下|搜索|查询一下|查询)",
        "",
        q
    ).strip()
    q = re.sub(r"(这边|这里|当前|附近|有没有|有没|有哪些|有什么|适合|学生用的|学生用|学生|呢|吗|呀)", "", q).strip()
    return q


def extract_order_index(text: str) -> Optional[int]:
    if not text:
        return None
    patterns = [
        r"第\s*(\d+)\s*个",
        r"第(\d+)个",
        r"第\s*(\d+)\s*款",
        r"第(\d+)款",
        r"第\s*(\d+)",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            try:
                idx = int(m.group(1))
                if idx > 0:
                    return idx
            except:
                pass

    chinese_map = {
        "第一个": 1, "第二个": 2, "第三个": 3, "第四个": 4, "第五个": 5,
        "第六个": 6, "第七个": 7, "第八个": 8, "第九个": 9, "第十个": 10,
        "第一款": 1, "第二款": 2, "第三款": 3, "第四款": 4, "第五款": 5,
        "第六款": 6, "第七款": 7, "第八款": 8, "第九款": 9, "第十款": 10,
    }
    for k, v in chinese_map.items():
        if k in text:
            return v

    return None


def is_followup_query(text: str) -> bool:
    if not text:
        return False
    patterns = [
        r"^评论呢$", r"^评分呢$", r"^价格呢$", r"^多少钱$",
        r"^它呢$", r"^这个呢$", r"^这个商品呢$", r"^该商品呢$",
        r"^怎么样$", r"^具体评论呢$", r"^评论$", r"^评分$", r"^价格$",
    ]
    return any(re.search(p, text) for p in patterns)


def get_tool_by_name(tool_name: str):
    for t in tools:
        if getattr(t, "name", None) == tool_name:
            return t
    return None


def parse_product_list_result(result: Any) -> List[Dict[str, Any]]:
    if not result:
        return []

    if isinstance(result, dict):
        if result.get("type") == "product_list":
            return result.get("products", []) or []
        if "products" in result and isinstance(result["products"], list):
            return result["products"]
        return []

    if isinstance(result, str):
        try:
            data = json.loads(result)
            if isinstance(data, dict):
                if data.get("type") == "product_list":
                    return data.get("products", []) or []
                if "products" in data and isinstance(data["products"], list):
                    return data["products"]
        except:
            pass

    return []


def save_recommendations(state: AgentState, result: Any):
    recs = parse_product_list_result(result)
    if recs:
        state["last_recommendations"] = recs[:MAX_RECOMMENDED_PRODUCTS]
        state["current_selected_product"] = None
    return recs


def set_selected_product(state: AgentState, product: Optional[Dict[str, Any]]):
    if product and isinstance(product, dict):
        state["current_selected_product"] = {
            "sku_id": str(product.get("sku_id") or "").strip(),
            "name": str(product.get("name") or "").strip(),
            "reference_name": str(product.get("reference_name") or product.get("name") or "").strip(),
            "price": product.get("price")
        }


def choose_target_product(state: AgentState, user_text: str) -> Optional[Dict[str, Any]]:
    idx = extract_order_index(user_text)
    recs = state.get("last_recommendations", []) or []

    if idx is not None:
        if idx < 1 or idx > len(recs):
            return {"_error_": "index_out_of_range", "requested_index": idx, "available_count": len(recs)}
        item = recs[idx - 1]
        if isinstance(item, dict):
            sku_id = str(item.get("sku_id") or "").strip()
            name = str(item.get("name") or item.get("reference_name") or "").strip()
            if sku_id and name:
                return {
                    "sku_id": sku_id,
                    "name": name,
                    "reference_name": str(item.get("reference_name") or name).strip(),
                    "price": item.get("price")
                }

    current = state.get("current_selected_product")
    if isinstance(current, dict):
        sku_id = str(current.get("sku_id") or "").strip()
        name = str(current.get("name") or "").strip()
        if sku_id and name:
            return current

    if recs:
        first = recs[0]
        if isinstance(first, dict):
            sku_id = str(first.get("sku_id") or "").strip()
            name = str(first.get("name") or first.get("reference_name") or "").strip()
            if sku_id and name:
                return {
                    "sku_id": sku_id,
                    "name": name,
                    "reference_name": str(first.get("reference_name") or name).strip(),
                    "price": first.get("price")
                }

    return None


def check_target_product_error(target: Optional[Dict[str, Any]]) -> Optional[str]:
    if target is None:
        return None
    if isinstance(target, dict) and target.get("_error_") == "index_out_of_range":
        idx = target.get("requested_index", 0)
        count = target.get("available_count", 0)
        return f"您选择的是第{idx}个商品，但我只推荐了{count}个商品。请选择第1到第{count}个商品。"
    return None


def build_search_query(user_text: str) -> Dict[str, Optional[str]]:
    brand = parse_brand(user_text)
    category = parse_category(user_text)
    return {"brand": brand, "category": category}


# ================== 主节点 ==================
async def call_model(state: AgentState, config: RunnableConfig):
    print("\n========== call_model 开始 ==========")

    configurable = config.get("configurable", {})
    user_email = configurable.get("user_email")
    session_id = configurable.get("session_id")
    if not session_id:
        session_id = user_email or f"session_{datetime.now().timestamp()}"
        session_id = session_id.replace(" ", "_") + "_" + uuid.uuid4().hex[:8]

    user_id = None
    user_profile_section = ""
    if user_email:
        user_id = f"user_{user_email.replace('@', '_at_').replace('.', '_dot_')}"
        raw_user_text = ""
        for msg in reversed(state.get("messages", [])):
            if isinstance(msg, HumanMessage):
                raw_user_text = msg.content or ""
                break
        user_query = extract_user_query(raw_user_text)
        user_profile_section = profile_manager.build_profile_prompt_section(user_id, user_query)
        if user_profile_section:
            print(f"[call_model] 已加载用户画像")

    if "last_recommendations" not in state:
        state["last_recommendations"] = []
    if "current_selected_product" not in state:
        state["current_selected_product"] = None
    if "intent" not in state:
        state["intent"] = None

    # ---------- 加载历史消息 ----------
    history_data = await get_session_cache(session_id) if session_id else None
    if history_data:
        history_messages = history_data.get("recent_messages", [])
        if history_messages:
            lc_history = convert_redis_messages_to_langchain(history_messages)
            current_msgs = state.get("messages", [])
            if not current_msgs:
                state["messages"] = lc_history
            elif len(current_msgs) == 1 and isinstance(current_msgs[0], HumanMessage):
                state["messages"] = lc_history + current_msgs
            else:
                if current_msgs and lc_history:
                    last_current = current_msgs[-1]
                    last_history = lc_history[-1]
                    if not (hasattr(last_current, "content") and hasattr(last_history, "content") and
                            last_current.content == last_history.content):
                        state["messages"] = lc_history + current_msgs

        metadata = history_data.get("metadata", {})
        if metadata.get("last_recommendations"):
            state["last_recommendations"] = metadata["last_recommendations"]
        if metadata.get("current_selected_product"):
            state["current_selected_product"] = metadata["current_selected_product"]
        if metadata.get("intent"):
            state["intent"] = metadata["intent"]

    raw_user_text = get_last_user_text(state)
    user_text = extract_user_query(raw_user_text)
    intent = detect_intent(user_text)
    brand = parse_brand(user_text)
    category = parse_category(user_text)
    budget = parse_budget(user_text)

    print(">>> intent:", intent, "brand:", brand, "category:", category, "budget:", budget, "user_text:", user_text)

    # ====== 1) 购物车 ======
    if intent == "cart":
        tool_fn = get_tool_by_name("check_user_cart")
        if not user_email:
            response = AIMessage(content="未获取到当前登录用户信息，无法查询购物车。")
            await update_session_cache(session_id, state["messages"] + [response], {
                "last_recommendations": state.get("last_recommendations", []),
                "current_selected_product": state.get("current_selected_product"),
                "intent": intent
            })
            return {"messages": [response], "intent": intent}

        result = tool_fn.invoke({"user_email": user_email}, config=config)
        response = AIMessage(content=str(result))
        await update_session_cache(session_id, state["messages"] + [response], {
            "last_recommendations": state.get("last_recommendations", []),
            "current_selected_product": state.get("current_selected_product"),
            "intent": intent
        })
        print("========== call_model 结束 ==========\n")
        return {"messages": [response], "intent": intent}

    # ====== 2) 订单 ======
    if intent == "order":
        if not user_email:
            response = AIMessage(content="未获取到当前登录用户信息，无法查询订单。")
            await update_session_cache(session_id, state["messages"] + [response], {
                "last_recommendations": state.get("last_recommendations", []),
                "current_selected_product": state.get("current_selected_product"),
                "intent": intent
            })
            return {"messages": [response], "intent": intent}

        trade_no = extract_trade_no(user_text)
        if trade_no:
            tool_fn = get_tool_by_name("get_order_details")
            result = tool_fn.invoke({"trade_no": trade_no}, config=config)
        else:
            tool_fn = get_tool_by_name("check_user_orders")
            result = tool_fn.invoke({"user_email": user_email, "limit": 10}, config=config)

        response = AIMessage(content=str(result))
        await update_session_cache(session_id, state["messages"] + [response], {
            "last_recommendations": state.get("last_recommendations", []),
            "current_selected_product": state.get("current_selected_product"),
            "intent": intent
        })
        print("========== call_model 结束 ==========\n")
        return {"messages": [response], "intent": intent}

    # ====== 3) 结算 ======
    if intent == "checkout":
        tool_fn = get_tool_by_name("checkout_cart")
        if not user_email:
            response = AIMessage(content="未获取到当前登录用户信息，无法结算购物车。")
            await update_session_cache(session_id, state["messages"] + [response], {
                "last_recommendations": state.get("last_recommendations", []),
                "current_selected_product": state.get("current_selected_product"),
                "intent": intent
            })
            return {"messages": [response], "intent": intent}

        result = tool_fn.invoke({"user_email": user_email, "address_id": 1}, config=config)
        response = AIMessage(content=str(result))
        await update_session_cache(session_id, state["messages"] + [response], {
            "last_recommendations": state.get("last_recommendations", []),
            "current_selected_product": state.get("current_selected_product"),
            "intent": intent
        })
        print("========== call_model 结束 ==========\n")
        return {"messages": [response], "intent": intent}

    # ====== 3.4) 购买建议 ======
    if intent == "purchase_recommendation":
        target = choose_target_product(state, user_text)
        error_msg = check_target_product_error(target)
        if error_msg:
            response = AIMessage(content=error_msg)
            await update_session_cache(session_id, state["messages"] + [response], {
                "last_recommendations": state.get("last_recommendations", []),
                "current_selected_product": state.get("current_selected_product"),
                "intent": intent
            })
            return {"messages": [response], "intent": intent}
        if not target:
            response = AIMessage(content="请先提供商品名称，或者先让我帮您推荐商品。")
            await update_session_cache(session_id, state["messages"] + [response], {
                "last_recommendations": state.get("last_recommendations", []),
                "current_selected_product": state.get("current_selected_product"),
                "intent": intent
            })
            return {"messages": [response], "intent": intent}

        set_selected_product(state, target)
        sku_id = target.get("sku_id", "")
        name = target.get("name", "")

        tool_fn = get_tool_by_name("generate_purchase_recommendation")
        result = tool_fn.invoke(
            {"product_name": name, "sku_id": sku_id},
            config=config
        )

        response = AIMessage(content=str(result))
        await update_session_cache(session_id, state["messages"] + [response], {
            "last_recommendations": state.get("last_recommendations", []),
            "current_selected_product": state.get("current_selected_product"),
            "intent": intent
        })
        print("========== call_model 结束 ==========\n")
        return {
            "messages": [response],
            "intent": intent,
            "current_selected_product": state.get("current_selected_product"),
            "last_recommendations": state.get("last_recommendations", [])
        }

    # ====== 3.5) 情感分析 / 正负面观点 / 对比分析 ======
    if intent in {"sentiment_analysis", "positive", "negative", "comparison"}:
        if intent == "comparison":
            recommendations = state.get("last_recommendations", [])
            if len(recommendations) < 2:
                response = AIMessage(content="请先推荐至少两个商品，我才能帮您对比分析。")
                await update_session_cache(session_id, state["messages"] + [response], {
                    "last_recommendations": recommendations,
                    "current_selected_product": state.get("current_selected_product"),
                    "intent": intent
                })
                return {"messages": [response], "intent": intent}

            product_names = [p.get("name", "") for p in recommendations[:3] if p.get("name")]
            sku_ids = [p.get("sku_id", "") for p in recommendations[:3] if p.get("sku_id")]

            tool_fn = get_tool_by_name("compare_product_sentiments")
            result = tool_fn.invoke(
                {"product_names": product_names, "sku_ids": sku_ids},
                config=config
            )
        else:
            target = choose_target_product(state, user_text)
            error_msg = check_target_product_error(target)
            if error_msg:
                response = AIMessage(content=error_msg)
                await update_session_cache(session_id, state["messages"] + [response], {
                    "last_recommendations": state.get("last_recommendations", []),
                    "current_selected_product": state.get("current_selected_product"),
                    "intent": intent
                })
                return {"messages": [response], "intent": intent}
            if not target:
                response = AIMessage(content="请先提供商品名称，或者先让我帮您推荐商品。")
                await update_session_cache(session_id, state["messages"] + [response], {
                    "last_recommendations": state.get("last_recommendations", []),
                    "current_selected_product": state.get("current_selected_product"),
                    "intent": intent
                })
                return {"messages": [response], "intent": intent}

            set_selected_product(state, target)
            sku_id = target.get("sku_id", "")
            name = target.get("name", "")

            if intent == "sentiment_analysis":
                tool_fn = get_tool_by_name("analyze_product_sentiment")
                result = tool_fn.invoke(
                    {"product_name": name, "sku_id": sku_id, "limit": 20},
                    config=config
                )
            elif intent == "positive":
                tool_fn = get_tool_by_name("search_positive_points")
                result = tool_fn.invoke(
                    {"query": name, "sku_id": sku_id, "top_k": 5},
                    config=config
                )
            else:
                tool_fn = get_tool_by_name("search_negative_points")
                result = tool_fn.invoke(
                    {"query": name, "sku_id": sku_id, "top_k": 5},
                    config=config
                )

        response = AIMessage(content=str(result))
        await update_session_cache(session_id, state["messages"] + [response], {
            "last_recommendations": state.get("last_recommendations", []),
            "current_selected_product": state.get("current_selected_product"),
            "intent": intent
        })
        print("========== call_model 结束 ==========\n")
        return {
            "messages": [response],
            "intent": intent,
            "current_selected_product": state.get("current_selected_product"),
            "last_recommendations": state.get("last_recommendations", [])
        }

    # ====== 4) 评论 / 评分 / 价格 ======
    if intent in {"review", "score", "price"}:
        target = choose_target_product(state, user_text)
        error_msg = check_target_product_error(target)
        if error_msg:
            response = AIMessage(content=error_msg)
            await update_session_cache(session_id, state["messages"] + [response], {
                "last_recommendations": state.get("last_recommendations", []),
                "current_selected_product": state.get("current_selected_product"),
                "intent": intent
            })
            print("========== call_model 结束 ==========\n")
            return {"messages": [response], "intent": intent}
        if not target:
            response = AIMessage(content="请先提供商品名称，或者先让我帮您推荐商品。")
            await update_session_cache(session_id, state["messages"] + [response], {
                "last_recommendations": state.get("last_recommendations", []),
                "current_selected_product": state.get("current_selected_product"),
                "intent": intent
            })
            print("========== call_model 结束 ==========\n")
            return {"messages": [response], "intent": intent}

        set_selected_product(state, target)
        sku_id = target.get("sku_id", "")
        name = target.get("name", "")

        if intent == "review":
            tool_fn = get_tool_by_name("get_product_comments")
            result = tool_fn.invoke(
                {"product_name": name, "sku_id": sku_id, "context_items": [name], "limit": 5},
                config=config
            )
        elif intent == "score":
            tool_fn = get_tool_by_name("get_product_score_summary")
            result = tool_fn.invoke(
                {"product_name": name, "sku_id": sku_id, "context_items": [name], "limit": 5},
                config=config
            )
        else:
            tool_fn = get_tool_by_name("get_product_price")
            result = tool_fn.invoke(
                {"product_names": name, "sku_id": sku_id, "context_items": [name]},
                config=config
            )

        response = AIMessage(content=str(result))
        await update_session_cache(session_id, state["messages"] + [response], {
            "last_recommendations": state.get("last_recommendations", []),
            "current_selected_product": state.get("current_selected_product"),
            "intent": intent
        })
        print("========== call_model 结束 ==========\n")
        return {
            "messages": [response],
            "intent": intent,
            "current_selected_product": state.get("current_selected_product"),
            "last_recommendations": state.get("last_recommendations", [])
        }

    # ====== 5) 预算推荐 / 搜索 ======
    if intent in {"search", "budget"}:
        search_brand = brand
        search_category = category

        if intent == "budget":
            tool_fn = get_tool_by_name("recommend_products_by_budget")
            if budget is None:
                budget = 3000.0

            tool_args = {
                "budget": float(budget),
                "context_items": []
            }
            if search_brand is not None:
                tool_args["brand"] = search_brand
            if search_category is not None:
                tool_args["category"] = search_category

            result = tool_fn.invoke(tool_args, config=config)

            save_recommendations(state, result)

            response = AIMessage(content=str(result))
            await update_session_cache(session_id, state["messages"] + [response], {
                "last_recommendations": state.get("last_recommendations", []),
                "current_selected_product": state.get("current_selected_product"),
                "intent": intent
            })
            print("========== call_model 结束 ==========\n")
            return {
                "messages": [response],
                "intent": intent,
                "last_recommendations": state.get("last_recommendations", []),
                "current_selected_product": state.get("current_selected_product")
            }

        else:
            tool_fn = get_tool_by_name("search_products_by_category")

            tool_args = {
                "limit": 10,
                "context_items": []
            }
            if search_brand is not None:
                tool_args["brand"] = search_brand
            if search_category is not None:
                tool_args["category"] = search_category

            result = tool_fn.invoke(tool_args, config=config)

            save_recommendations(state, result)

            response = AIMessage(content=str(result))
            await update_session_cache(session_id, state["messages"] + [response], {
                "last_recommendations": state.get("last_recommendations", []),
                "current_selected_product": state.get("current_selected_product"),
                "intent": intent
            })
            print("========== call_model 结束 ==========\n")
            return {
                "messages": [response],
                "intent": intent,
                "last_recommendations": state.get("last_recommendations", []),
                "current_selected_product": state.get("current_selected_product")
            }

    # ====== 6) 普通对话 ======
    system_parts = [build_system_prompt(user_email, user_profile_section)]

    if state.get("current_selected_product"):
        p = state["current_selected_product"]
        system_parts.append(
            f"当前选中的商品：{p.get('name', '')} | sku_id={p.get('sku_id', '')} | 价格={p.get('price', '')}"
        )

    if state.get("last_recommendations"):
        rec_lines = []
        for i, item in enumerate(state["last_recommendations"][:MAX_RECOMMENDED_PRODUCTS], start=1):
            if isinstance(item, dict):
                rec_lines.append(
                    f"{i}. {item.get('name', '')} | sku_id={item.get('sku_id', '')} | 价格={item.get('price', '')}"
                )
        if rec_lines:
            system_parts.append("最近推荐的商品：\n" + "\n".join(rec_lines))

    tmp_messages = [SystemMessage(content="\n\n".join(system_parts))]

    recent_msgs = []
    for msg in state["messages"][-MAX_CONTEXT_MESSAGES:]:
        if isinstance(msg, HumanMessage):
            recent_msgs.append(HumanMessage(content=msg.content or ""))
        elif isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            if msg.content:
                recent_msgs.append(AIMessage(content=msg.content))

    tmp_messages.extend(recent_msgs)
    response = llm.invoke(tmp_messages)

    await update_session_cache(session_id, state["messages"] + [response], {
        "last_recommendations": state.get("last_recommendations", []),
        "current_selected_product": state.get("current_selected_product"),
        "intent": intent
    })
    print("========== call_model 结束 ==========\n")
    return {
        "messages": [response],
        "current_selected_product": state.get("current_selected_product"),
        "last_recommendations": state.get("last_recommendations", []),
        "intent": intent
    }


# ================== 工具节点 ==================
def call_tool(state: AgentState, config: RunnableConfig):
    print("\n========== call_tool 开始 ==========")
    messages = state["messages"]
    last_message = messages[-1]
    tool_calls = getattr(last_message, "tool_calls", []) or []

    responses = []
    for tool_call in tool_calls:
        tool_name = tool_call["name"]
        tool_args = dict(tool_call["args"])
        tool_id = tool_call["id"]

        matched_tool = get_tool_by_name(tool_name)
        if matched_tool is None:
            result = f"错误：未找到工具 '{tool_name}'"
        else:
            try:
                result = matched_tool.invoke(tool_args, config=config)
                if not isinstance(result, str):
                    result = str(result)
            except Exception as e:
                result = f"工具调用失败：{str(e)}"

        responses.append(ToolMessage(content=result, tool_call_id=tool_id))

    print("========== call_tool 结束 ==========")
    return {"messages": responses}


def should_continue(state: AgentState) -> Literal["tools", "END"]:
    messages = state["messages"]
    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END


# ================== 构图 ==================
builder = StateGraph(AgentState)
builder.add_node("model", call_model)
builder.add_node("tools", call_tool)
builder.add_edge(START, "model")
builder.add_conditional_edges("model", should_continue, {"tools": "tools", END: END})
builder.add_edge("tools", "model")