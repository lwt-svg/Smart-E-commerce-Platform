import os
from langchain.tools import tool
from langchain_community.vectorstores import Chroma
from langchain_ollama import OllamaEmbeddings

# 全局嵌入模型（使用本地 Ollama bge-m3）
_embeddings = OllamaEmbeddings(
    model="bge-m3",
    base_url="http://localhost:11434"
)

_presales_db = None
_aftersales_db = None
_reviews_db = None


def get_presales_db():
    """获取售前知识库"""
    global _presales_db
    if _presales_db is None:
        _presales_db = Chroma(
            persist_directory="./chroma_db/presales",
            embedding_function=_embeddings
        )
    return _presales_db


def get_aftersales_db():
    """获取售后知识库"""
    global _aftersales_db
    if _aftersales_db is None:
        _aftersales_db = Chroma(
            persist_directory="./chroma_db/aftersales",
            embedding_function=_embeddings
        )
    return _aftersales_db


def get_reviews_db():
    """获取评价知识库"""
    global _reviews_db
    if _reviews_db is None:
        _reviews_db = Chroma(
            persist_directory="./chroma_db/reviews",
            embedding_function=_embeddings
        )
    return _reviews_db


@tool
def search_presales_knowledge(query: str, config: dict = None) -> str:
    """
    查询售前知识库，获取商品介绍、促销活动、尺码表等信息。
    当用户询问商品详情、优惠、购买建议时使用。
    """
    if config is not None:
        if hasattr(config, 'get'):
            use_rag = config.get("configurable", {}).get("use_rag", True)
        elif hasattr(config, 'configurable'):
            use_rag = config.configurable.get("use_rag", True) if config.configurable else True
        else:
            use_rag = True
    else:
        use_rag = True

    print(f"[DEBUG] search_presales_knowledge called, use_rag={use_rag}")
    if not use_rag:
        return ""

    db = get_presales_db()
    docs = db.similarity_search(query, k=3)
    print(f"[DEBUG] Retrieved {len(docs)} docs from presales")

    if not docs:
        return "未找到相关售前信息。"

    content = "\n\n---\n\n".join([doc.page_content for doc in docs])
    return content + "\n[source=retrieval]"


@tool
def search_aftersales_knowledge(query: str, config: dict = None) -> str:
    """
    查询售后知识库，获取退换货政策、物流查询、投诉流程等信息。
    当用户询问订单售后、退换货、物流问题时使用。
    """
    if config is not None:
        if hasattr(config, 'get'):
            use_rag = config.get("configurable", {}).get("use_rag", True)
        elif hasattr(config, 'configurable'):
            use_rag = config.configurable.get("use_rag", True) if config.configurable else True
        else:
            use_rag = True
    else:
        use_rag = True

    print(f"[DEBUG] search_aftersales_knowledge called, use_rag={use_rag}")
    if not use_rag:
        return ""

    db = get_aftersales_db()
    docs = db.similarity_search(query, k=3)
    print(f"[DEBUG] Retrieved {len(docs)} docs from aftersales")

    if not docs:
        return "未找到相关售后信息。"

    content = "\n\n---\n\n".join([doc.page_content for doc in docs])
    return content + "\n[source=retrieval]"


@tool
def search_product_reviews(query: str, sku_id: str = None, reference_name: str = None, config: dict = None) -> str:
    """
    查询商品用户评价。
    优先使用 sku_id 精确筛选，其次使用 reference_name 过滤，最后使用语义检索兜底。
    """
    if config is not None:
        if hasattr(config, "get"):
            use_rag = config.get("configurable", {}).get("use_rag", True)
        elif hasattr(config, "configurable"):
            use_rag = config.configurable.get("use_rag", True) if config.configurable else True
        else:
            use_rag = True
    else:
        use_rag = True

    print(f"[DEBUG] search_product_reviews called, use_rag={use_rag}")
    if not use_rag:
        return ""

    db = get_reviews_db()
    docs = []

    if sku_id:
        try:
            docs = db.similarity_search(query=query, k=5, filter={"sku_id": str(sku_id)})
            print(f"[DEBUG] Retrieved {len(docs)} docs by sku_id={sku_id}")
        except Exception as e:
            print(f"[DEBUG] sku_id filter search failed: {e}")

    if not docs and reference_name:
        try:
            docs = db.similarity_search(query=query, k=5, filter={"reference_name": reference_name})
            print(f"[DEBUG] Retrieved {len(docs)} docs by reference_name={reference_name}")
        except Exception as e:
            print(f"[DEBUG] reference_name filter search failed: {e}")

    if not docs:
        docs = db.similarity_search(query, k=5)
        print(f"[DEBUG] Retrieved {len(docs)} docs by semantic search")

    if not docs:
        return "未找到相关评价信息。"

    results = []
    for i, doc in enumerate(docs, 1):
        meta = doc.metadata or {}
        sku = meta.get("sku_id", "")
        name = meta.get("reference_name", "")
        score = meta.get("score", "")
        text = doc.page_content

        results.append(
            f"评价{i}：\n"
            f"商品名称：{name}\n"
            f"sku_id：{sku}\n"
            f"评分：{score}\n"
            f"内容：\n{text}"
        )

    return "\n\n---\n\n".join(results) + "\n[source=retrieval]"