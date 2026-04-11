import json
import re
from typing import List, Union, Optional, Dict, Any

from langchain.tools import tool
from ..database import get_db_connection

from langchain_community.vectorstores import Chroma
from langchain_ollama import OllamaEmbeddings

BASE_IMAGE_URL = "http://localhost:8001/static/product_images"
BASE_PRODUCT_URL = "http://localhost:8080/detail"
PLACEHOLDER_IMAGE = "https://via.placeholder.com/130"

INVALID_TOKENS = {"sku_id", "name", "reference_name", "comment_name", "", None}

CHROMA_REVIEW_DIR = "./chroma_db/reviews"

_embeddings = None
_reviews_db = None


def get_embedding_model():
    global _embeddings
    if _embeddings is None:
        _embeddings = OllamaEmbeddings(
            model="bge-m3",
            base_url="http://localhost:11434"
        )
    return _embeddings


def get_reviews_db():
    global _reviews_db
    if _reviews_db is None:
        _reviews_db = Chroma(
            persist_directory=CHROMA_REVIEW_DIR,
            embedding_function=get_embedding_model()
        )
    return _reviews_db


def safe_float(v, default=0.0):
    try:
        if v is None:
            return default
        return float(v)
    except:
        return default


def safe_int(v, default=0):
    try:
        if v is None:
            return default
        return int(v)
    except:
        return default


def parse_context_items(context_items):
    if not context_items:
        return []
    result = []
    for x in context_items:
        if x is None:
            continue
        s = str(x).strip()
        if s and s not in result and s not in INVALID_TOKENS:
            result.append(s)
    return result


def row_to_dict(cursor, row):
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    if not hasattr(cursor, "description") or cursor.description is None:
        return {}
    columns = [col[0] for col in cursor.description]
    return dict(zip(columns, row))


def fetch_all_dicts(cursor):
    rows = cursor.fetchall()
    if not rows:
        return []
    result = []
    for row in rows:
        if isinstance(row, dict):
            result.append(row)
        else:
            result.append(row_to_dict(cursor, row))
    return result


def is_valid_product_row(p: dict) -> bool:
    if not isinstance(p, dict):
        return False
    sku_id = str(p.get("sku_id") or p.get("sku") or "").strip()
    name = str(p.get("name") or "").strip()
    if sku_id in INVALID_TOKENS:
        return False
    if name in INVALID_TOKENS:
        return False
    return bool(sku_id and name)


def get_product_image_url(sku_id: str) -> str:
    if not sku_id or sku_id in INVALID_TOKENS:
        return PLACEHOLDER_IMAGE
    return f"{BASE_IMAGE_URL}/{sku_id}.jpg"


def get_product_detail_url(sku_id: str) -> str:
    if not sku_id or sku_id in INVALID_TOKENS:
        return BASE_PRODUCT_URL
    return f"{BASE_PRODUCT_URL}/{sku_id}"


def build_product_list_json(products_data):
    if not products_data:
        return ""

    products = []
    seen = set()

    for p in products_data:
        if not is_valid_product_row(p):
            continue

        sku_id = str(p.get("sku_id") or p.get("sku") or "").strip()
        name = str(p.get("name") or "").strip()

        if sku_id in seen:
            continue
        seen.add(sku_id)

        price = p.get("p_price")
        if price in [None, "", "p_price"]:
            price = p.get("jd_price")
        if price in [None, "", "jd_price"]:
            price = p.get("mk_price")
        if price in [None, "", "mk_price"]:
            price = p.get("price")
        if price in [None, "", "best_price"]:
            price = p.get("best_price")

        price = safe_float(price, 0.0)

        item = {
            "name": name,
            "price": price,
            "image_url": get_product_image_url(sku_id),
            "product_url": get_product_detail_url(sku_id),
            "sku_id": sku_id
        }

        if "main_brand" in p:
            item["main_brand"] = p.get("main_brand")
        if "main_category" in p:
            item["main_category"] = p.get("main_category")

        products.append(item)

    if not products:
        return ""

    return json.dumps({
        "type": "product_list",
        "products": products
    }, ensure_ascii=False)


def build_score_summary_json(products_data):
    if not products_data:
        return ""

    results = []
    seen = set()
    for p in products_data:
        if not isinstance(p, dict):
            continue
        sku_id = str(p.get("sku_id") or "").strip()
        name = str(p.get("name") or "").strip()
        if not sku_id or not name or sku_id in seen:
            continue
        seen.add(sku_id)
        results.append({
            "sku_id": sku_id,
            "name": name,
            "avg_score": round(safe_float(p.get("avg_score"), 0.0), 1),
            "total_comments": safe_int(p.get("total_comments"), 0)
        })

    if not results:
        return ""

    return json.dumps({
        "type": "score_summary",
        "products": results
    }, ensure_ascii=False)


def build_comment_json(product_name: str, sku_id: str, avg_score: float, total_comments: int, comments: List[Dict[str, Any]]):
    return json.dumps({
        "type": "comment_list",
        "product_name": product_name,
        "sku_id": sku_id,
        "avg_score": round(avg_score, 1),
        "total_comments": total_comments,
        "comments": comments
    }, ensure_ascii=False)


def normalize_search_keyword(text: str) -> str:
    if not text:
        return ""
    text = str(text).strip()

    text = re.sub(
        r"^(给我|帮我|麻烦|请)?(查查|查一下|查下|找一下|找下|找|推荐一下|推荐下|推荐|看看|搜索一下|搜索|查询一下|查询)",
        "",
        text
    ).strip()

    text = re.sub(r"(这边|这里|当前|附近|有没有|有没|有哪些|有什么|适合|学生用的|学生用|学生|呢|吗|呀)", "", text).strip()
    return text


def parse_brand_category_query(text: str) -> Dict[str, Optional[str]]:
    """
    解析用户输入中的 brand / category
    例：
    华为平板 => brand=华为 category=平板
    华为手机 => brand=华为 category=手机
    """
    raw = (text or "").strip()
    low = raw.lower()

    brand = None
    category = None

    # category 优先识别
    if any(k in low for k in ["平板", "pad", "tablet", "matepad", "ipad"]):
        category = "平板"
    elif any(k in low for k in ["手机", "phone", "iphone"]):
        category = "手机"
    elif any(k in low for k in ["电脑", "笔记本", "laptop", "notebook"]):
        category = "电脑"
    elif any(k in low for k in ["耳机", "耳麦"]):
        category = "耳机"
    elif any(k in low for k in ["手表", "watch"]):
        category = "手表"
    elif any(k in low for k in ["手环", "band"]):
        category = "手环"
    elif any(k in low for k in ["音箱", "speaker"]):
        category = "音箱"
    elif any(k in low for k in ["路由器", "router"]):
        category = "路由器"
    elif any(k in low for k in ["显示器", "monitor"]):
        category = "显示器"

    # brand 识别
    if any(k in low for k in ["苹果", "iphone", "ipad"]):
        brand = "苹果"
    elif any(k in low for k in ["华为", "huawei"]):
        brand = "华为"
    elif any(k in low for k in ["小米", "redmi", "mi"]):
        brand = "小米"
    elif any(k in low for k in ["荣耀", "honor"]):
        brand = "荣耀"
    elif "oppo" in low:
        brand = "OPPO"
    elif "vivo" in low:
        brand = "vivo"
    elif any(k in low for k in ["三星", "samsung"]):
        brand = "三星"
    elif any(k in low for k in ["联想", "lenovo"]):
        brand = "联想"
    elif any(k in low for k in ["华硕", "asus"]):
        brand = "华硕"
    elif any(k in low for k in ["惠普", "hp"]):
        brand = "惠普"
    elif any(k in low for k in ["戴尔", "dell"]):
        brand = "戴尔"
    elif any(k in low for k in ["微软", "surface"]):
        brand = "微软"

    return {"brand": brand, "category": category}


def is_accessory_product(name: str) -> bool:
    if not name:
        return False
    accessory_keywords = [
        "手机壳", "保护壳", "贴膜", "膜", "壳", "支架",
        "充电器", "耳机", "数据线", "配件", "手环", "手表",
        "腕带", "挂绳", "钢化膜", "保护套",
        "散热器", "散热背夹", "风扇", "底座", "支撑架",
        "保护膜", "转换器", "转接头", "扩展坞", "键盘膜", "触控笔"
    ]
    n = name.lower()
    return any(k.lower() in n for k in accessory_keywords)


def search_reviews_from_chroma(query: str, sku_id: Optional[str] = None, reference_name: Optional[str] = None, top_k: int = 5):
    try:
        db = get_reviews_db()
        docs = []

        if sku_id:
            try:
                docs = db.similarity_search(query, k=top_k, filter={"sku_id": str(sku_id)})
            except Exception as e:
                print(f"[DEBUG] sku_id filter search failed: {e}")

        if not docs and reference_name:
            try:
                docs = db.similarity_search(query, k=top_k, filter={"reference_name": reference_name})
            except Exception as e:
                print(f"[DEBUG] reference_name filter search failed: {e}")

        if not docs:
            docs = db.similarity_search(query, k=top_k)

        if not docs:
            return []

        results = []
        for doc in docs:
            md = doc.metadata or {}
            results.append({
                "sku_id": str(md.get("sku_id", sku_id or "")).strip(),
                "reference_name": str(md.get("reference_name", reference_name or "")).strip(),
                "nickname": md.get("nickname", "匿名"),
                "score": safe_float(md.get("score"), 0.0),
                "create_time": md.get("create_time", ""),
                "content": doc.page_content
            })
        return results
    except Exception as e:
        print(f"search_reviews_from_chroma 异常: {e}")
        return []


def execute_product_query(cursor, query: str, params: list):
    cursor.execute(query, params)
    rows = fetch_all_dicts(cursor)
    return rows


def build_product_filter_condition(brand: Optional[str] = None, category: Optional[str] = None):
    cond = ""
    params = []
    if brand:
        cond += " AND g.main_brand LIKE %s"
        params.append(f"%{brand}%")
    if category:
        cond += " AND g.main_category LIKE %s"
        params.append(f"%{category}%")
    return cond, params


def build_fallback_query_condition(query_text: str):
    if not query_text:
        return "", []
    q = query_text.strip()
    return " AND (g.name LIKE %s OR g.main_brand LIKE %s OR g.main_category LIKE %s)", [
        f"%{q}%",
        f"%{q}%",
        f"%{q}%"
    ]


def rank_products(rows, brand: Optional[str] = None, category: Optional[str] = None, budget: Optional[float] = None):
    def score_row(r):
        s = 0
        name = str(r.get("name", ""))
        main_brand = str(r.get("main_brand", ""))
        main_category = str(r.get("main_category", ""))
        price = safe_float(r.get("p_price") or r.get("jd_price") or r.get("mk_price") or r.get("best_price"), 0.0)

        if brand and brand in main_brand:
            s += 100
        if category and category in main_category:
            s += 80
        if brand and brand in name:
            s += 20
        if category and category in name:
            s += 10

        if budget and price > 0:
            s += max(0, 30 - abs(price - budget) / 100)

        return s

    return sorted(rows, key=lambda x: score_row(x), reverse=True)


@tool
def search_products_by_category(
    brand: str = None,
    category: str = None,
    max_price: float = None,
    limit: int = 10,
    context_items: List[str] = None
) -> str:
    """按品牌、类目或关键词搜索商品，返回商品列表。"""
    print(f"\n>>> 进入工具 search_products_by_category")
    print(f"   参数 brand: {brand}, category: {category}, max_price: {max_price}, limit: {limit}, context_items: {context_items}")

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            return "数据库连接失败"
        cursor = conn.cursor()

        context_items = parse_context_items(context_items)

        query = """
            SELECT
                g.sku_id AS sku_id,
                g.name AS name,
                g.main_brand AS main_brand,
                g.main_category AS main_category,
                g.p_price AS p_price,
                g.jd_price AS jd_price,
                g.mk_price AS mk_price
            FROM goods g
            WHERE 1=1
        """
        params = []

        strict_cond, strict_params = build_product_filter_condition(brand, category)
        query += strict_cond
        params.extend(strict_params)

        if not strict_cond:
            # 没有结构化条件时再走模糊兜底
            fallback_target = " ".join(context_items) if context_items else ""
            if not fallback_target:
                fallback_target = category or brand or ""
            fallback_cond, fallback_params = build_fallback_query_condition(fallback_target)
            query += fallback_cond
            params.extend(fallback_params)

        if max_price is not None and max_price > 0:
            query += " AND (COALESCE(g.p_price, g.jd_price, g.mk_price) <= %s)"
            params.append(max_price)

        if context_items:
            placeholders = ",".join(["%s"] * len(context_items))
            query += f" AND g.name IN ({placeholders})"
            params.extend(context_items)

        query += """
            GROUP BY g.sku_id, g.name, g.main_brand, g.main_category, g.p_price, g.jd_price, g.mk_price
            ORDER BY COALESCE(g.p_price, g.jd_price, g.mk_price) ASC, g.sku_id
            LIMIT %s
        """
        params.append(limit)

        rows = execute_product_query(cursor, query, params)
        rows = [r for r in rows if not is_accessory_product(str(r.get("name", "")))]

        if rows:
            rows = rank_products(rows, brand=brand, category=category, budget=max_price)

        if not rows:
            # 二次兜底：只模糊查
            fallback_target = " ".join(context_items) if context_items else (category or brand or "")
            query2 = """
                SELECT
                    g.sku_id AS sku_id,
                    g.name AS name,
                    g.main_brand AS main_brand,
                    g.main_category AS main_category,
                    g.p_price AS p_price,
                    g.jd_price AS jd_price,
                    g.mk_price AS mk_price
                FROM goods g
                WHERE 1=1
            """
            params2 = []
            fallback_cond, fallback_params = build_fallback_query_condition(fallback_target)
            query2 += fallback_cond
            params2.extend(fallback_params)

            if max_price is not None and max_price > 0:
                query2 += " AND (COALESCE(g.p_price, g.jd_price, g.mk_price) <= %s)"
                params2.append(max_price)

            query2 += """
                GROUP BY g.sku_id, g.name, g.main_brand, g.main_category, g.p_price, g.jd_price, g.mk_price
                ORDER BY COALESCE(g.p_price, g.jd_price, g.mk_price) ASC, g.sku_id
                LIMIT %s
            """
            params2.append(limit)

            rows = execute_product_query(cursor, query2, params2)
            rows = [r for r in rows if not is_accessory_product(str(r.get("name", "")))]
            if rows:
                rows = rank_products(rows, brand=brand, category=category, budget=max_price)

        if not rows:
            return f"未找到与 '{brand or category or ''}' 相关的商品"

        return build_product_list_json(rows)

    except Exception as e:
        print(f"search_products_by_category 异常: {e}")
        return f"搜索商品时出错: {str(e)}"
    finally:
        try:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
        except:
            pass


def query_products_by_brand_and_budget(cursor, brand: str = None, category: str = None, budget: float = None, limit: int = 10):
    query = """
        SELECT
            g.sku_id AS sku_id,
            g.name AS name,
            g.main_brand AS main_brand,
            g.main_category AS main_category,
            g.p_price AS p_price,
            g.jd_price AS jd_price,
            g.mk_price AS mk_price,
            COALESCE(g.p_price, g.jd_price, g.mk_price) AS best_price
        FROM goods g
        WHERE 1=1
    """
    params = []

    cond, cond_params = build_product_filter_condition(brand, category)
    query += cond
    params.extend(cond_params)

    if not cond and (brand or category):
        fallback_target = f"{brand or ''}{category or ''}"
        fallback_cond, fallback_params = build_fallback_query_condition(fallback_target)
        query += fallback_cond
        params.extend(fallback_params)

    query += """
        AND (
            (g.p_price IS NOT NULL AND g.p_price <= %s)
            OR (g.jd_price IS NOT NULL AND g.jd_price <= %s)
            OR (g.mk_price IS NOT NULL AND g.mk_price <= %s)
        )
    """
    params.extend([budget, budget, budget])

    query += """
        GROUP BY g.sku_id, g.name, g.main_brand, g.main_category, g.p_price, g.jd_price, g.mk_price
        ORDER BY ABS(COALESCE(g.p_price, g.jd_price, g.mk_price) - %s) ASC,
                 COALESCE(g.p_price, g.jd_price, g.mk_price) ASC,
                 g.sku_id ASC
        LIMIT %s
    """
    params.append(budget)
    params.append(limit)

    cursor.execute(query, params)
    rows = fetch_all_dicts(cursor)
    rows = [r for r in rows if not is_accessory_product(str(r.get("name", "")))]
    rows = rank_products(rows, brand=brand, category=category, budget=budget)
    return rows


def query_brand_cheapest_products(cursor, brand: str = None, category: str = None, limit: int = 5):
    query = """
        SELECT
            g.sku_id AS sku_id,
            g.name AS name,
            g.main_brand AS main_brand,
            g.main_category AS main_category,
            g.p_price AS p_price,
            g.jd_price AS jd_price,
            g.mk_price AS mk_price,
            COALESCE(g.p_price, g.jd_price, g.mk_price) AS best_price
        FROM goods g
        WHERE 1=1
    """
    params = []

    cond, cond_params = build_product_filter_condition(brand, category)
    query += cond
    params.extend(cond_params)

    if not cond and (brand or category):
        fallback_target = f"{brand or ''}{category or ''}"
        fallback_cond, fallback_params = build_fallback_query_condition(fallback_target)
        query += fallback_cond
        params.extend(fallback_params)

    query += """
        GROUP BY g.sku_id, g.name, g.main_brand, g.main_category, g.p_price, g.jd_price, g.mk_price
        ORDER BY COALESCE(g.p_price, g.jd_price, g.mk_price) ASC, g.sku_id ASC
        LIMIT %s
    """
    params.append(limit)

    cursor.execute(query, params)
    rows = fetch_all_dicts(cursor)
    rows = [r for r in rows if not is_accessory_product(str(r.get("name", "")))]
    rows = rank_products(rows, brand=brand, category=category, budget=None)
    return rows


@tool
def recommend_products_by_budget(budget: float, brand: str = None, category: str = None, context_items: List[str] = None) -> str:
    """根据预算和品牌/类目推荐商品，返回推荐列表。"""
    print(f"\n>>> 进入工具 recommend_products_by_budget")
    print(f"   参数 budget: {budget}, brand: {brand}, category: {category}, context_items: {context_items}")

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            return "数据库连接失败"

        cursor = conn.cursor()
        context_items = parse_context_items(context_items)

        if context_items:
            placeholders = ",".join(["%s"] * len(context_items))
            query = f"""
                SELECT
                    g.sku_id AS sku_id,
                    g.name AS name,
                    g.main_brand AS main_brand,
                    g.main_category AS main_category,
                    g.p_price AS p_price,
                    g.jd_price AS jd_price,
                    g.mk_price AS mk_price
                FROM goods g
                WHERE g.name IN ({placeholders})
                  AND (
                    (g.p_price IS NOT NULL AND g.p_price <= %s)
                    OR (g.jd_price IS NOT NULL AND g.jd_price <= %s)
                    OR (g.mk_price IS NOT NULL AND g.mk_price <= %s)
                  )
                GROUP BY g.sku_id, g.name, g.main_brand, g.main_category, g.p_price, g.jd_price, g.mk_price
                ORDER BY COALESCE(g.p_price, g.jd_price, g.mk_price) ASC, g.sku_id ASC
                LIMIT 10
            """
            params = tuple(context_items) + (budget, budget, budget)
            cursor.execute(query, params)
            rows = fetch_all_dicts(cursor)
            rows = [r for r in rows if not is_accessory_product(str(r.get("name", "")))]
            if rows:
                rows = rank_products(rows, brand=brand, category=category, budget=budget)
                return build_product_list_json(rows)

        rows = query_products_by_brand_and_budget(cursor, brand=brand, category=category, budget=budget, limit=10)

        if not rows and (brand or category):
            rows = query_brand_cheapest_products(cursor, brand=brand, category=category, limit=5)

        if not rows:
            rows = query_brand_cheapest_products(cursor, brand=None, category=None, limit=5)

        if not rows:
            return f"预算 ¥{budget} 内没有找到商品"

        rows = [r for r in rows if not is_accessory_product(str(r.get("name", "")))]
        rows = rank_products(rows, brand=brand, category=category, budget=budget)
        return build_product_list_json(rows) or f"预算 ¥{budget} 内没有找到商品"

    except Exception as e:
        print(f"recommend_products_by_budget 异常: {e}")
        return f"推荐商品时出错: {str(e)}"
    finally:
        try:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
        except:
            pass


@tool
def get_product_price(product_names: Union[str, List[str]] = None, context_items: List[str] = None, sku_id: str = None) -> str:
    """查询指定商品价格，优先使用 sku_id 精准匹配。"""
    print(f"\n>>> 进入工具 get_product_price")
    print(f"   参数 product_names: {product_names}")
    print(f"   参数 context_items: {context_items}")
    print(f"   参数 sku_id: {sku_id}")

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            return "数据库连接失败"
        cursor = conn.cursor()

        if sku_id:
            query = """
                SELECT
                    g.sku_id AS sku_id,
                    g.name AS name,
                    g.main_brand AS main_brand,
                    g.main_category AS main_category,
                    g.p_price AS p_price,
                    g.jd_price AS jd_price,
                    g.mk_price AS mk_price
                FROM goods g
                WHERE g.sku_id = %s
                LIMIT 1
            """
            cursor.execute(query, (sku_id,))
            rows = fetch_all_dicts(cursor)
            if rows:
                return build_product_list_json(rows)
            return "未找到相关商品的价格信息。"

        if context_items:
            names_list = parse_context_items(context_items)
            exact_match = True
        else:
            if product_names is None:
                return "请提供要查询的商品名称。"
            names_list = [product_names] if isinstance(product_names, str) else product_names
            exact_match = False

        products_data = []

        for name in names_list:
            parsed = parse_brand_category_query(str(name))
            if parsed["brand"] or parsed["category"]:
                query = """
                    SELECT
                        g.sku_id AS sku_id,
                        g.name AS name,
                        g.main_brand AS main_brand,
                        g.main_category AS main_category,
                        g.p_price AS p_price,
                        g.jd_price AS jd_price,
                        g.mk_price AS mk_price
                    FROM goods g
                    WHERE 1=1
                """
                params = []
                if parsed["brand"]:
                    query += " AND g.main_brand LIKE %s"
                    params.append(f"%{parsed['brand']}%")
                if parsed["category"]:
                    query += " AND g.main_category LIKE %s"
                    params.append(f"%{parsed['category']}%")
                query += " LIMIT 10"
                cursor.execute(query, tuple(params))
            else:
                if exact_match:
                    query = """
                        SELECT
                            g.sku_id AS sku_id,
                            g.name AS name,
                            g.main_brand AS main_brand,
                            g.main_category AS main_category,
                            g.p_price AS p_price,
                            g.jd_price AS jd_price,
                            g.mk_price AS mk_price
                        FROM goods g
                        WHERE g.name = %s
                        LIMIT 1
                    """
                    cursor.execute(query, (name,))
                else:
                    query = """
                        SELECT
                            g.sku_id AS sku_id,
                            g.name AS name,
                            g.main_brand AS main_brand,
                            g.main_category AS main_category,
                            g.p_price AS p_price,
                            g.jd_price AS jd_price,
                            g.mk_price AS mk_price
                        FROM goods g
                        WHERE g.name LIKE %s
                           OR g.main_brand LIKE %s
                           OR g.main_category LIKE %s
                        LIMIT 5
                    """
                    cursor.execute(query, (f"%{name}%", f"%{name}%", f"%{name}%"))

            rows = fetch_all_dicts(cursor)
            if rows:
                products_data.extend(rows)

        if not products_data:
            return "未找到相关商品的价格信息。"

        products_data = [r for r in products_data if not is_accessory_product(str(r.get("name", "")))]
        return build_product_list_json(products_data)

    except Exception as e:
        return f"查询商品价格时出错: {str(e)}"
    finally:
        try:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
        except:
            pass


@tool
def get_product_score_summary(product_name: str = None, context_items: List[str] = None, limit: int = 5, sku_id: str = None) -> str:
    """查询指定商品的评分摘要，优先使用 sku_id 精准匹配。"""
    print(f"\n>>> 进入工具 get_product_score_summary")
    print(f"   参数 product_name: {product_name}, context_items: {context_items}, limit: {limit}, sku_id: {sku_id}")

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            return "数据库连接失败"
        cursor = conn.cursor()

        all_products = []

        if sku_id:
            query = """
                SELECT
                    g.sku_id AS sku_id,
                    g.name AS name,
                    AVG(c.score) AS avg_score,
                    COUNT(c.id) AS total_comments
                FROM goods g
                LEFT JOIN comment c ON g.sku_id = c.sku_id
                WHERE g.sku_id = %s
                GROUP BY g.sku_id, g.name
                LIMIT 1
            """
            cursor.execute(query, (sku_id,))
            rows = fetch_all_dicts(cursor)
            for row in rows:
                sku = str(row.get("sku_id") or "").strip()
                name = str(row.get("name") or "").strip()
                if sku and name:
                    all_products.append({
                        "sku_id": sku,
                        "name": name,
                        "avg_score": round(safe_float(row.get("avg_score"), 0.0), 1),
                        "total_comments": safe_int(row.get("total_comments"), 0)
                    })

            if not all_products:
                return "未找到相关商品评分信息。"

            return build_score_summary_json(all_products)

        product_list = parse_context_items(context_items)
        if not product_list and product_name:
            product_list = [product_name]

        if not product_list:
            return "请提供商品名称或上下文商品列表。"

        for name in product_list:
            query = """
                SELECT
                    g.sku_id AS sku_id,
                    g.name AS name,
                    AVG(c.score) AS avg_score,
                    COUNT(c.id) AS total_comments
                FROM goods g
                LEFT JOIN comment c ON g.sku_id = c.sku_id
                WHERE g.name LIKE %s
                GROUP BY g.sku_id, g.name
                ORDER BY total_comments DESC
                LIMIT %s
            """
            cursor.execute(query, (f"%{name}%", limit))
            rows = fetch_all_dicts(cursor)

            if not rows:
                query = """
                    SELECT
                        sku_id,
                        reference_name AS name,
                        AVG(score) AS avg_score,
                        COUNT(*) AS total_comments
                    FROM comment
                    WHERE reference_name LIKE %s
                    GROUP BY sku_id, reference_name
                    ORDER BY total_comments DESC
                    LIMIT %s
                """
                cursor.execute(query, (f"%{name}%", limit))
                rows = fetch_all_dicts(cursor)

            for row in rows:
                sku = str(row.get("sku_id") or "").strip()
                name_val = str(row.get("name") or "").strip()
                if not sku or not name_val:
                    continue
                all_products.append({
                    "sku_id": sku,
                    "name": name_val,
                    "avg_score": round(safe_float(row.get("avg_score"), 0.0), 1),
                    "total_comments": safe_int(row.get("total_comments"), 0)
                })

        if not all_products:
            return "未找到相关商品评分信息。"

        return build_score_summary_json(all_products)

    except Exception as e:
        return f"查询商品评分摘要时出错: {str(e)}"
    finally:
        try:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
        except:
            pass


@tool
def get_product_comments(product_name: str = None, limit: int = 5, context_items: List[str] = None, sku_id: str = None) -> str:
    """查询指定商品评论，优先使用 sku_id 精准匹配。"""
    print(f"\n>>> 进入工具 get_product_comments")
    print(f"   参数 product_name: {product_name}, limit: {limit}, context_items: {context_items}, sku_id: {sku_id}")

    conn = None
    cursor = None
    try:
        product_list = parse_context_items(context_items)
        if not product_list and product_name:
            product_list = [product_name]

        if not product_list and not sku_id:
            return "请提供商品名称或上下文商品列表。"

        product_name_found = product_name or "未知商品"
        sku_id_found = sku_id

        if sku_id_found:
            conn = get_db_connection()
            if not conn:
                return "数据库连接失败"
            cursor = conn.cursor()

            query = """
                SELECT sku_id, name
                FROM goods
                WHERE sku_id = %s
                LIMIT 1
            """
            cursor.execute(query, (sku_id_found,))
            row = cursor.fetchone()
            if row:
                row_dict = row_to_dict(cursor, row)
                product_name_found = row_dict.get("name") or product_name_found
                sku_id_found = row_dict.get("sku_id") or sku_id_found

        query_text = " ".join(product_list) if product_list else (product_name_found or "")
        chroma_results = []

        if sku_id_found:
            chroma_results = search_reviews_from_chroma(
                query=query_text,
                sku_id=sku_id_found,
                reference_name=product_name_found,
                top_k=limit
            )
        else:
            chroma_results = search_reviews_from_chroma(
                query=query_text,
                sku_id=None,
                reference_name=product_name_found,
                top_k=limit
            )

        if chroma_results:
            if sku_id_found:
                chroma_results = [
                    x for x in chroma_results
                    if str(x.get("sku_id") or "").strip() == str(sku_id_found).strip()
                ]

            if chroma_results:
                score_list = [x.get("score", 0.0) for x in chroma_results]
                avg_score = sum(score_list) / len(score_list) if score_list else 0.0
                total_comments = len(chroma_results)

                comments = []
                for x in chroma_results:
                    comments.append({
                        "sku_id": str(x.get("sku_id") or sku_id_found or "").strip(),
                        "nickname": x.get("nickname", "匿名"),
                        "score": safe_float(x.get("score"), 0.0),
                        "create_time": x.get("create_time", ""),
                        "content": x.get("content", "")
                    })

                return build_comment_json(
                    product_name=product_name_found,
                    sku_id=sku_id_found or "",
                    avg_score=avg_score,
                    total_comments=total_comments,
                    comments=comments
                )

        if not conn:
            conn = get_db_connection()
            if not conn:
                return "数据库连接失败"
            cursor = conn.cursor()

        if not sku_id_found:
            for name in product_list:
                query = """
                    SELECT sku_id, name
                    FROM goods
                    WHERE name LIKE %s
                    LIMIT 1
                """
                cursor.execute(query, (f"%{name}%",))
                rows = fetch_all_dicts(cursor)
                if rows:
                    sku_id_found = rows[0].get("sku_id")
                    product_name_found = rows[0].get("name") or product_name_found
                    break

        if not sku_id_found:
            return "未找到相关商品评论。"

        query = """
            SELECT id, content, score, create_time, nickname, reference_name, sku_id
            FROM comment
            WHERE sku_id = %s
            ORDER BY create_time DESC
            LIMIT %s
        """
        cursor.execute(query, (sku_id_found, limit))
        comments_rows = fetch_all_dicts(cursor)

        if not comments_rows:
            return "未找到相关商品评论。"

        query = """
            SELECT AVG(score) AS avg_score, COUNT(*) AS total_comments
            FROM comment
            WHERE sku_id = %s
        """
        cursor.execute(query, (sku_id_found,))
        stats_rows = fetch_all_dicts(cursor)
        stats = stats_rows[0] if stats_rows else {}

        avg_score = safe_float(stats.get("avg_score"), 0.0)
        total_comments = safe_int(stats.get("total_comments"), 0)

        comments = []
        for c in comments_rows:
            comments.append({
                "sku_id": sku_id_found,
                "nickname": c.get("nickname") or "匿名",
                "score": safe_float(c.get("score"), 0.0),
                "create_time": c.get("create_time", ""),
                "content": c.get("content", "")
            })

        return build_comment_json(
            product_name=product_name_found,
            sku_id=sku_id_found,
            avg_score=avg_score,
            total_comments=total_comments,
            comments=comments
        )

    except Exception as e:
        return f"查询商品评论时出错: {str(e)}"
    finally:
        try:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
        except:
            pass


all_tool_funcs = [
    search_products_by_category,
    get_product_price,
    get_product_comments,
    recommend_products_by_budget,
    get_product_score_summary,
]