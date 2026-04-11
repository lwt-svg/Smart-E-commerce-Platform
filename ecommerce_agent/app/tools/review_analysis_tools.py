'''
评论分析工具
'''
import json
from typing import List, Optional, Dict, Any
from langchain.tools import tool
from langchain_community.vectorstores import Chroma
from langchain_ollama import OllamaEmbeddings

from .sentiment_analyzer import (
    SentimentAnalyzer, 
    ReviewAnalysisEngine, 
    ReviewAnalysisResult
)
from ..database import get_db_connection
import pymysql

_embeddings = None
_reviews_db = None
_positive_db = None
_negative_db = None


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
            persist_directory="./chroma_db/reviews",
            embedding_function=get_embedding_model()
        )
    return _reviews_db


def get_positive_db():
    global _positive_db
    if _positive_db is None:
        try:
            _positive_db = Chroma(
                persist_directory="./chroma_db/reviews_positive",
                embedding_function=get_embedding_model()
            )
        except Exception as e:
            print(f"[WARN] 正面观点向量库加载失败: {e}")
            return None
    return _positive_db


def get_negative_db():
    global _negative_db
    if _negative_db is None:
        try:
            _negative_db = Chroma(
                persist_directory="./chroma_db/reviews_negative",
                embedding_function=get_embedding_model()
            )
        except Exception as e:
            print(f"[WARN] 负面观点向量库加载失败: {e}")
            return None
    return _negative_db


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


def fetch_all_dicts(cursor):
    rows = cursor.fetchall()
    if not rows:
        return []
    result = []
    for row in rows:
        if isinstance(row, dict):
            result.append(row)
        else:
            columns = [col[0] for col in cursor.description]
            result.append(dict(zip(columns, row)))
    return result


@tool
def search_positive_points(query: str, sku_id: str = None, top_k: int = 5) -> str:
    """
    检索商品的正面评价观点。
    用于查询用户对商品的优点、好评内容。
    返回正面观点列表，支持按商品sku_id精确筛选。
    """
    print(f"\n>>> 进入工具 search_positive_points")
    print(f"   参数 query: {query}, sku_id: {sku_id}, top_k: {top_k}")

    db = get_positive_db()
    if db is None:
        return "正面观点向量库未初始化，请先运行 python build_sentiment_reviews_db.py 构建向量库。"

    docs = []
    try:
        search_k = max(top_k * 10, 50)
        if sku_id:
            docs = db.similarity_search(query, k=search_k, filter={"sku_id": str(sku_id)})
        if not docs:
            docs = db.similarity_search(query, k=search_k)
    except Exception as e:
        print(f"[ERROR] 正面观点检索失败: {e}")
        return f"正面观点检索失败: {str(e)}"

    if not docs:
        return "未找到相关正面评价。"

    seen_points = set()
    results = []
    for doc in docs:
        meta = doc.metadata or {}
        point = meta.get("point", doc.page_content.replace("【正面评价】", ""))
        if point in seen_points:
            continue
        seen_points.add(point)
        results.append({
            "rank": len(results) + 1,
            "product_name": meta.get("reference_name", ""),
            "sku_id": meta.get("sku_id", ""),
            "point": point,
            "score": meta.get("score"),
            "confidence": meta.get("confidence", 0)
        })
        if len(results) >= top_k:
            break

    return json.dumps({
        "type": "positive_points",
        "query": query,
        "total": len(results),
        "points": results
    }, ensure_ascii=False)


@tool
def search_negative_points(query: str, sku_id: str = None, top_k: int = 5) -> str:
    """
    检索商品的负面评价观点。
    用于查询用户对商品的缺点、差评内容。
    返回负面观点列表，支持按商品sku_id精确筛选。
    """
    print(f"\n>>> 进入工具 search_negative_points")
    print(f"   参数 query: {query}, sku_id: {sku_id}, top_k: {top_k}")

    db = get_negative_db()
    if db is None:
        return "负面观点向量库未初始化，请先运行 python build_sentiment_reviews_db.py 构建向量库。"

    docs = []
    try:
        search_k = max(top_k * 10, 50)
        if sku_id:
            docs = db.similarity_search(query, k=search_k, filter={"sku_id": str(sku_id)})
        if not docs:
            docs = db.similarity_search(query, k=search_k)
    except Exception as e:
        print(f"[ERROR] 负面观点检索失败: {e}")
        return f"负面观点检索失败: {str(e)}"

    if not docs:
        return "未找到相关负面评价。"

    seen_points = set()
    results = []
    for doc in docs:
        meta = doc.metadata or {}
        point = meta.get("point", doc.page_content.replace("【负面评价】", ""))
        if point in seen_points:
            continue
        seen_points.add(point)
        results.append({
            "rank": len(results) + 1,
            "product_name": meta.get("reference_name", ""),
            "sku_id": meta.get("sku_id", ""),
            "point": point,
            "score": meta.get("score"),
            "confidence": meta.get("confidence", 0)
        })
        if len(results) >= top_k:
            break

    return json.dumps({
        "type": "negative_points",
        "query": query,
        "total": len(results),
        "points": results
    }, ensure_ascii=False)


@tool
def analyze_product_sentiment(product_name: str = None, sku_id: str = None, limit: int = 20) -> str:
    """
    分析商品评论的情感倾向，生成正负面观点对比、分歧度、矛盾点标注和综合评价。
    用于深入了解商品口碑，辅助用户购买决策。
    """
    print(f"\n>>> 进入工具 analyze_product_sentiment")
    print(f"   参数 product_name: {product_name}, sku_id: {sku_id}, limit: {limit}")

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            return "数据库连接失败"
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        sku_id_found = sku_id
        product_name_found = product_name

        if not sku_id_found and product_name:
            query = """
                SELECT sku_id, name
                FROM goods
                WHERE name LIKE %s
                LIMIT 1
            """
            cursor.execute(query, (f"%{product_name}%",))
            rows = fetch_all_dicts(cursor)
            if rows:
                sku_id_found = rows[0].get("sku_id")
                product_name_found = rows[0].get("name") or product_name_found

        if not sku_id_found:
            return "请提供商品名称或sku_id。"

        query = """
            SELECT content, sku_id, reference_name, score, nickname, create_time
            FROM comment
            WHERE sku_id = %s
            ORDER BY create_time DESC
            LIMIT %s
        """
        cursor.execute(query, (sku_id_found, limit))
        reviews = fetch_all_dicts(cursor)

        if not reviews:
            return f"未找到商品 {product_name_found or sku_id_found} 的评论数据。"

        engine = ReviewAnalysisEngine()
        analysis_result = engine.analyze_product_reviews(
            sku_id=sku_id_found,
            product_name=product_name_found or sku_id_found,
            reviews=reviews
        )

        llm_summary = engine.generate_llm_summary(analysis_result)

        result_data = {
            "type": "sentiment_analysis",
            "product_name": analysis_result.product_name,
            "sku_id": analysis_result.sku_id,
            "total_reviews": analysis_result.total_reviews,
            "sentiment_distribution": {
                "positive": analysis_result.positive_count,
                "negative": analysis_result.negative_count,
                "neutral": analysis_result.neutral_count,
                "positive_rate": round(analysis_result.positive_count / analysis_result.total_reviews * 100, 1) if analysis_result.total_reviews > 0 else 0
            },
            "top_positive_points": [
                {"point": p.get("point", ""), "count": p.get("count", 0)}
                for p in analysis_result.positive_points[:5]
            ],
            "top_negative_points": [
                {"point": p.get("point", ""), "count": p.get("count", 0)}
                for p in analysis_result.negative_points[:5]
            ],
            "divergence_score": analysis_result.divergence_score,
            "contradictions": analysis_result.contradictions,
            "summary": llm_summary
        }

        return json.dumps(result_data, ensure_ascii=False, default=str)

    except Exception as e:
        return f"情感分析失败: {str(e)}"
    finally:
        try:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
        except:
            pass


@tool
def compare_product_sentiments(product_names: List[str] = None, sku_ids: List[str] = None) -> str:
    """
    对比多个商品的评论情感分析结果。
    用于帮助用户在多个商品间做出选择。
    最多支持对比3个商品。
    """
    print(f"\n>>> 进入工具 compare_product_sentiments")
    print(f"   参数 product_names: {product_names}, sku_ids: {sku_ids}")

    if not product_names and not sku_ids:
        return "请提供商品名称列表或sku_id列表。"

    max_products = 3
    products_to_analyze = []

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            return "数据库连接失败"
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        if sku_ids:
            for sku_id in sku_ids[:max_products]:
                query = "SELECT sku_id, name FROM goods WHERE sku_id = %s LIMIT 1"
                cursor.execute(query, (sku_id,))
                rows = fetch_all_dicts(cursor)
                if rows:
                    products_to_analyze.append({
                        "sku_id": rows[0].get("sku_id"),
                        "name": rows[0].get("name")
                    })

        if len(products_to_analyze) < max_products and product_names:
            for name in product_names[:max_products - len(products_to_analyze)]:
                query = "SELECT sku_id, name FROM goods WHERE name LIKE %s LIMIT 1"
                cursor.execute(query, (f"%{name}%",))
                rows = fetch_all_dicts(cursor)
                if rows:
                    sku = rows[0].get("sku_id")
                    if not any(p.get("sku_id") == sku for p in products_to_analyze):
                        products_to_analyze.append({
                            "sku_id": sku,
                            "name": rows[0].get("name")
                        })

        if not products_to_analyze:
            return "未找到相关商品。"

        engine = ReviewAnalysisEngine()
        comparison_results = []

        for product in products_to_analyze:
            sku_id = product.get("sku_id")
            name = product.get("name")

            query = """
                SELECT content, sku_id, reference_name, score, nickname, create_time
                FROM comment
                WHERE sku_id = %s
                ORDER BY create_time DESC
                LIMIT 20
            """
            cursor.execute(query, (sku_id,))
            reviews = fetch_all_dicts(cursor)

            if reviews:
                analysis = engine.analyze_product_reviews(sku_id, name, reviews)
                comparison_results.append({
                    "product_name": name,
                    "sku_id": sku_id,
                    "total_reviews": analysis.total_reviews,
                    "positive_rate": round(analysis.positive_count / analysis.total_reviews * 100, 1) if analysis.total_reviews > 0 else 0,
                    "divergence_score": analysis.divergence_score,
                    "top_positive": [p.get("point", "") for p in analysis.positive_points[:2]],
                    "top_negative": [p.get("point", "") for p in analysis.negative_points[:2]],
                    "summary": analysis.summary
                })
            else:
                comparison_results.append({
                    "product_name": name,
                    "sku_id": sku_id,
                    "total_reviews": 0,
                    "positive_rate": 0,
                    "divergence_score": 0,
                    "top_positive": [],
                    "top_negative": [],
                    "summary": "暂无评论数据"
                })

        comparison_results.sort(key=lambda x: x.get("positive_rate", 0), reverse=True)

        return json.dumps({
            "type": "sentiment_comparison",
            "products": comparison_results
        }, ensure_ascii=False)

    except Exception as e:
        return f"情感对比分析失败: {str(e)}"
    finally:
        try:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
        except:
            pass


@tool
def generate_purchase_recommendation(product_name: str = None, sku_id: str = None) -> str:
    """
    基于商品评论分析，生成购买建议。
    用于回答"推荐买吗"、"值得买吗"等问题。
    返回明确的购买建议，包含推荐理由和注意事项。
    """
    print(f"\n>>> 进入工具 generate_purchase_recommendation")
    print(f"   参数 product_name: {product_name}, sku_id: {sku_id}")

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            return "数据库连接失败"
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        sku_id_found = sku_id
        product_name_found = product_name

        if not sku_id_found and product_name:
            query = """
                SELECT sku_id, name, price
                FROM goods
                WHERE name LIKE %s
                LIMIT 1
            """
            cursor.execute(query, (f"%{product_name}%",))
            rows = fetch_all_dicts(cursor)
            if rows:
                sku_id_found = rows[0].get("sku_id")
                product_name_found = rows[0].get("name")
                product_price = rows[0].get("price")

        if not sku_id_found:
            return "请提供商品名称或sku_id。"

        query = """
            SELECT content, sku_id, reference_name, score, nickname, create_time
            FROM comment
            WHERE sku_id = %s
            ORDER BY create_time DESC
            LIMIT 30
        """
        cursor.execute(query, (sku_id_found,))
        reviews = fetch_all_dicts(cursor)

        if not reviews:
            return json.dumps({
                "type": "purchase_recommendation",
                "product_name": product_name_found or sku_id_found,
                "sku_id": sku_id_found,
                "recommendation": "neutral",
                "summary": "暂无评论数据，无法给出购买建议。",
                "pros": [],
                "cons": []
            }, ensure_ascii=False)

        engine = ReviewAnalysisEngine()
        analysis_result = engine.analyze_product_reviews(
            sku_id=sku_id_found,
            product_name=product_name_found or sku_id_found,
            reviews=reviews
        )

        positive_rate = 0
        if analysis_result.total_reviews > 0:
            positive_rate = analysis_result.positive_count / analysis_result.total_reviews * 100

        pros = [p.get("point", "") for p in analysis_result.positive_points[:3]]
        cons = [p.get("point", "") for p in analysis_result.negative_points[:3]]

        if positive_rate >= 70:
            recommendation = "recommended"
            recommendation_text = "推荐购买"
        elif positive_rate >= 50:
            recommendation = "neutral"
            recommendation_text = "可以考虑"
        else:
            recommendation = "not_recommended"
            recommendation_text = "不推荐"

        summary_parts = []
        if pros:
            summary_parts.append(f"优点：{', '.join(pros[:2])}")
        if cons:
            summary_parts.append(f"注意：{', '.join(cons[:2])}")
        
        summary = f"该商品好评率{positive_rate:.0f}%。{'; '.join(summary_parts)}。"

        return json.dumps({
            "type": "purchase_recommendation",
            "product_name": analysis_result.product_name,
            "sku_id": analysis_result.sku_id,
            "recommendation": recommendation,
            "recommendation_text": recommendation_text,
            "positive_rate": round(positive_rate, 1),
            "total_reviews": analysis_result.total_reviews,
            "pros": pros,
            "cons": cons,
            "summary": summary
        }, ensure_ascii=False)

    except Exception as e:
        return f"购买建议生成失败: {str(e)}"
    finally:
        try:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
        except:
            pass
