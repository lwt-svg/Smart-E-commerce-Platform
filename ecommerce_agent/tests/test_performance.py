"""
电商智能助手 性能基准测试框架

测试目标：http://localhost:8001/chat
测试内容：
  1. 单请求延迟测试（5类场景，每场景5次取平均）
  2. 并发测试（1/5/10/20并发级别，每级别20次请求）
  3. Tool执行耗时分析（直接调用Tool函数，每个3次取平均）
  4. 结果报告（控制台表格 + JSON文件）
"""

import sys
import os
import time
import json
import asyncio
import statistics
import functools
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable

# 添加项目根目录到 sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import aiohttp

# ==================== 常量配置 ====================

BASE_URL = "http://localhost:8001"
CHAT_URL = f"{BASE_URL}/chat"
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

# 单请求测试场景
SINGLE_REQUEST_SCENARIOS = [
    {"name": "简单搜索", "message": "华为手机"},
    {"name": "复杂搜索", "message": "8000左右的苹果手机"},
    {"name": "购物车查询", "message": "我的购物车"},
    {"name": "评论分析", "message": "这个商品咋样"},
    {"name": "闲聊", "message": "你好"},
]

# 每场景重复次数
SINGLE_REPEAT_COUNT = 5

# 并发测试级别
CONCURRENCY_LEVELS = [1, 5, 10, 20]

# 每个并发级别的总请求数
CONCURRENCY_TOTAL_REQUESTS = 20

# Tool测试重复次数
TOOL_REPEAT_COUNT = 3


# ==================== PerformanceProfiler ====================

class PerformanceProfiler:
    """
    性能分析器
    - 提供装饰器 @profile_tool 用于测量各Tool的执行耗时
    - 记录每次调用的耗时数据
    """

    def __init__(self):
        # 存储各函数的耗时记录 {函数名: [耗时1, 耗时2, ...]}
        self.records: Dict[str, List[float]] = {}

    def profile_tool(self, func: Callable) -> Callable:
        """装饰器：测量Tool函数的执行耗时"""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start
                func_name = func.__name__
                if func_name not in self.records:
                    self.records[func_name] = []
                self.records[func_name].append(elapsed)
            return result
        return wrapper

    def get_summary(self) -> Dict[str, Dict[str, float]]:
        """获取各函数的耗时统计摘要"""
        summary = {}
        for name, times in self.records.items():
            if not times:
                continue
            summary[name] = {
                "avg": round(statistics.mean(times), 4),
                "min": round(min(times), 4),
                "max": round(max(times), 4),
                "median": round(statistics.median(times), 4),
                "count": len(times),
            }
        return summary

    def clear(self):
        """清空记录"""
        self.records.clear()


# ==================== 工具函数 ====================

def percentile(data: List[float], pct: float) -> float:
    """计算百分位数"""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (pct / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return round(sorted_data[f], 4)
    d0 = sorted_data[f] * (c - k)
    d1 = sorted_data[c] * (k - f)
    return round(d0 + d1, 4)


def ensure_results_dir():
    """确保结果目录存在"""
    os.makedirs(RESULTS_DIR, exist_ok=True)


# ==================== 1. 单请求延迟测试 ====================

async def send_single_request(session: aiohttp.ClientSession, message: str) -> Dict[str, Any]:
    """
    发送单次请求并测量延迟
    返回: {"total_time": ..., "ttfb": ..., "status": ..., "error": ...}
    """
    payload = {
        "message": message,
        "use_rag": True,
    }
    start = time.perf_counter()
    ttfb = None
    try:
        async with session.post(CHAT_URL, json=payload) as resp:
            # TTFB：从请求发出到收到响应头的时间
            ttfb = time.perf_counter() - start
            body = await resp.text()
            total_time = time.perf_counter() - start
            return {
                "total_time": round(total_time, 4),
                "ttfb": round(ttfb, 4),
                "status": resp.status,
                "error": None,
            }
    except Exception as e:
        total_time = time.perf_counter() - start
        return {
            "total_time": round(total_time, 4),
            "ttfb": ttfb,
            "status": None,
            "error": str(e),
        }


async def run_single_request_tests() -> List[Dict[str, Any]]:
    """
    单请求延迟测试主函数
    对5类场景各发送5次请求，统计平均响应时间
    """
    results = []
    async with aiohttp.ClientSession() as session:
        for scenario in SINGLE_REQUEST_SCENARIOS:
            scenario_name = scenario["name"]
            message = scenario["message"]
            print(f"\n--- 单请求测试: [{scenario_name}] 消息=\"{message}\" ---")

            times = []
            ttfbs = []
            errors = 0

            for i in range(SINGLE_REPEAT_COUNT):
                result = await send_single_request(session, message)
                if result["error"]:
                    errors += 1
                    print(f"  第{i+1}次请求失败: {result['error']}")
                else:
                    times.append(result["total_time"])
                    ttfb_val = result["ttfb"]
                    if ttfb_val is not None:
                        ttfbs.append(ttfb_val)
                    print(f"  第{i+1}次: 总耗时={result['total_time']:.3f}s, TTFB={ttfb_val:.3f}s" if ttfb_val else f"  第{i+1}次: 总耗时={result['total_time']:.3f}s")

            # 统计
            scenario_result = {
                "scenario": scenario_name,
                "message": message,
                "repeat_count": SINGLE_REPEAT_COUNT,
                "error_count": errors,
                "avg_total_time": round(statistics.mean(times), 4) if times else 0,
                "min_total_time": round(min(times), 4) if times else 0,
                "max_total_time": round(max(times), 4) if times else 0,
                "median_total_time": round(statistics.median(times), 4) if times else 0,
                "avg_ttfb": round(statistics.mean(ttfbs), 4) if ttfbs else None,
                "all_times": [round(t, 4) for t in times],
            }
            results.append(scenario_result)

    return results


# ==================== 2. 并发测试 ====================

async def send_concurrent_batch(
    session: aiohttp.ClientSession,
    message: str,
    concurrency: int,
    total_requests: int,
) -> Dict[str, Any]:
    """
    以指定并发级别发送一批请求
    """
    semaphore = asyncio.Semaphore(concurrency)
    results = []

    async def bounded_request(idx: int):
        async with semaphore:
            payload = {"message": message, "use_rag": True}
            start = time.perf_counter()
            try:
                async with session.post(CHAT_URL, json=payload) as resp:
                    elapsed = time.perf_counter() - start
                    status = resp.status
                    return {"elapsed": round(elapsed, 4), "status": status, "error": None}
            except Exception as e:
                elapsed = time.perf_counter() - start
                return {"elapsed": round(elapsed, 4), "status": None, "error": str(e)}

    batch_start = time.perf_counter()
    tasks = [bounded_request(i) for i in range(total_requests)]
    results = await asyncio.gather(*tasks)
    batch_end = time.perf_counter()
    batch_duration = batch_end - batch_start

    # 统计
    successes = [r for r in results if r["error"] is None]
    failures = [r for r in results if r["error"] is not None]
    success_times = [r["elapsed"] for r in successes]

    return {
        "concurrency": concurrency,
        "total_requests": total_requests,
        "success_count": len(successes),
        "error_count": len(failures),
        "error_rate": round(len(failures) / total_requests * 100, 2) if total_requests > 0 else 0,
        "batch_duration": round(batch_duration, 4),
        "throughput": round(len(successes) / batch_duration, 2) if batch_duration > 0 else 0,
        "avg_response_time": round(statistics.mean(success_times), 4) if success_times else 0,
        "min_response_time": round(min(success_times), 4) if success_times else 0,
        "max_response_time": round(max(success_times), 4) if success_times else 0,
        "p50": percentile(success_times, 50) if success_times else 0,
        "p95": percentile(success_times, 95) if success_times else 0,
        "p99": percentile(success_times, 99) if success_times else 0,
    }


async def run_concurrency_tests() -> List[Dict[str, Any]]:
    """
    并发测试主函数
    测试并发级别 1, 5, 10, 20，每个级别发送20次请求
    使用"华为手机"作为测试消息
    """
    test_message = "华为手机"
    results = []

    async with aiohttp.ClientSession() as session:
        for level in CONCURRENCY_LEVELS:
            print(f"\n--- 并发测试: 并发级别={level}, 总请求数={CONCURRENCY_TOTAL_REQUESTS} ---")
            result = await send_concurrent_batch(
                session, test_message, level, CONCURRENCY_TOTAL_REQUESTS
            )
            results.append(result)
            print(f"  吞吐量: {result['throughput']} req/s")
            print(f"  平均响应时间: {result['avg_response_time']:.3f}s")
            print(f"  P50/P95/P99: {result['p50']:.3f}s / {result['p95']:.3f}s / {result['p99']:.3f}s")
            print(f"  错误率: {result['error_rate']}%")

    return results


# ==================== 3. Tool执行耗时分析 ====================

def run_tool_profiling() -> Dict[str, Any]:
    """
    直接调用各Tool函数，测量执行耗时
    每个Tool执行3次取平均
    """
    profiler = PerformanceProfiler()

    # 导入Tool函数（使用profiler装饰器包装）
    try:
        from app.tools.product_tools import (
            search_products_by_category,
            recommend_products_by_budget,
            get_product_comments,
        )
        from app.tools.order_cart_tools import (
            check_user_cart,
            check_user_orders,
        )
        from app.tools.review_analysis_tools import (
            analyze_product_sentiment,
        )
    except ImportError as e:
        print(f"[WARN] 导入Tool函数失败: {e}")
        print("[WARN] Tool耗时分析将跳过，请确保数据库连接正常")
        return {"tools": [], "error": str(e)}

    # 用 profiler 装饰各Tool函数
    profiled_search = profiler.profile_tool(search_products_by_category)
    profiled_recommend = profiler.profile_tool(recommend_products_by_budget)
    profiled_cart = profiler.profile_tool(check_user_cart)
    profiled_orders = profiler.profile_tool(check_user_orders)
    profiled_comments = profiler.profile_tool(get_product_comments)
    profiled_sentiment = profiler.profile_tool(analyze_product_sentiment)

    tool_tests = [
        {
            "name": "search_products_by_category",
            "func": profiled_search,
            "kwargs": {"brand": "华为", "category": "手机"},
        },
        {
            "name": "recommend_products_by_budget",
            "func": profiled_recommend,
            "kwargs": {"budget": 8000, "brand": "苹果"},
        },
        {
            "name": "check_user_cart",
            "func": profiled_cart,
            "kwargs": {"user_email": "123456@qq.com"},
        },
        {
            "name": "check_user_orders",
            "func": profiled_orders,
            "kwargs": {"user_email": "123456@qq.com"},
        },
        {
            "name": "get_product_comments",
            "func": profiled_comments,
            "kwargs": {"product_name": "华为手机"},
        },
        {
            "name": "analyze_product_sentiment",
            "func": profiled_sentiment,
            "kwargs": {"product_name": "华为手机"},
        },
    ]

    for tool_test in tool_tests:
        name = tool_test["name"]
        func = tool_test["func"]
        kwargs = tool_test["kwargs"]
        print(f"\n--- Tool测试: {name} ---")
        for i in range(TOOL_REPEAT_COUNT):
            try:
                result = func(**kwargs)
                # 截断过长的返回值用于显示
                result_preview = str(result)[:80] if result else "None"
                print(f"  第{i+1}次完成, 返回预览: {result_preview}...")
            except Exception as e:
                print(f"  第{i+1}次执行出错: {e}")

    # 获取统计摘要
    summary = profiler.get_summary()

    # 构建排名列表
    ranking = []
    for tool_name, stats in summary.items():
        ranking.append({
            "tool_name": tool_name,
            "avg_time": stats["avg"],
            "min_time": stats["min"],
            "max_time": stats["max"],
            "median_time": stats["median"],
            "count": stats["count"],
        })
    # 按平均耗时降序排列（最慢的排最前）
    ranking.sort(key=lambda x: x["avg_time"], reverse=True)

    return {"tools": ranking}


# ==================== 4. 结果报告 ====================

def print_separator(char: str = "-", width: int = 90):
    """打印分隔线"""
    print(char * width)


def print_table_header(columns: List[str], widths: List[int]):
    """打印表格头"""
    header = ""
    for col, w in zip(columns, widths):
        header += f"| {col:<{w-3}}"
    header += "|"
    print_separator()
    print(header)
    print_separator()


def print_table_row(values: List[str], widths: List[int]):
    """打印表格行"""
    row = ""
    for val, w in zip(values, widths):
        row += f"| {str(val):<{w-3}}"
    row += "|"
    print(row)


def print_single_request_report(data: List[Dict[str, Any]]):
    """打印单请求延迟统计表"""
    print("\n" + "=" * 90)
    print("  单请求延迟测试报告")
    print("=" * 90)

    widths = [14, 20, 14, 14, 14, 14, 14, 10]
    columns = ["场景", "测试消息", "平均耗时(s)", "最小耗时(s)", "最大耗时(s)", "中位数(s)", "平均TTFB(s)", "错误数"]
    print_table_header(columns, widths)

    for item in data:
        ttfb_str = f"{item['avg_ttfb']:.3f}" if item['avg_ttfb'] is not None else "N/A"
        print_table_row([
            item["scenario"],
            item["message"],
            f"{item['avg_total_time']:.3f}",
            f"{item['min_total_time']:.3f}",
            f"{item['max_total_time']:.3f}",
            f"{item['median_total_time']:.3f}",
            ttfb_str,
            str(item["error_count"]),
        ], widths)

    print_separator()


def print_concurrency_report(data: List[Dict[str, Any]]):
    """打印并发测试统计表"""
    print("\n" + "=" * 100)
    print("  并发测试报告")
    print("=" * 100)

    widths = [10, 10, 10, 10, 12, 16, 14, 12, 10, 10, 10]
    columns = ["并发数", "总请求数", "成功数", "错误率(%)", "吞吐量(req/s)", "平均响应(s)", "P50(s)", "P95(s)", "P99(s)", "最小(s)", "最大(s)"]
    print_table_header(columns, widths)

    for item in data:
        print_table_row([
            str(item["concurrency"]),
            str(item["total_requests"]),
            str(item["success_count"]),
            f"{item['error_rate']:.1f}",
            f"{item['throughput']:.2f}",
            f"{item['avg_response_time']:.3f}",
            f"{item['p50']:.3f}",
            f"{item['p95']:.3f}",
            f"{item['p99']:.3f}",
            f"{item['min_response_time']:.3f}",
            f"{item['max_response_time']:.3f}",
        ], widths)

    print_separator()


def print_tool_ranking_report(tool_data: Dict[str, Any], single_request_data: List[Dict[str, Any]]):
    """打印Tool耗时排名及LLM调用耗时估算"""
    tools = tool_data.get("tools", [])
    if not tools:
        print("\n[INFO] 无Tool耗时数据，跳过排名报告")
        return

    print("\n" + "=" * 90)
    print("  Tool执行耗时排名（从慢到快）")
    print("=" * 90)

    widths = [6, 36, 14, 14, 14, 14]
    columns = ["排名", "Tool名称", "平均耗时(s)", "最小耗时(s)", "最大耗时(s)", "中位数(s)"]
    print_table_header(columns, widths)

    for idx, tool in enumerate(tools, 1):
        print_table_row([
            str(idx),
            tool["tool_name"],
            f"{tool['avg_time']:.4f}",
            f"{tool['min_time']:.4f}",
            f"{tool['max_time']:.4f}",
            f"{tool['median_time']:.4f}",
        ], widths)

    print_separator()

    # LLM调用耗时估算
    print("\n" + "=" * 90)
    print("  LLM调用耗时估算（总响应时间 - Tool执行时间）")
    print("=" * 90)

    # 获取各场景的平均Tool耗时（取最慢的一个Tool作为该场景的Tool耗时估算）
    tool_avg_map = {t["tool_name"]: t["avg_time"] for t in tools}

    # 场景与主要Tool的映射
    scenario_tool_map = {
        "简单搜索": "search_products_by_category",
        "复杂搜索": "recommend_products_by_budget",
        "购物车查询": "check_user_cart",
        "评论分析": "analyze_product_sentiment",
        "闲聊": None,  # 闲聊不调用Tool
    }

    widths2 = [14, 16, 14, 14, 14]
    columns2 = ["场景", "主要Tool", "总响应(s)", "Tool耗时(s)", "LLM耗时估算(s)"]
    print_table_header(columns2, widths2)

    for item in single_request_data:
        scenario = item["scenario"]
        main_tool = scenario_tool_map.get(scenario)
        total_time = item["avg_total_time"]
        tool_time = tool_avg_map.get(main_tool, 0) if main_tool else 0
        llm_time = max(0, total_time - tool_time)
        print_table_row([
            scenario,
            main_tool or "无",
            f"{total_time:.3f}",
            f"{tool_time:.4f}",
            f"{llm_time:.3f}",
        ], widths2)

    print_separator()


def save_results_to_json(
    single_data: List[Dict[str, Any]],
    concurrency_data: List[Dict[str, Any]],
    tool_data: Dict[str, Any],
):
    """保存结果到JSON文件"""
    ensure_results_dir()
    output = {
        "test_time": datetime.now().isoformat(),
        "test_target": CHAT_URL,
        "single_request_tests": single_data,
        "concurrency_tests": concurrency_data,
        "tool_profiling": tool_data,
    }
    output_path = os.path.join(RESULTS_DIR, "perf_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n[结果] 性能报告已保存到: {output_path}")


# ==================== 主入口 ====================

async def main():
    """性能基准测试主入口"""
    print("=" * 90)
    print("  电商智能助手 性能基准测试")
    print(f"  测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  测试目标: {CHAT_URL}")
    print("=" * 90)

    # 1. 单请求延迟测试
    print("\n\n" + "#" * 90)
    print("# 第一部分：单请求延迟测试")
    print("#" * 90)
    single_results = await run_single_request_tests()
    print_single_request_report(single_results)

    # 2. 并发测试
    print("\n\n" + "#" * 90)
    print("# 第二部分：并发测试")
    print("#" * 90)
    concurrency_results = await run_concurrency_tests()
    print_concurrency_report(concurrency_results)

    # 3. Tool执行耗时分析
    print("\n\n" + "#" * 90)
    print("# 第三部分：Tool执行耗时分析")
    print("#" * 90)
    tool_results = run_tool_profiling()
    print_tool_ranking_report(tool_results, single_results)

    # 4. 保存结果
    save_results_to_json(single_results, concurrency_results, tool_results)

    print("\n" + "=" * 90)
    print("  性能基准测试完成！")
    print("=" * 90)


if __name__ == "__main__":
    asyncio.run(main())
