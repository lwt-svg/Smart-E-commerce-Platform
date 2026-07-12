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
MAX_RECENT_MESSAGES = 3       # Redis缓存最近3条，减少缓存体积
MAX_CONTEXT_MESSAGES = 4      # 发送给LLM的上下文消息数
MAX_RECOMMENDED_PRODUCTS = 10

tools = all_tool_funcs
llm_with_tools = llm.bind_tools(tools)
SCHEMA_INFO = get_database_schema()
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

print("当前 tools:", [getattr(t, "name", str(t)) for t in tools])


# ================== Redis 会话 ==================
async def get_session_cache(session_id: str) -> Optional[Dict[str, Any]]:
    try:
        key = f"session:{session_id}"
        data = await redis_client.get(key)
        return json.loads(data) if data else None
    except Exception as e:
        print(f"[SessionCache] 读取失败(降级跳过): {type(e).__name__}")
        return None


async def update_session_cache(session_id: str, messages: List[Any], metadata: Dict[str, Any] = None):
    try:
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
    except Exception as e:
        print(f"[SessionCache] 写入失败(降级跳过): {type(e).__name__}")


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
        profile_prompt = f"\n{user_profile_section}\n"

    return f"""你是电商客服助手。
{profile_prompt}
【规则】
- 品牌和品类必须精准：华为平板≠华为手机，iPad=苹果平板
- "第几款"必须绑定推荐列表定位，追问默认指当前选中商品
- 查评论/评分/价格优先用sku_id精准查
- 购物车/订单/结算走对应工具，不走商品搜索
- 只用用户真实问题作查询条件，不拼入登录信息
- 用户画像有品牌偏好时优先考虑，但仍需满足当前需求

【意图→工具】
查商品→search_products_by_category | 查价格→get_product_price | 查评分→get_product_score_summary
查评论→get_product_comments | 预算推荐→recommend_products_by_budget | 购物车→check_user_cart
查订单→check_user_orders | 订单详情→get_order_details | 结算→checkout_cart
查优点→search_positive_points | 查缺点→search_negative_points | 综合评价→analyze_product_sentiment
购买建议→generate_purchase_recommendation

DB结构：
{SCHEMA_INFO}

中文简洁回复。"""


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
        return "电子产品"
    if any(k in t for k in ["手机", "phone", "iphone"]):
        return "手机"
    if any(k in t for k in ["笔记本", "laptop", "notebook"]):
        return "笔记本"
    if any(k in t for k in ["电脑", "computer", "台式"]):
        return "电子产品"
    if any(k in t for k in ["耳机", "耳麦"]):
        return "耳机"
    if any(k in t for k in ["手表", "watch", "手环", "band"]):
        return "电子产品"
    if any(k in t for k in ["音箱", "speaker"]):
        return "音箱"
    if any(k in t for k in ["路由器", "router", "显示器", "monitor"]):
        return "电子产品"
    if any(k in t for k in ["电视", "tv"]):
        return "电视"
    # 服装品类
    if any(k in t for k in ["男装", "女装", "服装", "衣服", "上衣", "衬衫", "t恤", "tshirt"]):
        return "服饰鞋靴"
    if any(k in t for k in ["裤子", "裤", "牛仔裤", "短裤", "长裤"]):
        return "服饰鞋靴"
    if any(k in t for k in ["裙子", "连衣裙", "半身裙"]):
        return "服饰鞋靴"
    if any(k in t for k in ["内衣", "内裤", "文胸", "袜子"]):
        return "服饰鞋靴"
    if any(k in t for k in ["外套", "夹克", "羽绒服", "卫衣", "风衣"]):
        return "服饰鞋靴"
    if any(k in t for k in ["鞋", "运动鞋", "板鞋", "帆布鞋", "拖鞋"]):
        return "服饰鞋靴"
    # 食品品类
    if any(k in t for k in ["食品", "零食", "饮料", "吃的", "茶叶", "咖啡"]):
        return "食品饮料"
    # 美妆品类
    if any(k in t for k in ["化妆品", "护肤", "面膜", "口红", "香水", "美妆"]):
        return "美妆护肤"
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

    # 纯价格查询（多少钱/报价）不走预算逻辑
    pure_price_hints = ["多少钱", "报价", "多少元"]
    if any(k in t for k in pure_price_hints) and not re.search(r"\d+.*(?:左右|上下|以内|以下|不超过)", t):
        return None

    # 必须包含数字才可能识别为预算（避免"性价比高""便宜点"等无数字场景被误判为budget）
    if not re.search(r"\d", t):
        return None

    patterns = [
        r"(\d+(?:\.\d+)?)\s*(?:元|块|rmb|人民币)?\s*(?:左右|上下|以内|以下|不超过|别超过)",
        r"预算\s*(\d+(?:\.\d+)?)",
        r"(\d+(?:\.\d+)?)\s*预算",                      # 新增：5000预算
        r"(\d+(?:\.\d+)?)\s*(?:块钱|元)\s*的",          # 新增：1000块钱的耳机
        r"(\d+(?:\.\d+)?)\s*以内",
    ]
    for pat in patterns:
        m = re.search(pat, t, re.I)
        if m:
            try:
                return float(m.group(1))
            except:
                pass
    # 仅在文本含数字且含明确预算暗示词时返回默认预算
    if any(k in t for k in ["学生用", "学生", "便宜点", "预算", "价位"]) and re.search(r"\d", t):
        return 3000.0
    return None


def is_review_query(text: str) -> bool:
    """评论查询：包含评论/评价等关键词，且不包含购买建议/情感分析等更高优先级意图"""
    # "口碑/综合评价/正面评价/评价一下"应归sentiment_analysis或positive，不属于review
    if any(k in text for k in ["口碑", "综合评价", "正面评价", "评价一下", "分析一下"]):
        return False
    review_keywords = ["评论", "评价", "用户怎么说"]
    if not any(k in text for k in review_keywords):
        return False
    # 如果同时包含购买建议关键词，不是review
    purchase_hints = ["推荐买", "值得买", "建议买", "买不买", "可以买"]
    if any(k in text for k in purchase_hints):
        return False
    return True


def is_score_query(text: str) -> bool:
    """评分查询：包含评分/星级/好评率等关键词"""
    return any(k in text for k in ["评分", "星级", "几星", "好评率", "打分"])


def is_sentiment_analysis_query(text: str) -> bool:
    """情感分析查询：注意只在review/score/positive/negative都不匹配时才匹配"""
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
        "入手不", "购买不推荐", "推荐不", "能冲吗", "值得冲吗"
    ]
    return any(k in text for k in patterns)


def is_positive_query(text: str) -> bool:
    """正面评价查询：排除'好评率'（属于score）和'不好的地方'（属于negative）"""
    # "好评率"属于评分查询，不是正面评价
    if "好评率" in text:
        return False
    # "不好的地方"属于负面查询，虽然包含"好的地方"子串
    if "不好" in text or "不咋好" in text:
        return False
    return any(k in text for k in ["好评", "优点", "好的地方", "正面评价", "推荐理由"])


def is_negative_query(text: str) -> bool:
    """负面评价查询：'不好的地方'应该匹配到这里"""
    return any(k in text for k in ["差评", "缺点", "不好的地方", "负面评价", "槽点", "避坑", "问题点"])


def is_comparison_query(text: str) -> bool:
    return any(k in text for k in ["对比", "比较", "哪个好", "哪个值得买", "区别", "选哪个"])


def is_price_query(text: str) -> bool:
    """价格查询：查某个已知商品的价格。包含搜索意图时走search不走price"""
    # 搜索意图关键词（用户想找商品，不是查价格）
    search_hints = ["查找", "找一下", "找下", "帮我找", "搜索", "有没有", "买什么", "推荐"]
    if any(k in text for k in search_hints):
        return False
    return any(k in text for k in ["价格", "多少钱", "多少元", "价钱", "报价"])


def is_cart_query(text: str) -> bool:
    return any(k in text for k in ["购物车", "我的购物车", "查购物车", "查看购物车"])


def is_order_query(text: str) -> bool:
    """订单查询：去除'结算/支付'等关键词（它们属于checkout）"""
    return any(k in text for k in ["订单", "我的订单", "查订单", "查看订单", "订单详情", "取消订单", "所有订单"])


def is_checkout_query(text: str) -> bool:
    """结算查询：包含结算/下单/支付等操作性关键词"""
    return any(k in text for k in ["结算", "下单", "提交订单", "去支付", "支付", "帮我付款", "付款"])


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
    # review和score优先于sentiment_analysis，避免"评论怎么样"被误判为情感分析
    if is_review_query(text):
        return "review"
    if is_score_query(text):
        return "score"
    if is_sentiment_analysis_query(text):
        return "sentiment_analysis"
    if is_positive_query(text):
        return "positive"
    if is_negative_query(text):
        return "negative"

    budget = parse_budget(text)
    if budget is not None:
        return "budget"

    if is_price_query(text):
        return "price"

    if is_search_query(text):
        return "search"

    # 如果能识别到品类，默认走search（覆盖"夏天款的男装"等无搜索关键词的查询）
    if parse_category(text):
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


async def _handle_no_target_with_recommendation(state: AgentState, session_id: str,
                                                  user_text: str, intent: str,
                                                  config: RunnableConfig) -> Dict[str, Any]:
    """指代词无上下文商品时的友好兜底：按品类或热销推荐代替"请先提供商品名称"。

    返回值同 call_model 节点的返回结构。
    """
    fallback_category = parse_category(user_text)
    tool_fn = get_tool_by_name("search_products_by_category")
    tool_args: Dict[str, Any] = {"limit": 5, "context_items": []}
    if fallback_category:
        tool_args["category"] = fallback_category

    try:
        result = tool_fn.invoke(tool_args, config=config)
    except Exception as e:
        result = f"暂时无法获取推荐商品：{e}"

    save_recommendations(state, result)

    if fallback_category:
        prefix = (f"您提到的这款{fallback_category}目前没有上下文信息，"
                  f"先为您推荐几款{fallback_category}商品，您可以告诉我对哪款感兴趣：\n")
    else:
        prefix = ("您还没有指定具体商品呢，先为您推荐几款热门商品，"
                  "您可以告诉我对哪款感兴趣，我会帮您查询详细信息：\n")

    response = AIMessage(content=prefix + str(result))
    await update_session_cache(session_id, state["messages"] + [response], {
        "last_recommendations": state.get("last_recommendations", []),
        "current_selected_product": state.get("current_selected_product"),
        "intent": intent
    })
    print("========== call_model 结束（指代词兜底） ==========\n")
    return {
        "messages": [response],
        "intent": intent,
        "last_recommendations": state.get("last_recommendations", []),
        "current_selected_product": state.get("current_selected_product")
    }


def set_selected_product(state: AgentState, product: Optional[Dict[str, Any]]):
    if product and isinstance(product, dict):
        state["current_selected_product"] = {
            "sku_id": str(product.get("sku_id") or "").strip(),
            "name": str(product.get("name") or "").strip(),
            "reference_name": str(product.get("reference_name") or product.get("name") or "").strip(),
            "price": product.get("price")
        }


def extract_product_name_from_price_query(text: str) -> Optional[str]:
    """从价格查询文本中提取商品名。

    例：'华为Mate30EPro多少钱？' → '华为Mate30EPro'
        'iPhone 15的售价是多少' → 'iPhone 15'
    """
    if not text:
        return None
    t = str(text).strip()
    # 含指代词时不提取（应走history上下文）
    if any(k in t for k in ["这款", "这个", "那款", "那个", "这", "那"]):
        return None
    # 去除括号内容
    t = re.sub(r'[（(].*?[)）]', '', t)
    # 去除价格关键词及之后内容
    t = re.sub(r'(多少钱|多少元|价钱|价格|报价|售价|卖多少|卖多少钱|要多少|要多少钱).*$', '', t)
    # 去除尾部"的"字和标点
    t = re.sub(r'[的?？!！。.,，~]+$', '', t).strip()
    t = t.strip()
    if len(t) < 2:
        return None
    return t


def extract_products_from_messages(state: AgentState) -> List[Dict[str, Any]]:
    """从messages历史中的AIMessage提取商品列表。

    用于支持history字段传入的多轮上下文：当last_recommendations为空但messages历史
    中有商品推荐JSON时，从中解析商品作为target候选。

    扫描顺序：从后往前找第一个含product_list JSON的AIMessage。
    """
    messages = state.get("messages", []) or []
    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        content = msg.content or ""
        if not isinstance(content, str):
            continue
        if '"type"' not in content or '"product_list"' not in content:
            continue
        # 用栈匹配找最外层JSON
        try:
            start = content.find("{")
            while start != -1:
                stack = []
                end = -1
                for i in range(start, len(content)):
                    if content[i] == '{':
                        stack.append('{')
                    elif content[i] == '}':
                        if stack:
                            stack.pop()
                            if not stack:
                                end = i
                                break
                if end != -1:
                    candidate = content[start:end + 1]
                    try:
                        parsed = json.loads(candidate)
                        if isinstance(parsed, dict) and parsed.get("type") == "product_list":
                            products = parsed.get("products", [])
                            if products and isinstance(products, list):
                                return products
                    except:
                        pass
                    start = content.find("{", end + 1)
                else:
                    break
        except Exception:
            continue
    return []


def choose_target_product(state: AgentState, user_text: str) -> Optional[Dict[str, Any]]:
    idx = extract_order_index(user_text)
    recs = state.get("last_recommendations", []) or []

    # 当last_recommendations为空时，从messages历史中的AIMessage提取商品（支持history字段传入的多轮上下文）
    if not recs:
        recs = extract_products_from_messages(state)

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
            return await _handle_no_target_with_recommendation(state, session_id, user_text, intent, config)

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
                return await _handle_no_target_with_recommendation(state, session_id, user_text, intent, config)

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
            # price意图特化：用户直接说出商品名（如"华为Mate30EPro多少钱？"），从user_text提取商品名直接查价格
            if intent == "price":
                product_name = extract_product_name_from_price_query(user_text)
                if product_name:
                    print(f"[PriceAgent] 从用户问题提取商品名: {product_name}，直接查价格")
                    tool_fn = get_tool_by_name("get_product_price")
                    result = tool_fn.invoke(
                        {"product_names": product_name, "sku_id": "", "context_items": [product_name]},
                        config=config
                    )
                    result_str = str(result)
                    # 如果查到了价格（非"未找到"），直接返回
                    if result_str and "未找到" not in result_str and "无" not in result_str[:20]:
                        response = AIMessage(content=result_str)
                        await update_session_cache(session_id, state["messages"] + [response], {
                            "last_recommendations": state.get("last_recommendations", []),
                            "current_selected_product": state.get("current_selected_product"),
                            "intent": intent
                        })
                        print("========== call_model 结束（价格直查） ==========\n")
                        return {
                            "messages": [response],
                            "intent": intent,
                            "current_selected_product": state.get("current_selected_product"),
                            "last_recommendations": state.get("last_recommendations", [])
                        }
            # 其他情况走兜底推荐
            return await _handle_no_target_with_recommendation(state, session_id, user_text, intent, config)

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
            # budget 为 None 时说明 parse_budget 没识别出预算（理论上不会进budget分支）
            # 给个安全兜底 3000，避免工具调用报错
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

            # 把用户查询关键词传入context_items，用于rank_products排序
            search_keywords = []
            normalized = normalize_search_query(user_text)
            if normalized:
                words = re.split(r'[的\s,，、]+', normalized)
                search_keywords = [w for w in words if len(w) >= 2]

            tool_args = {
                "limit": 10,
                "context_items": search_keywords
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
    # 流式调用LLM（产生on_chat_model_stream事件，供SSE逐字输出）
    chunks = []
    async for chunk in llm.astream(tmp_messages, config=config):
        if chunk.content:
            chunks.append(chunk.content)
    full_content = "".join(chunks)
    response = AIMessage(content=full_content)

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