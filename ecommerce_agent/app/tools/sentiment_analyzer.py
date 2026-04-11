'''
情感分析工具
'''

import json
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from langchain_core.messages import SystemMessage, HumanMessage
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from my_llm import llm


@dataclass
class SentimentResult:
    sentiment: str
    confidence: float
    positive_points: List[str]
    negative_points: List[str]
    keywords: List[str]


@dataclass
class ReviewAnalysisResult:
    sku_id: str
    product_name: str
    total_reviews: int
    positive_count: int
    negative_count: int
    neutral_count: int
    positive_points: List[Dict[str, Any]]
    negative_points: List[Dict[str, Any]]
    divergence_score: float
    contradictions: List[Dict[str, Any]]
    summary: str


class SentimentAnalyzer:
    POSITIVE_KEYWORDS = [
        "好", "棒", "满意", "喜欢", "推荐", "不错", "值得", "优秀", "完美",
        "快", "流畅", "漂亮", "好看", "实惠", "便宜", "质量好", "好用",
        "舒适", "精致", "高端", "大气", "超值", "惊喜", "赞", "给力",
        "清晰", "灵敏", "耐用", "稳定", "强劲", "出色", "满分"
    ]
    
    NEGATIVE_KEYWORDS = [
        "差", "烂", "垃圾", "失望", "后悔", "不好", "不行", "问题", "毛病",
        "慢", "卡", "贵", "坑", "假", "破", "坏", "掉", "断", "裂",
        "退货", "退款", "投诉", "差评", "难用", "难看", "不推荐",
        "发热", "噪音", "模糊", "延迟", "卡顿", "闪退", "崩溃"
    ]

    def __init__(self):
        self.llm = llm

    def analyze_single_review(self, content: str, score: float = None) -> SentimentResult:
        if not content or not content.strip():
            return SentimentResult(
                sentiment="neutral",
                confidence=0.5,
                positive_points=[],
                negative_points=[],
                keywords=[]
            )
        
        if score is not None:
            try:
                score = float(score)
            except:
                score = None
            
            if score is not None:
                if score >= 4.0:
                    base_sentiment = "positive"
                    base_confidence = min(0.9, 0.6 + (score - 4.0) * 0.15)
                elif score <= 2.0:
                    base_sentiment = "negative"
                    base_confidence = min(0.9, 0.6 + (2.0 - score) * 0.15)
                else:
                    base_sentiment = "neutral"
                    base_confidence = 0.5
            else:
                base_sentiment, base_confidence = self._keyword_based_sentiment(content)
        else:
            base_sentiment, base_confidence = self._keyword_based_sentiment(content)
        
        positive_points, negative_points, keywords = self._extract_points_and_keywords(content)
        
        if positive_points and not negative_points:
            sentiment = "positive"
            confidence = max(base_confidence, 0.7)
        elif negative_points and not positive_points:
            sentiment = "negative"
            confidence = max(base_confidence, 0.7)
        elif positive_points and negative_points:
            if len(positive_points) > len(negative_points):
                sentiment = "positive"
            elif len(negative_points) > len(positive_points):
                sentiment = "negative"
            else:
                sentiment = base_sentiment
            confidence = 0.6
        else:
            sentiment = base_sentiment
            confidence = base_confidence
        
        return SentimentResult(
            sentiment=sentiment,
            confidence=confidence,
            positive_points=positive_points,
            negative_points=negative_points,
            keywords=keywords
        )

    def _keyword_based_sentiment(self, content: str) -> Tuple[str, float]:
        content_lower = content.lower()
        positive_count = sum(1 for kw in self.POSITIVE_KEYWORDS if kw in content_lower)
        negative_count = sum(1 for kw in self.NEGATIVE_KEYWORDS if kw in content_lower)
        
        total = positive_count + negative_count
        if total == 0:
            return "neutral", 0.5
        
        positive_ratio = positive_count / total
        if positive_ratio >= 0.7:
            return "positive", min(0.85, 0.5 + positive_count * 0.05)
        elif positive_ratio <= 0.3:
            return "negative", min(0.85, 0.5 + negative_count * 0.05)
        else:
            return "neutral", 0.5

    def _extract_points_and_keywords(self, content: str) -> Tuple[List[str], List[str], List[str]]:
        positive_points = []
        negative_points = []
        keywords = []
        
        sentences = re.split(r'[。！？\n]', content)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        for sentence in sentences:
            has_positive = any(kw in sentence for kw in self.POSITIVE_KEYWORDS)
            has_negative = any(kw in sentence for kw in self.NEGATIVE_KEYWORDS)
            
            if has_positive and not has_negative:
                positive_points.append(sentence)
            elif has_negative and not has_positive:
                negative_points.append(sentence)
            elif has_positive and has_negative:
                positive_points.append(sentence)
                negative_points.append(sentence)
        
        all_keywords = self.POSITIVE_KEYWORDS + self.NEGATIVE_KEYWORDS
        keywords = [kw for kw in all_keywords if kw in content]
        
        return positive_points[:5], negative_points[:5], keywords[:10]

    def analyze_reviews_batch(self, reviews: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results = []
        for review in reviews:
            content = review.get("content", "")
            score = review.get("score")
            
            sentiment_result = self.analyze_single_review(content, score)
            
            results.append({
                "sku_id": review.get("sku_id", ""),
                "content": content,
                "score": score,
                "sentiment": sentiment_result.sentiment,
                "confidence": sentiment_result.confidence,
                "positive_points": sentiment_result.positive_points,
                "negative_points": sentiment_result.negative_points,
                "keywords": sentiment_result.keywords
            })
        
        return results


class ReviewAnalysisEngine:
    def __init__(self):
        self.sentiment_analyzer = SentimentAnalyzer()
        self.llm = llm

    def analyze_product_reviews(
        self,
        sku_id: str,
        product_name: str,
        reviews: List[Dict[str, Any]]
    ) -> ReviewAnalysisResult:
        if not reviews:
            return ReviewAnalysisResult(
                sku_id=sku_id,
                product_name=product_name,
                total_reviews=0,
                positive_count=0,
                negative_count=0,
                neutral_count=0,
                positive_points=[],
                negative_points=[],
                divergence_score=0.0,
                contradictions=[],
                summary="暂无评论数据"
            )
        
        analyzed_reviews = self.sentiment_analyzer.analyze_reviews_batch(reviews)
        
        positive_count = sum(1 for r in analyzed_reviews if r["sentiment"] == "positive")
        negative_count = sum(1 for r in analyzed_reviews if r["sentiment"] == "negative")
        neutral_count = sum(1 for r in analyzed_reviews if r["sentiment"] == "neutral")
        
        positive_points = self._aggregate_points(analyzed_reviews, "positive_points")
        negative_points = self._aggregate_points(analyzed_reviews, "negative_points")
        
        divergence_score = self._calculate_divergence(positive_count, negative_count, neutral_count)
        
        contradictions = self._identify_contradictions(positive_points, negative_points)
        
        summary = self._generate_summary(
            product_name, 
            len(reviews), 
            positive_count, 
            negative_count,
            positive_points[:3],
            negative_points[:3],
            contradictions
        )
        
        return ReviewAnalysisResult(
            sku_id=sku_id,
            product_name=product_name,
            total_reviews=len(reviews),
            positive_count=positive_count,
            negative_count=negative_count,
            neutral_count=neutral_count,
            positive_points=positive_points[:10],
            negative_points=negative_points[:10],
            divergence_score=divergence_score,
            contradictions=contradictions,
            summary=summary
        )

    def _aggregate_points(self, analyzed_reviews: List[Dict], point_type: str) -> List[Dict[str, Any]]:
        point_counter = {}
        
        for review in analyzed_reviews:
            points = review.get(point_type, [])
            for point in points:
                if point in point_counter:
                    point_counter[point]["count"] += 1
                else:
                    point_counter[point] = {"point": point, "count": 1}
        
        sorted_points = sorted(point_counter.values(), key=lambda x: x["count"], reverse=True)
        return sorted_points

    def _calculate_divergence(self, positive: int, negative: int, neutral: int) -> float:
        total = positive + negative + neutral
        if total == 0:
            return 0.0
        
        if positive == 0 or negative == 0:
            return 0.0
        
        positive_ratio = positive / total
        negative_ratio = negative / total
        
        divergence = min(positive_ratio, negative_ratio) * 2
        
        return round(divergence * 100, 1)

    def _identify_contradictions(
        self, 
        positive_points: List[Dict], 
        negative_points: List[Dict]
    ) -> List[Dict[str, Any]]:
        contradictions = []
        
        contradiction_keywords = [
            ("价格", ["贵", "便宜", "实惠", "值", "坑"]),
            ("质量", ["好", "差", "烂", "棒", "问题"]),
            ("外观", ["好看", "漂亮", "丑", "难看"]),
            ("性能", ["快", "慢", "流畅", "卡", "稳定"]),
            ("续航", ["长", "短", "耐用", "不耐用"]),
            ("屏幕", ["清晰", "模糊", "好", "差"]),
            ("音质", ["好", "差", "清晰", "杂音"]),
        ]
        
        for topic, keywords in contradiction_keywords:
            pos_mentions = []
            neg_mentions = []
            
            for p in positive_points[:10]:
                point = p.get("point", "")
                if topic in point or any(kw in point for kw in keywords):
                    pos_mentions.append(point)
            
            for p in negative_points[:10]:
                point = p.get("point", "")
                if topic in point or any(kw in point for kw in keywords):
                    neg_mentions.append(point)
            
            if pos_mentions and neg_mentions:
                contradictions.append({
                    "topic": topic,
                    "positive_views": pos_mentions[:2],
                    "negative_views": neg_mentions[:2],
                    "conflict_level": "high" if len(pos_mentions) >= 2 and len(neg_mentions) >= 2 else "medium"
                })
        
        return contradictions

    def _generate_summary(
        self,
        product_name: str,
        total: int,
        positive: int,
        negative: int,
        positive_points: List[Dict],
        negative_points: List[Dict],
        contradictions: List[Dict]
    ) -> str:
        if total == 0:
            return f"暂无{product_name}的评论数据。"
        
        positive_ratio = positive / total * 100 if total > 0 else 0
        
        summary_parts = [f"{product_name}共有{total}条评价，好评率{positive_ratio:.1f}%。"]
        
        if positive_points:
            top_positive = positive_points[0].get("point", "") if positive_points else ""
            if top_positive:
                summary_parts.append(f"用户普遍认可：{top_positive[:50]}。")
        
        if negative_points:
            top_negative = negative_points[0].get("point", "") if negative_points else ""
            if top_negative:
                summary_parts.append(f"主要槽点：{top_negative[:50]}。")
        
        if contradictions:
            topics = [c["topic"] for c in contradictions[:2]]
            summary_parts.append(f"评价存在分歧的方面：{', '.join(topics)}。")
        
        return "".join(summary_parts)

    def generate_llm_summary(self, analysis_result: ReviewAnalysisResult) -> str:
        return analysis_result.summary


def analyze_sentiment_for_review(content: str, score: float = None) -> Dict[str, Any]:
    analyzer = SentimentAnalyzer()
    result = analyzer.analyze_single_review(content, score)
    return asdict(result)


def analyze_product_reviews_full(
    sku_id: str,
    product_name: str,
    reviews: List[Dict[str, Any]]
) -> Dict[str, Any]:
    engine = ReviewAnalysisEngine()
    result = engine.analyze_product_reviews(sku_id, product_name, reviews)
    return asdict(result)
