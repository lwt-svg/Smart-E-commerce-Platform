'''
用户画像管理类 - 用户画像核心模块
'''
import os
import json
import re
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
from langchain_core.messages import HumanMessage, AIMessage

from .config import (
    CHROMA_PERSIST_DIR,
    CHROMA_COLLECTION_NAME,
    PROFILE_SUMMARY_MAX_LENGTH,
    PROFILE_MAX_PREFERENCES,
    PROFILE_DECAY_FACTOR,
    PROFILE_MIN_WEIGHT
)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "bge-m3")


@dataclass
class Preference:
    preference_type: str
    content: str
    weight: float
    count: int
    last_updated: str
    metadata: Dict[str, Any]


@dataclass
class UserProfile:
    user_id: str
    summary: str
    brand_preferences: List[str]
    category_preferences: List[str]
    budget_range: List[int]
    key_features: List[str]
    decision_style: str
    total_sessions: int
    last_updated: str


class ProfileManager:
    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False)
        )
        
        try:
            self.embedding_func = embedding_functions.OllamaEmbeddingFunction(
                url=OLLAMA_BASE_URL,
                model_name=OLLAMA_MODEL
            )
            print(f"[ProfileManager] 使用 Ollama embedding: {OLLAMA_MODEL} @ {OLLAMA_BASE_URL}")
        except Exception as e:
            print(f"[ProfileManager] Ollama embedding 初始化失败，使用默认: {e}")
            self.embedding_func = embedding_functions.DefaultEmbeddingFunction()
        
        self.collection = self.client.get_or_create_collection(
            name=CHROMA_COLLECTION_NAME,
            embedding_function=self.embedding_func,
            metadata={"hnsw:space": "cosine"}
        )
        self.summary_cache: Dict[str, UserProfile] = {}
        print(f"[ProfileManager] ChromaDB 初始化完成，存储路径: {CHROMA_PERSIST_DIR}")

    def _get_user_collection_suffix(self, user_id: str) -> str:
        return hashlib.md5(user_id.encode()).hexdigest()[:8]

    def _build_preference_id(self, user_id: str, preference_type: str, key: str) -> str:
        return f"{user_id}_{preference_type}_{key}"

    async def extract_preferences_from_session(
        self,
        messages: List[Dict[str, Any]],
        llm
    ) -> Dict[str, Any]:
        if not messages:
            return {}

        conversation_text = self._format_conversation(messages)
        
        preferences = self._extract_by_rules(messages)
        
        if preferences:
            print(f"[ProfileManager] 规则提取到的偏好: {preferences}")
            return preferences

        extraction_prompt = f"""请分析以下电商对话记录，提取用户的偏好信息。

对话记录：
{conversation_text}

请以JSON格式返回以下信息（只返回JSON，不要其他内容）：
{{
    "brands": ["用户查询或关注的品牌列表"],
    "categories": ["用户查询或关注的品类列表"],
    "budget_min": 预算下限（数字，如果没有则null）,
    "budget_max": 预算上限（数字，如果没有则null）,
    "features": ["用户关注的特征，如：性价比、续航、拍照、外观等"],
    "decision_style": "决策风格：价格敏感型/品质导向型/品牌忠诚型/功能导向型",
    "sentiment": "整体情绪：积极/中性/消极"
}}

注意：
1. 只提取明确提到的信息，不要推测
2. 品牌名称统一为：华为、苹果、小米、荣耀、OPPO、vivo、三星等
3. 品类统一为：手机、平板、电脑、耳机、手表等
4. 如果没有相关信息，对应字段返回空列表或null"""

        try:
            response = await llm.ainvoke([HumanMessage(content=extraction_prompt)])
            result_text = response.content.strip()

            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]

            preferences = json.loads(result_text)
            print(f"[ProfileManager] LLM提取到的偏好: {preferences}")
            return preferences

        except json.JSONDecodeError as e:
            print(f"[ProfileManager] JSON解析失败: {e}")
            return {}
        except Exception as e:
            print(f"[ProfileManager] 偏好提取失败: {e}")
            return {}

    def _extract_by_rules(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        brands_set = set()
        categories_set = set()
        features_set = set()
        budget_min = None
        budget_max = None
        
        brand_keywords = ["华为", "苹果", "小米", "荣耀", "OPPO", "vivo", "三星", "一加", "realme", "红米", "iPhone", "HUAWEI", "Xiaomi"]
        category_keywords = ["手机", "平板", "电脑", "耳机", "手表", "笔记本", "显示器", "键盘", "鼠标"]
        feature_keywords = ["性价比", "续航", "拍照", "外观", "性能", "屏幕", "音质", "快充", "轻薄", "游戏"]
        
        for msg in messages:
            content = msg.get("content", "").lower()
            
            for brand in brand_keywords:
                if brand.lower() in content:
                    brands_set.add(brand)
            
            for cat in category_keywords:
                if cat in content:
                    categories_set.add(cat)
            
            for feat in feature_keywords:
                if feat in content:
                    features_set.add(feat)
            
            budget_patterns = [
                r"(\d+)[块元]?(左右|以内|以下|预算)",
                r"预算.*?(\d+)",
                r"(\d+).*?(\d+).*?[块元]",
            ]
            for pattern in budget_patterns:
                match = re.search(pattern, content)
                if match:
                    groups = match.groups()
                    if len(groups) >= 2 and groups[1] and groups[1].isdigit():
                        budget_min = int(groups[0]) if budget_min is None else min(budget_min, int(groups[0]))
                        budget_max = int(groups[1]) if budget_max is None else max(budget_max, int(groups[1]))
                    elif groups[0].isdigit():
                        val = int(groups[0])
                        if budget_max is None or val > budget_max:
                            budget_max = val
        
        if not brands_set and not categories_set:
            return {}
        
        return {
            "brands": list(brands_set),
            "categories": list(categories_set),
            "budget_min": budget_min,
            "budget_max": budget_max,
            "features": list(features_set),
            "decision_style": None,
            "sentiment": None
        }

    def _format_conversation(self, messages: List[Dict[str, Any]]) -> str:
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if role == "user":
                lines.append(f"用户: {content}")
            elif role == "assistant":
                lines.append(f"助手: {content}")
        return "\n".join(lines[-20:])

    async def update_user_profile(
        self,
        user_id: str,
        new_preferences: Dict[str, Any]
    ) -> None:
        if not user_id or not new_preferences:
            return

        now = datetime.now().isoformat()

        brands = new_preferences.get("brands", [])
        for brand in brands:
            if brand:
                await self._update_preference(
                    user_id=user_id,
                    preference_type="brand",
                    key=brand,
                    content=f"用户偏好{brand}品牌",
                    now=now
                )

        categories = new_preferences.get("categories", [])
        for category in categories:
            if category:
                await self._update_preference(
                    user_id=user_id,
                    preference_type="category",
                    key=category,
                    content=f"用户关注{category}品类",
                    now=now
                )

        features = new_preferences.get("features", [])
        for feature in features:
            if feature:
                await self._update_preference(
                    user_id=user_id,
                    preference_type="feature",
                    key=feature,
                    content=f"用户关注{feature}",
                    now=now
                )

        budget_min = new_preferences.get("budget_min")
        budget_max = new_preferences.get("budget_max")
        if budget_min or budget_max:
            budget_key = f"{budget_min or 0}_{budget_max or 99999}"
            content = f"用户预算区间: {budget_min or '不限'}-{budget_max or '不限'}元"
            await self._update_preference(
                user_id=user_id,
                preference_type="budget",
                key=budget_key,
                content=content,
                now=now,
                metadata={"budget_min": budget_min, "budget_max": budget_max}
            )

        decision_style = new_preferences.get("decision_style")
        if decision_style:
            await self._update_preference(
                user_id=user_id,
                preference_type="decision_style",
                key=decision_style,
                content=f"用户决策风格: {decision_style}",
                now=now
            )

        await self._apply_decay_and_cleanup(user_id)
        await self._regenerate_summary(user_id)

    async def _update_preference(
        self,
        user_id: str,
        preference_type: str,
        key: str,
        content: str,
        now: str,
        metadata: Dict[str, Any] = None
    ) -> None:
        pref_id = self._build_preference_id(user_id, preference_type, key)

        try:
            existing = self.collection.get(ids=[pref_id])
            if existing and existing["metadatas"]:
                old_meta = existing["metadatas"][0]
                old_weight = float(old_meta.get("weight", 0.5))
                old_count = int(old_meta.get("count", 0))

                new_weight = old_weight * PROFILE_DECAY_FACTOR + 1.0 * (1 - PROFILE_DECAY_FACTOR)
                new_count = old_count + 1

                self.collection.update(
                    ids=[pref_id],
                    metadatas=[{
                        "user_id": user_id,
                        "preference_type": preference_type,
                        "key": key,
                        "weight": new_weight,
                        "count": new_count,
                        "last_updated": now,
                        **(metadata or {})
                    }]
                )
                print(f"[ProfileManager] 更新偏好: {pref_id}, weight: {new_weight:.2f}, count: {new_count}")
            else:
                self.collection.add(
                    ids=[pref_id],
                    documents=[content],
                    metadatas=[{
                        "user_id": user_id,
                        "preference_type": preference_type,
                        "key": key,
                        "weight": 1.0,
                        "count": 1,
                        "last_updated": now,
                        **(metadata or {})
                    }]
                )
                print(f"[ProfileManager] 新增偏好: {pref_id}")
        except Exception as e:
            print(f"[ProfileManager] 更新偏好失败: {e}")

    async def _apply_decay_and_cleanup(self, user_id: str) -> None:
        try:
            all_prefs = self.collection.get(
                where={"user_id": user_id}
            )

            if not all_prefs or not all_prefs["ids"]:
                return

            ids_to_delete = []
            for i, pref_id in enumerate(all_prefs["ids"]):
                meta = all_prefs["metadatas"][i]
                weight = float(meta.get("weight", 1.0))

                new_weight = weight * PROFILE_DECAY_FACTOR
                if new_weight < PROFILE_MIN_WEIGHT:
                    ids_to_delete.append(pref_id)
                else:
                    self.collection.update(
                        ids=[pref_id],
                        metadatas=[{**meta, "weight": new_weight}]
                    )

            if ids_to_delete:
                self.collection.delete(ids=ids_to_delete)
                print(f"[ProfileManager] 删除低权重偏好: {len(ids_to_delete)} 条")

            if len(all_prefs["ids"]) - len(ids_to_delete) > PROFILE_MAX_PREFERENCES:
                prefs_with_weights = [
                    (pref_id, float(meta.get("weight", 0)))
                    for pref_id, meta in zip(all_prefs["ids"], all_prefs["metadatas"])
                ]
                prefs_with_weights.sort(key=lambda x: x[1], reverse=True)
                ids_to_delete = [p[0] for p in prefs_with_weights[PROFILE_MAX_PREFERENCES:]]
                if ids_to_delete:
                    self.collection.delete(ids=ids_to_delete)
                    print(f"[ProfileManager] 删除超量偏好: {len(ids_to_delete)} 条")

        except Exception as e:
            print(f"[ProfileManager] 清理偏好失败: {e}")

    async def _regenerate_summary(self, user_id: str, llm=None) -> None:
        try:
            all_prefs = self.collection.get(
                where={"user_id": user_id}
            )

            if not all_prefs or not all_prefs["ids"]:
                return

            brands = []
            categories = []
            features = []
            budget_min = None
            budget_max = None
            decision_style = None

            for meta in all_prefs["metadatas"]:
                pref_type = meta.get("preference_type")
                key = meta.get("key")
                weight = float(meta.get("weight", 0))

                if pref_type == "brand" and weight > 0.3:
                    brands.append((key, weight))
                elif pref_type == "category" and weight > 0.3:
                    categories.append((key, weight))
                elif pref_type == "feature" and weight > 0.3:
                    features.append((key, weight))
                elif pref_type == "budget":
                    b_min = meta.get("budget_min")
                    b_max = meta.get("budget_max")
                    if b_min:
                        budget_min = b_min if budget_min is None else max(budget_min, budget_min)
                    if b_max:
                        budget_max = b_max if budget_max is None else min(budget_max, b_max)
                elif pref_type == "decision_style" and weight > 0.3:
                    decision_style = key

            brands.sort(key=lambda x: x[1], reverse=True)
            categories.sort(key=lambda x: x[1], reverse=True)
            features.sort(key=lambda x: x[1], reverse=True)

            summary_parts = []
            if brands:
                top_brands = [b[0] for b in brands[:3]]
                summary_parts.append(f"偏好品牌: {', '.join(top_brands)}")
            if categories:
                top_cats = [c[0] for c in categories[:3]]
                summary_parts.append(f"关注品类: {', '.join(top_cats)}")
            if budget_min or budget_max:
                budget_str = f"预算: {budget_min or '不限'}-{budget_max or '不限'}元"
                summary_parts.append(budget_str)
            if features:
                top_features = [f[0] for f in features[:3]]
                summary_parts.append(f"关注点: {', '.join(top_features)}")
            if decision_style:
                summary_parts.append(f"决策风格: {decision_style}")

            summary = "；".join(summary_parts) if summary_parts else "暂无明确偏好"

            profile = UserProfile(
                user_id=user_id,
                summary=summary[:PROFILE_SUMMARY_MAX_LENGTH],
                brand_preferences=[b[0] for b in brands[:5]],
                category_preferences=[c[0] for c in categories[:5]],
                budget_range=[budget_min or 0, budget_max or 99999],
                key_features=[f[0] for f in features[:5]],
                decision_style=decision_style or "未确定",
                total_sessions=len(set(meta.get("last_updated", "")[:10] for meta in all_prefs["metadatas"])),
                last_updated=datetime.now().isoformat()
            )

            self.summary_cache[user_id] = profile
            print(f"[ProfileManager] 生成画像摘要: {summary}")

        except Exception as e:
            print(f"[ProfileManager] 生成摘要失败: {e}")

    def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        if user_id in self.summary_cache:
            return self.summary_cache[user_id]

        try:
            all_prefs = self.collection.get(
                where={"user_id": user_id}
            )

            if not all_prefs or not all_prefs["ids"]:
                return None

            import asyncio
            asyncio.create_task(self._regenerate_summary(user_id))
            return None

        except Exception as e:
            print(f"[ProfileManager] 获取画像失败: {e}")
            return None

    def get_profile_summary(self, user_id: str) -> str:
        profile = self.get_user_profile(user_id)
        if profile:
            return profile.summary
        return ""

    def get_relevant_preferences(
        self,
        user_id: str,
        query: str,
        limit: int = 3
    ) -> List[str]:
        try:
            results = self.collection.query(
                query_texts=[query],
                where={"user_id": user_id},
                n_results=limit
            )

            if results and results["documents"]:
                preferences = []
                for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
                    weight = float(meta.get("weight", 0))
                    if weight > PROFILE_MIN_WEIGHT:
                        preferences.append(doc)
                return preferences

        except Exception as e:
            print(f"[ProfileManager] 检索偏好失败: {e}")

        return []

    def build_profile_prompt_section(
        self,
        user_id: str,
        current_query: str = ""
    ) -> str:
        if not user_id:
            return ""

        summary = self.get_profile_summary(user_id)
        if not summary:
            return ""

        relevant_prefs = []
        if current_query:
            relevant_prefs = self.get_relevant_preferences(user_id, current_query, limit=2)

        profile_section = f"\n【用户画像】\n{summary}"

        if relevant_prefs:
            profile_section += f"\n\n【当前问题相关偏好】\n" + "\n".join(f"- {p}" for p in relevant_prefs)

        return profile_section


profile_manager = ProfileManager()
