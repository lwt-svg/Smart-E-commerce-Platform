'''
构建情感分析数据库脚本
'''
import os
import pymysql
import json
from typing import List, Dict, Any, Optional
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.tools.sentiment_analyzer import SentimentAnalyzer, analyze_sentiment_for_review

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "123456")
DB_NAME = os.getenv("DB_NAME", "muxi_shop")


def get_comments_from_mysql():
    conn = pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT content, sku_id, reference_name, score, nickname, create_time,
                   sentiment, sentiment_confidence, positive_points, negative_points,
                   is_verified, helpful_count
            FROM comment
            WHERE content IS NOT NULL AND content != ''
        """)
        rows = cursor.fetchall()
        return rows
    finally:
        cursor.close()
        conn.close()


def build_sentiment_vector_db(use_llm_summary: bool = False):
    print("正在从 MySQL 读取评论...")
    rows = get_comments_from_mysql()
    print(f"共读取 {len(rows)} 条评论")

    if not rows:
        print("没有评论数据，请先运行评论生成脚本。")
        return

    sentiment_analyzer = SentimentAnalyzer()
    embeddings = OllamaEmbeddings(
        model="bge-m3",
        base_url="http://localhost:11434"
    )

    positive_documents = []
    negative_documents = []
    all_documents = []

    print("正在进行情感分析和观点提取...")
    for i, row in enumerate(rows):
        content = row.get("content", "").strip()
        if not content:
            continue

        sku_id = str(row.get("sku_id", ""))
        reference_name = row.get("reference_name", "") or ""
        score = float(row.get("score")) if row.get("score") is not None else 0.0
        nickname = row.get("nickname", "") or ""
        create_time = str(row.get("create_time", ""))
        is_verified = int(row.get("is_verified", 0) or 0)
        helpful_count = int(row.get("helpful_count", 0) or 0)

        db_sentiment = row.get("sentiment")
        db_confidence = row.get("sentiment_confidence")
        db_positive_points = row.get("positive_points")
        db_negative_points = row.get("negative_points")

        if db_sentiment and db_sentiment in ["positive", "negative", "neutral"]:
            sentiment = db_sentiment
            confidence = float(db_confidence) if db_confidence else 0.5
            
            if db_positive_points:
                try:
                    positive_points = json.loads(db_positive_points) if isinstance(db_positive_points, str) else db_positive_points
                except:
                    positive_points = []
            else:
                positive_points = []
            
            if db_negative_points:
                try:
                    negative_points = json.loads(db_negative_points) if isinstance(db_negative_points, str) else db_negative_points
                except:
                    negative_points = []
            else:
                negative_points = []
        else:
            sentiment_result = sentiment_analyzer.analyze_single_review(content, score)
            sentiment = sentiment_result.sentiment
            positive_points = sentiment_result.positive_points
            negative_points = sentiment_result.negative_points
            confidence = sentiment_result.confidence

        base_metadata = {
            "sku_id": sku_id,
            "reference_name": reference_name,
            "score": score,
            "nickname": nickname,
            "create_time": create_time,
            "sentiment": sentiment,
            "confidence": confidence,
            "is_verified": is_verified,
            "helpful_count": helpful_count
        }

        full_content = (
            f"商品名称：{reference_name}\n"
            f"评论内容：{content}\n"
            f"评分：{score}\n"
            f"情感倾向：{sentiment}\n"
            f"正面观点：{'；'.join(positive_points) if positive_points else '无'}\n"
            f"负面观点：{'；'.join(negative_points) if negative_points else '无'}"
        )
        
        all_doc = Document(
            page_content=full_content,
            metadata={**base_metadata, "doc_type": "full_review"}
        )
        all_documents.append(all_doc)

        if sentiment == "positive" and positive_points:
            for point in positive_points:
                point_content = f"【正面评价】{reference_name}：{point}"
                point_doc = Document(
                    page_content=point_content,
                    metadata={
                        **base_metadata,
                        "doc_type": "positive_point",
                        "point": point
                    }
                )
                positive_documents.append(point_doc)

        if sentiment == "negative" and negative_points:
            for point in negative_points:
                point_content = f"【负面评价】{reference_name}：{point}"
                point_doc = Document(
                    page_content=point_content,
                    metadata={
                        **base_metadata,
                        "doc_type": "negative_point",
                        "point": point
                    }
                )
                negative_documents.append(point_doc)

        if (i + 1) % 100 == 0:
            print(f"已处理 {i + 1}/{len(rows)} 条评论...")

    print(f"\n分析完成：")
    print(f"  - 全部评论文档：{len(all_documents)}")
    print(f"  - 正面观点文档：{len(positive_documents)}")
    print(f"  - 负面观点文档：{len(negative_documents)}")

    print("\n正在构建全部评论向量库...")
    all_persist_dir = "./chroma_db/reviews"
    vectordb_all = Chroma.from_documents(
        documents=all_documents,
        embedding=embeddings,
        persist_directory=all_persist_dir
    )
    vectordb_all.persist()
    print(f"全部评论向量库已保存至：{all_persist_dir}")

    print("\n正在构建正面观点向量库...")
    positive_persist_dir = "./chroma_db/reviews_positive"
    if positive_documents:
        vectordb_positive = Chroma.from_documents(
            documents=positive_documents,
            embedding=embeddings,
            persist_directory=positive_persist_dir
        )
        vectordb_positive.persist()
        print(f"正面观点向量库已保存至：{positive_persist_dir}")
    else:
        print("没有正面观点数据，跳过。")

    print("\n正在构建负面观点向量库...")
    negative_persist_dir = "./chroma_db/reviews_negative"
    if negative_documents:
        vectordb_negative = Chroma.from_documents(
            documents=negative_documents,
            embedding=embeddings,
            persist_directory=negative_persist_dir
        )
        vectordb_negative.persist()
        print(f"负面观点向量库已保存至：{negative_persist_dir}")
    else:
        print("没有负面观点数据，跳过。")

    print("\n向量库构建完成！")


def update_sentiment_vector_db(new_comments: List[Dict[str, Any]]):
    if not new_comments:
        print("没有新评论需要更新。")
        return

    sentiment_analyzer = SentimentAnalyzer()
    embeddings = OllamaEmbeddings(
        model="bge-m3",
        base_url="http://localhost:11434"
    )

    positive_documents = []
    negative_documents = []
    all_documents = []

    print(f"正在处理 {len(new_comments)} 条新评论...")
    for row in new_comments:
        content = row.get("content", "").strip()
        if not content:
            continue

        sku_id = str(row.get("sku_id", ""))
        reference_name = row.get("reference_name", "")
        score = row.get("score")
        nickname = row.get("nickname", "")
        create_time = str(row.get("create_time", ""))

        sentiment_result = sentiment_analyzer.analyze_single_review(content, score)
        sentiment = sentiment_result.sentiment
        positive_points = sentiment_result.positive_points
        negative_points = sentiment_result.negative_points
        confidence = sentiment_result.confidence

        base_metadata = {
            "sku_id": sku_id,
            "reference_name": reference_name,
            "score": score,
            "nickname": nickname,
            "create_time": create_time,
            "sentiment": sentiment,
            "confidence": confidence
        }

        full_content = (
            f"商品名称：{reference_name}\n"
            f"评论内容：{content}\n"
            f"评分：{score}\n"
            f"情感倾向：{sentiment}\n"
            f"正面观点：{'；'.join(positive_points) if positive_points else '无'}\n"
            f"负面观点：{'；'.join(negative_points) if negative_points else '无'}"
        )
        
        all_documents.append(Document(
            page_content=full_content,
            metadata={**base_metadata, "doc_type": "full_review"}
        ))

        if sentiment == "positive" and positive_points:
            for point in positive_points:
                positive_documents.append(Document(
                    page_content=f"【正面评价】{reference_name}：{point}",
                    metadata={**base_metadata, "doc_type": "positive_point", "point": point}
                ))

        if sentiment == "negative" and negative_points:
            for point in negative_points:
                negative_documents.append(Document(
                    page_content=f"【负面评价】{reference_name}：{point}",
                    metadata={**base_metadata, "doc_type": "negative_point", "point": point}
                ))

    if all_documents:
        print("正在增量更新全部评论向量库...")
        vectordb_all = Chroma(
            persist_directory="./chroma_db/reviews",
            embedding_function=embeddings
        )
        vectordb_all.add_documents(all_documents)
        print(f"已添加 {len(all_documents)} 条评论到全部评论向量库")

    if positive_documents:
        print("正在增量更新正面观点向量库...")
        vectordb_positive = Chroma(
            persist_directory="./chroma_db/reviews_positive",
            embedding_function=embeddings
        )
        vectordb_positive.add_documents(positive_documents)
        print(f"已添加 {len(positive_documents)} 条正面观点")

    if negative_documents:
        print("正在增量更新负面观点向量库...")
        vectordb_negative = Chroma(
            persist_directory="./chroma_db/reviews_negative",
            embedding_function=embeddings
        )
        vectordb_negative.add_documents(negative_documents)
        print(f"已添加 {len(negative_documents)} 条负面观点")

    print("增量更新完成！")


if __name__ == "__main__":
    build_sentiment_vector_db()
