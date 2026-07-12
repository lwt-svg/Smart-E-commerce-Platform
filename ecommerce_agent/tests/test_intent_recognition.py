# -*- coding: utf-8 -*-
"""
意图识别准确率测试框架
======================
测试 detect_intent 函数对13种意图的识别准确率，
输出详细的分类指标报告（TP/FP/FN/Precision/Recall/F1），
并将结果保存到 tests/results/intent_results.json。

用法：
    cd fastapi-langchain(latest)/ecommerce_agent
    python -m pytest tests/test_intent_recognition.py -v -s
    或
    python tests/test_intent_recognition.py
"""

import sys
import os
import json
import types
from datetime import datetime
from collections import defaultdict

# ============================================================
# 1. 添加项目根目录到 sys.path，使得 from app.agent 能正常工作
# ============================================================
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)


# ============================================================
# 2. Mock 重依赖模块，避免导入 app.agent 时因 redis/langgraph 等报错
#    所有 mock 必须在 import app.agent 之前完成
# ============================================================
def _setup_mocks():
    """
    在导入 app.agent 之前，向 sys.modules 注入 mock 模块，
    绕过 redis / langgraph / langchain / pymysql / chromadb 等重依赖。
    仅 mock 到足以让 detect_intent 函数正常可用的程度。
    """

    def _make_module(name, attrs=None):
        """快速创建一个 mock 模块并设置属性"""
        mod = types.ModuleType(name)
        if attrs:
            for k, v in attrs.items():
                setattr(mod, k, v)
        return mod

    # ---- Mock redis ----
    sys.modules['redis'] = _make_module('redis')
    mock_redis_async = _make_module('redis.asyncio', {
        'from_url': lambda *a, **kw: _make_module('mock_redis', {
            'get': lambda self, k: None,
            'setex': lambda self, *a, **kw: None,
        })
    })
    sys.modules['redis.asyncio'] = mock_redis_async

    # ---- Mock langgraph ----
    mock_state_graph = type('StateGraph', (), {
        '__init__': lambda self, *a, **kw: None,
        'add_node': lambda self, *a, **kw: None,
        'add_edge': lambda self, *a, **kw: None,
        'add_conditional_edges': lambda self, *a, **kw: None,
    })
    sys.modules['langgraph'] = _make_module('langgraph')
    sys.modules['langgraph.graph'] = _make_module('langgraph.graph', {
        'StateGraph': mock_state_graph,
        'MessagesState': dict,
        'START': '__start__',
        'END': '__end__',
    })

    # ---- Mock langchain_core ----
    for cls_name in ('SystemMessage', 'AIMessage', 'ToolMessage', 'HumanMessage'):
        pass  # 仅需类存在即可

    sys.modules['langchain_core'] = _make_module('langchain_core')
    sys.modules['langchain_core.messages'] = _make_module('langchain_core.messages', {
        'SystemMessage': type('SystemMessage', (), {'__init__': lambda self, content='': None}),
        'AIMessage': type('AIMessage', (), {
            '__init__': lambda self, content='', **kw: None,
            'tool_calls': [],
        }),
        'ToolMessage': type('ToolMessage', (), {
            '__init__': lambda self, content='', tool_call_id='': None,
        }),
        'HumanMessage': type('HumanMessage', (), {'__init__': lambda self, content='': None}),
    })
    sys.modules['langchain_core.runnables'] = _make_module('langchain_core.runnables', {
        'RunnableConfig': dict,
    })

    # ---- Mock my_llm ----
    # llm 在 agent.py 中作为模块属性使用，bind_tools / invoke 是普通函数调用
    mock_llm = _make_module('my_llm', {
        'llm': _make_module('MockLLM', {
            'bind_tools': lambda tools=None: None,
            'invoke': lambda msgs=None: None,
        }),
    })
    sys.modules['my_llm'] = mock_llm

    # ---- Mock app 内部子模块（agent.py 的相对导入） ----
    # 先确保 app 包在 sys.modules 中，且 __path__ 指向正确目录
    if 'app' not in sys.modules:
        app_mod = _make_module('app')
        app_mod.__path__ = [os.path.join(PROJECT_ROOT, 'app')]
        app_mod.__package__ = 'app'
        sys.modules['app'] = app_mod

    # app.tools — agent.py: from .tools import all_tool_funcs
    sys.modules['app.tools'] = _make_module('app.tools', {
        'all_tool_funcs': [],
    })

    # app.schema — agent.py: from .schema import get_database_schema
    sys.modules['app.schema'] = _make_module('app.schema', {
        'get_database_schema': lambda: '',
    })

    # app.config — agent.py: from .config import REDIS_URL
    sys.modules['app.config'] = _make_module('app.config', {
        'REDIS_URL': 'redis://localhost:6379/0',
    })

    # app.profile — agent.py: from .profile import profile_manager
    sys.modules['app.profile'] = _make_module('app.profile', {
        'profile_manager': _make_module('MockProfileManager', {
            'build_profile_prompt_section': lambda self, *a, **kw: '',
        }),
    })


# 执行 mock 注入
_setup_mocks()

# 现在可以安全导入 detect_intent
from app.agent import detect_intent


# ============================================================
# 3. 测试用例数据集
#    每条包含 input_text（用户输入）和 expected_intent（期望意图）
#    覆盖全部13种意图，每种至少5条，含边界/口语化/网络用语
# ============================================================
TEST_CASES = [
    # ==================== search（商品搜索） ====================
    {"input_text": "华为平板推荐一下", "expected_intent": "search"},
    {"input_text": "帮我看看华为手机", "expected_intent": "search"},
    {"input_text": "有没有苹果手机", "expected_intent": "search"},
    {"input_text": "查一下小米耳机", "expected_intent": "search"},
    {"input_text": "买什么手机好", "expected_intent": "search"},
    {"input_text": "找一款华为手表", "expected_intent": "search"},
    {"input_text": "推荐几款笔记本", "expected_intent": "search"},
    # 口语化/网络用语
    {"input_text": "推荐一下", "expected_intent": "search"},
    {"input_text": "看看有没有便宜的平板", "expected_intent": "search"},

    # ==================== budget（预算推荐） ====================
    {"input_text": "8000左右的苹果手机", "expected_intent": "budget"},
    {"input_text": "8000预算买什么手机", "expected_intent": "budget"},
    {"input_text": "5000以内买华为", "expected_intent": "budget"},
    {"input_text": "3000左右推荐手机", "expected_intent": "budget"},
    {"input_text": "预算2000买平板", "expected_intent": "budget"},
    {"input_text": "1000块钱的耳机", "expected_intent": "budget"},
    {"input_text": "学生用推荐", "expected_intent": "budget"},
    # 边界：口语化预算表达
    {"input_text": "1500左右有什么手机", "expected_intent": "budget"},
    {"input_text": "便宜点的手机", "expected_intent": "budget"},

    # ==================== price（价格查询） ====================
    {"input_text": "这个多少钱", "expected_intent": "price"},
    {"input_text": "华为手机价格", "expected_intent": "price"},
    {"input_text": "苹果平板报价", "expected_intent": "price"},
    {"input_text": "这款手机多少钱啊", "expected_intent": "price"},
    {"input_text": "这个多少元", "expected_intent": "price"},
    # 边界：含型号名的价格查询
    {"input_text": "Mate60价钱", "expected_intent": "price"},

    # ==================== review（评论查询） ====================
    {"input_text": "看看用户评论", "expected_intent": "review"},
    {"input_text": "这款手机的评价", "expected_intent": "review"},
    {"input_text": "这个商品的评论", "expected_intent": "review"},
    {"input_text": "用户怎么说这款手机", "expected_intent": "review"},
    {"input_text": "这款手机口碑", "expected_intent": "review"},
    {"input_text": "第二款评论", "expected_intent": "review"},
    # 边界：口语化评论查询（"怎么样"/"咋样"与sentiment_analysis冲突）
    {"input_text": "第二款评论怎么样", "expected_intent": "review"},
    {"input_text": "这款手机评价咋样", "expected_intent": "review"},

    # ==================== score（评分查询） ====================
    {"input_text": "这个平板评分多少", "expected_intent": "score"},
    {"input_text": "看看星级", "expected_intent": "score"},
    {"input_text": "这款手机几星", "expected_intent": "score"},
    {"input_text": "好评率多少", "expected_intent": "score"},
    {"input_text": "这款商品的评分", "expected_intent": "score"},
    {"input_text": "评分是多少", "expected_intent": "score"},
    # 边界：含"怎么样"的评分查询
    {"input_text": "好评率怎么样", "expected_intent": "score"},

    # ==================== sentiment_analysis（综合评价/情感分析） ====================
    {"input_text": "这个商品咋样", "expected_intent": "sentiment_analysis"},
    {"input_text": "第二款怎么样", "expected_intent": "sentiment_analysis"},
    {"input_text": "你觉得这款手机好不好", "expected_intent": "sentiment_analysis"},
    {"input_text": "综合评价一下", "expected_intent": "sentiment_analysis"},
    {"input_text": "分析一下这款手机", "expected_intent": "sentiment_analysis"},
    {"input_text": "优缺点有哪些", "expected_intent": "sentiment_analysis"},
    # 口语化
    {"input_text": "好不好用", "expected_intent": "sentiment_analysis"},
    {"input_text": "口碑怎么样", "expected_intent": "sentiment_analysis"},

    # ==================== positive（正面评价/好评） ====================
    {"input_text": "有没有好评", "expected_intent": "positive"},
    {"input_text": "这个手机的优点", "expected_intent": "positive"},
    {"input_text": "正面评价", "expected_intent": "positive"},
    {"input_text": "推荐理由是什么", "expected_intent": "positive"},
    {"input_text": "好的地方有哪些", "expected_intent": "positive"},
    # 边界：含"值得买"但非购买建议问句
    {"input_text": "值得买的手机", "expected_intent": "positive"},

    # ==================== negative（负面评价/差评） ====================
    {"input_text": "有什么缺点", "expected_intent": "negative"},
    {"input_text": "差评多吗", "expected_intent": "negative"},
    {"input_text": "不好的地方", "expected_intent": "negative"},
    {"input_text": "槽点有哪些", "expected_intent": "negative"},
    {"input_text": "避坑指南", "expected_intent": "negative"},
    {"input_text": "苹果平板的缺点", "expected_intent": "negative"},
    # 边界："问题"可能产生误判
    {"input_text": "这款手机问题多吗", "expected_intent": "negative"},

    # ==================== cart（购物车） ====================
    {"input_text": "我的购物车", "expected_intent": "cart"},
    {"input_text": "查看购物车", "expected_intent": "cart"},
    {"input_text": "购物车里有什么", "expected_intent": "cart"},
    {"input_text": "查购物车", "expected_intent": "cart"},
    {"input_text": "购物车", "expected_intent": "cart"},
    {"input_text": "看看购物车", "expected_intent": "cart"},

    # ==================== checkout（结算） ====================
    {"input_text": "帮我结算", "expected_intent": "checkout"},
    {"input_text": "下单吧", "expected_intent": "checkout"},
    {"input_text": "提交订单", "expected_intent": "checkout"},
    {"input_text": "去支付", "expected_intent": "checkout"},
    {"input_text": "我要结算", "expected_intent": "checkout"},
    {"input_text": "结算一下", "expected_intent": "checkout"},
    # 边界："支付"不在checkout关键词中（仅"去支付"匹配）
    {"input_text": "帮我支付", "expected_intent": "checkout"},

    # ==================== order（订单查询） ====================
    {"input_text": "查一下我的订单", "expected_intent": "order"},
    {"input_text": "我的订单", "expected_intent": "order"},
    {"input_text": "订单详情", "expected_intent": "order"},
    {"input_text": "取消订单", "expected_intent": "order"},
    {"input_text": "所有订单", "expected_intent": "order"},
    {"input_text": "查看订单", "expected_intent": "order"},
    {"input_text": "帮我查订单", "expected_intent": "order"},

    # ==================== comparison（对比分析） ====================
    {"input_text": "华为和苹果哪个好", "expected_intent": "comparison"},
    {"input_text": "对比一下这两款", "expected_intent": "comparison"},
    {"input_text": "比较华为和小米", "expected_intent": "comparison"},
    {"input_text": "这两款有什么区别", "expected_intent": "comparison"},
    {"input_text": "选哪个好", "expected_intent": "comparison"},
    {"input_text": "哪个值得买", "expected_intent": "comparison"},

    # ==================== purchase_recommendation（购买建议） ====================
    {"input_text": "这个值得买吗", "expected_intent": "purchase_recommendation"},
    {"input_text": "推荐买不", "expected_intent": "purchase_recommendation"},
    {"input_text": "建议买吗", "expected_intent": "purchase_recommendation"},
    {"input_text": "可以买吗", "expected_intent": "purchase_recommendation"},
    {"input_text": "值得入手吗", "expected_intent": "purchase_recommendation"},
    {"input_text": "推荐买吗", "expected_intent": "purchase_recommendation"},
    # 口语化
    {"input_text": "推荐购买不", "expected_intent": "purchase_recommendation"},
    {"input_text": "建议买不", "expected_intent": "purchase_recommendation"},

    # ==================== general（通用/闲聊） ====================
    {"input_text": "你好", "expected_intent": "general"},
    {"input_text": "谢谢", "expected_intent": "general"},
    {"input_text": "在吗", "expected_intent": "general"},
    {"input_text": "你是谁", "expected_intent": "general"},
    {"input_text": "早上好", "expected_intent": "general"},
    {"input_text": "再见", "expected_intent": "general"},
    {"input_text": "哈哈", "expected_intent": "general"},
]


# ============================================================
# 4. 核心测试逻辑
# ============================================================
def test_intent_accuracy():
    """
    意图识别准确率测试主函数。
    遍历所有测试用例，调用 detect_intent，统计正确/错误，
    计算总体准确率和每个意图的 Precision / Recall / F1，
    输出详细报告并保存到 JSON 文件。
    """
    # ---------- 遍历用例，收集结果 ----------
    results = []
    for case in TEST_CASES:
        input_text = case["input_text"]
        expected = case["expected_intent"]
        actual = detect_intent(input_text)
        is_correct = (actual == expected)
        results.append({
            "input_text": input_text,
            "expected": expected,
            "actual": actual,
            "correct": is_correct,
        })

    # ---------- 计算总体准确率 ----------
    total = len(results)
    correct_count = sum(1 for r in results if r["correct"])
    overall_accuracy = correct_count / total if total > 0 else 0.0

    # ---------- 收集所有意图类别 ----------
    all_intents = sorted(set(case["expected_intent"] for case in TEST_CASES)
                         | set(r["actual"] for r in results))

    # ---------- 计算每个意图的 TP / FP / FN / Precision / Recall / F1 ----------
    metrics = {}
    for intent in all_intents:
        tp = sum(1 for r in results if r["expected"] == intent and r["actual"] == intent)
        fp = sum(1 for r in results if r["expected"] != intent and r["actual"] == intent)
        fn = sum(1 for r in results if r["expected"] == intent and r["actual"] != intent)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
        metrics[intent] = {
            "TP": tp,
            "FP": fp,
            "FN": fn,
            "Precision": round(precision, 4),
            "Recall": round(recall, 4),
            "F1": round(f1, 4),
        }

    # ---------- 计算宏平均（Macro Average） ----------
    macro_precision = sum(m["Precision"] for m in metrics.values()) / len(metrics) if metrics else 0
    macro_recall = sum(m["Recall"] for m in metrics.values()) / len(metrics) if metrics else 0
    macro_f1 = sum(m["F1"] for m in metrics.values()) / len(metrics) if metrics else 0

    # ---------- 输出控制台报告 ----------
    _print_report(results, all_intents, metrics, total, correct_count,
                  overall_accuracy, macro_precision, macro_recall, macro_f1)

    # ---------- 保存结果到 JSON ----------
    _save_results(results, all_intents, metrics, total, correct_count,
                  overall_accuracy, macro_precision, macro_recall, macro_f1)

    # ---------- 断言：总体准确率不低于预期阈值（可根据实际调优） ----------
    # 当前阈值设为 0.70，可随规则优化后逐步提升
    assert overall_accuracy >= 0.70, (
        f"总体准确率 {overall_accuracy:.2%} 低于阈值 70%，请检查意图识别规则"
    )

    return overall_accuracy


def _print_report(results, all_intents, metrics, total, correct_count,
                  overall_accuracy, macro_precision, macro_recall, macro_f1):
    """输出格式化的测试报告到控制台"""

    # 分隔线
    sep = "=" * 90
    thin_sep = "-" * 90

    print(f"\n{sep}")
    print("                     意图识别准确率测试报告")
    print(f"{sep}")
    print(f"  测试时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  测试用例总数：{total}")
    print(f"  正确数量：{correct_count}    错误数量：{total - correct_count}")
    print(f"  总体准确率：{overall_accuracy:.2%}")
    print(f"  宏平均 Precision：{macro_precision:.4f}    Recall：{macro_recall:.4f}    F1：{macro_f1:.4f}")
    print(f"{thin_sep}")

    # 分类指标表格
    header = f"{'意图':<26} {'TP':>4} {'FP':>4} {'FN':>4} {'Precision':>10} {'Recall':>10} {'F1':>10}"
    print(header)
    print(thin_sep)
    for intent in all_intents:
        m = metrics[intent]
        row = (f"{intent:<26} {m['TP']:>4} {m['FP']:>4} {m['FN']:>4} "
               f"{m['Precision']:>10.4f} {m['Recall']:>10.4f} {m['F1']:>10.4f}")
        print(row)
    print(thin_sep)
    macro_row = (f"{'Macro Average':<26} {'':>4} {'':>4} {'':>4} "
                 f"{macro_precision:>10.4f} {macro_recall:>10.4f} {macro_f1:>10.4f}")
    print(macro_row)
    print(sep)

    # 错误用例详情
    error_cases = [r for r in results if not r["correct"]]
    if error_cases:
        print(f"\n  ❌ 错误用例详情（共 {len(error_cases)} 条）：\n")
        print(f"  {'输入文本':<28} {'期望意图':<24} {'实际意图':<24}")
        print(f"  {'-' * 76}")
        for r in error_cases:
            input_display = r["input_text"][:24] + "..." if len(r["input_text"]) > 24 else r["input_text"]
            print(f"  {input_display:<28} {r['expected']:<24} {r['actual']:<24}")
        print()

    print(sep + "\n")


def _save_results(results, all_intents, metrics, total, correct_count,
                  overall_accuracy, macro_precision, macro_recall, macro_f1):
    """将测试结果保存到 tests/results/intent_results.json"""

    # 确保输出目录存在
    results_dir = os.path.join(os.path.dirname(__file__), 'results')
    os.makedirs(results_dir, exist_ok=True)

    output_path = os.path.join(results_dir, 'intent_results.json')

    report = {
        "test_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "summary": {
            "total_cases": total,
            "correct_count": correct_count,
            "error_count": total - correct_count,
            "overall_accuracy": round(overall_accuracy, 4),
            "macro_precision": round(macro_precision, 4),
            "macro_recall": round(macro_recall, 4),
            "macro_f1": round(macro_f1, 4),
        },
        "per_intent_metrics": metrics,
        "error_cases": [
            {
                "input_text": r["input_text"],
                "expected": r["expected"],
                "actual": r["actual"],
            }
            for r in results if not r["correct"]
        ],
        "all_results": [
            {
                "input_text": r["input_text"],
                "expected": r["expected"],
                "actual": r["actual"],
                "correct": r["correct"],
            }
            for r in results
        ],
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"  📁 测试结果已保存到：{output_path}\n")


# ============================================================
# 5. 支持 pytest 和直接运行两种方式
# ============================================================
if __name__ == "__main__":
    accuracy = test_intent_accuracy()
    print(f"  ✅ 测试完成，总体准确率：{accuracy:.2%}\n")
