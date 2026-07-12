# -*- coding: utf-8 -*-
"""
Token消耗统计工具
================
通过LangChain Callback机制，自动记录每次LLM调用的token消耗。
支持按会话、按意图分类统计，输出汇总报告。

集成方式：在 agent.ainvoke 的 config["callbacks"] 中添加 TokenTracker 实例。
"""

import json
import os
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import defaultdict
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult


class TokenTracker(BaseCallbackHandler):
    """Token消耗追踪器，作为LangChain Callback Handler集成"""

    def __init__(self, results_dir: str = None):
        self.records: List[Dict[str, Any]] = []
        self.current_trace_id: Optional[str] = None
        self.current_intent: Optional[str] = None

        if results_dir is None:
            results_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "tests", "results"
            )
        self.results_dir = results_dir
        os.makedirs(results_dir, exist_ok=True)

    def set_trace_info(self, trace_id: str = None, intent: str = None):
        """设置当前追踪信息"""
        self.current_trace_id = trace_id
        self.current_intent = intent

    def on_llm_start(self, serialized, prompts, **kwargs):
        """LLM调用开始"""
        pass

    def on_llm_end(self, response: LLMResult, **kwargs):
        """LLM调用结束，记录token消耗"""
        for generation in response.flatten():
            gen_info = generation.generation_info or {}
            token_usage = gen_info.get("token_usage", {}) or gen_info.get("usage", {})

            # 兼容不同LLM返回格式
            prompt_tokens = (
                token_usage.get("prompt_tokens")
                or token_usage.get("input_tokens")
                or token_usage.get("inputTokenCount")
                or 0
            )
            completion_tokens = (
                token_usage.get("completion_tokens")
                or token_usage.get("output_tokens")
                or token_usage.get("outputTokenCount")
                or 0
            )
            total_tokens = (
                token_usage.get("total_tokens")
                or prompt_tokens + completion_tokens
                or 0
            )

            # 只有实际有token数据才记录
            if total_tokens > 0 or prompt_tokens > 0 or completion_tokens > 0:
                record = {
                    "timestamp": datetime.now().isoformat(),
                    "trace_id": self.current_trace_id,
                    "intent": self.current_intent,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "model_name": getattr(response, "llm_output", {}).get("model_name", "unknown") if hasattr(response, "llm_output") else "unknown"
                }
                self.records.append(record)
                print(f"[TokenTracker] LLM调用: input={prompt_tokens}, output={completion_tokens}, total={total_tokens}")

    def on_llm_error(self, error, **kwargs):
        """LLM调用错误"""
        print(f"[TokenTracker] LLM调用错误: {error}")

    def get_summary(self) -> Dict[str, Any]:
        """获取Token消耗汇总统计"""
        if not self.records:
            return {"total_calls": 0, "total_tokens": 0}

        total_prompt = sum(r["prompt_tokens"] for r in self.records)
        total_completion = sum(r["completion_tokens"] for r in self.records)
        total_tokens = sum(r["total_tokens"] for r in self.records)

        # 按意图分组统计
        by_intent = defaultdict(lambda: {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        for r in self.records:
            intent = r.get("intent") or "unknown"
            by_intent[intent]["calls"] += 1
            by_intent[intent]["prompt_tokens"] += r["prompt_tokens"]
            by_intent[intent]["completion_tokens"] += r["completion_tokens"]
            by_intent[intent]["total_tokens"] += r["total_tokens"]

        return {
            "total_calls": len(self.records),
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_tokens,
            "avg_tokens_per_call": round(total_tokens / len(self.records), 1) if self.records else 0,
            "by_intent": dict(by_intent),
            "timestamp": datetime.now().isoformat()
        }

    def save_report(self, filename: str = "token_usage.json"):
        """保存Token消耗报告到文件"""
        report = self.get_summary()
        filepath = os.path.join(self.results_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"[TokenTracker] 报告已保存: {filepath}")
        return filepath

    def print_summary(self):
        """打印Token消耗摘要"""
        summary = self.get_summary()
        if summary["total_calls"] == 0:
            print("\n========== Token消耗统计 ==========")
            print("暂无Token使用记录（LLM可能未返回token_usage信息）")
            print("提示：智谱GLM-4的API响应中包含usage字段，需确认LangChain是否正确解析")
            print("=====================================\n")
            return

        print("\n========== Token消耗统计 ==========")
        print(f"总调用次数: {summary['total_calls']}")
        print(f"总Token消耗: {summary['total_tokens']}")
        print(f"  输入Token: {summary['total_prompt_tokens']}")
        print(f"  输出Token: {summary['total_completion_tokens']}")
        print(f"  平均每次: {summary['avg_tokens_per_call']}")
        print()
        print("按意图分组:")
        for intent, stats in summary.get("by_intent", {}).items():
            print(f"  {intent}: {stats['calls']}次, 总{stats['total_tokens']}tokens")
        print("=====================================\n")


# 全局Token追踪实例
token_tracker = TokenTracker()
