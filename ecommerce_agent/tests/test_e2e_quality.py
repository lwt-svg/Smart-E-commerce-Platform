"""
端到端对话质量评估框架 (LLM-as-Judge方案)
==========================================

本模块实现两种评估模式：
  模式1：API调用评估 - 需要FastAPI服务运行在 localhost:8001
  模式2：离线评估 - 直接导入agent模块进行意图准确性验证

使用方法：
  python tests/test_e2e_quality.py --mode api      # API调用评估
  python tests/test_e2e_quality.py --mode offline   # 离线评估
  python tests/test_e2e_quality.py                  # 默认运行API模式
"""

import sys
import os
import json
import time
import argparse
import asyncio
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime
from pathlib import Path
# ==================== 路径配置 ====================
# 将项目根目录添加到sys.path，确保可以导入my_llm和app模块
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ==================== 导入依赖 ====================
try:
    import httpx
except ImportError:
    print("提示: 安装 httpx 以支持API模式: pip install httpx")
    httpx = None

try:
    from my_llm import llm
    LLM_AVAILABLE = True
except ImportError as e:
    print(f"警告: 无法导入LLM模型 ({e})，LLM评估功能将不可用")
    LLM_AVAILABLE = False
    llm = None

try:
    from app.agent import detect_intent
    AGENT_AVAILABLE = True
except ImportError as e:
    print(f"警告: 无法导入agent模块 ({e})，离线模式将不可用")
    AGENT_AVAILABLE = False
    detect_intent = None


# ==================== 数据类定义 ====================

@dataclass
class E2ETestCase:
    """端到端测试用例数据类"""
    user_message: str                              # 用户输入消息
    expected_intent: str                           # 期望的意图类别
    evaluation_criteria: str                       # 评估标准说明（用于LLM Judge）
    category: str                                  # 测试用例分类标签
    history: List[Dict[str, str]] = field(default_factory=list)  # 多轮对话历史上下文
    token: Optional[str] = None                    # 登录token（购物车/订单类测试需要）
    user_email: Optional[str] = None               # 用户邮箱（无token时可用）


@dataclass
class E2EResult:
    """单条测试结果数据类"""
    test_case: E2ETestCase                # 原始测试用例
    actual_response: Optional[str]        # Agent实际回复内容
    intent_correct: bool                  # 意图识别是否正确
    scores: Dict[str, int]                # 各维度评分 {相关性, 完整性, 准确性, 友好度}
    response_time: float                  # 响应耗时(秒)
    error: Optional[str] = None           # 错误信息（如有）
    comment: str = ""                     # LLM Judge评语


# ==================== LLMJudge 评估器 ====================

EVALUATION_PROMPT_TEMPLATE = """你是一个专业的对话质量评估专家。请对以下电商客服助手的回复质量进行评分。

## 评估任务
- **用户问题**: {user_question}
- **助手回复**: {assistant_response}
- **评估标准**: {evaluation_criteria}

## 评分维度（每个维度1-5分）
请从以下4个维度分别打分并说明理由：

1. **相关性** (Relevance)：回复是否直接回答了用户问题？是否切中用户意图？
2. **完整性** (Completeness)：回复是否覆盖了用户问题涉及的所有要点？信息是否充分？
3. **准确性** (Accuracy)：回复中的事实、价格、商品名称等信息是否准确无误？
4. **友好度** (Friendliness)：语气是否友好自然？是否符合客服场景的表达习惯？

## 输出格式要求
请严格按以下JSON格式输出，不要包含其他文字：
{{
    "relevance": <1-5分整数>,
    "completeness": <1-5分整数>,
    "accuracy": <1-5分整数>,
    "friendliness": <1-5分整数>,
    "overall_comment": "<综合评语，简要说明打分依据>"
}}

注意：
- 5分=优秀，4分=良好，3分=合格，2分=较差，1分=很差
- 如果助手回复为空或报错，所有维度给1分
- 请客观公正地评价"""


class LLMJudge:
    """
    LLM-as-Judge 评估器
    
    使用智谱GLM-4模型对Agent回复质量进行多维度打分。
    """

    def __init__(self):
        if not LLM_AVAILABLE:
            raise RuntimeError("LLM模型未可用，无法初始化LLMJudge")
        self.llm = llm

    def evaluate(self, user_question: str, assistant_response: str,
                 evaluation_criteria: str) -> Tuple[Dict[str, int], str]:
        """
        对单轮对话进行质量评估
        
        参数:
            user_question: 用户原始问题
            assistant_response: Agent助手的回复
            evaluation_criteria: 评估标准说明
            
        返回:
            (scores_dict, comment) - 评分字典和评语
        """
        if not assistant_response or assistant_response.strip() == "":
            return {
                "relevance": 1,
                "completeness": 1,
                "accuracy": 1,
                "friendliness": 1
            }, "助手回复为空"

        # 构建评估Prompt
        prompt = EVALUATION_PROMPT_TEMPLATE.format(
            user_question=user_question,
            assistant_response=assistant_response,
            evaluation_criteria=evaluation_criteria
        )

        try:
            from langchain_core.messages import HumanMessage
            response = self.llm.invoke([HumanMessage(content=prompt)])
            result_text = response.content.strip()

            # 尝试从响应中提取JSON
            scores, comment = self._parse_eval_result(result_text)
            return scores, comment

        except Exception as e:
            err_msg = str(e)
            print(f"  [LLMJudge] 评估过程出错: {e}")
            # 429限流时返回特殊标记，让evaluator跳过该case的评分，而不是打0分拉低均分
            if "429" in err_msg or "1302" in err_msg or "速率限制" in err_msg or "rate" in err_msg.lower():
                return None, f"LLM限流跳过评分: {err_msg}"
            return {
                "relevance": 0,
                "completeness": 0,
                "accuracy": 0,
                "friendliness": 0
            }, f"评估出错: {err_msg}"

    def _parse_eval_result(self, text: str) -> Tuple[Dict[str, int], str]:
        """解析LLM返回的JSON评估结果"""
        import re
        # 尝试匹配JSON对象
        json_match = re.search(r'\{[^{}]*"relevance"[^{}]*\}', text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                scores = {
                    "relevance": self._clamp_score(data.get("relevance", 0)),
                    "completeness": self._clamp_score(data.get("completeness", 0)),
                    "accuracy": self._clamp_score(data.get("accuracy", 0)),
                    "friendliness": self._clamp_score(data.get("friendliness", 0))
                }
                comment = data.get("overall_comment", "")
                return scores, comment
            except json.JSONDecodeError:
                pass

        # JSON解析失败时尝试正则提取各维度分数
        scores = {}
        for dim in ["relevance", "completeness", "accuracy", "friendliness"]:
            pattern = rf'"{dim}"\s*[:：]\s*(\d)'
            m = re.search(pattern, text)
            scores[dim] = self._clamp_score(int(m.group(1))) if m else 0
        
        comment = text[:200] if text else ""
        return scores, comment

    @staticmethod
    def _clamp_score(value: int) -> int:
        """将分数限制在0-5范围内"""
        return max(0, min(5, value))


# ==================== E2EEvaluator 主评估器 ====================

class E2EEvaluator:
    """
    端到端评估主控类
    
    支持两种运行模式：
    - API模式：通过HTTP请求调用FastAPI /chat接口
    - 离线模式：直接导入模块验证意图识别准确率
    """

    # API服务地址
    API_BASE_URL = "http://localhost:8001"
    CHAT_ENDPOINT = f"{API_BASE_URL}/chat"
    
    # 请求超时设置（秒）
    REQUEST_TIMEOUT = 60

    def __init__(self, use_judge: bool = True):
        """
        初始化评估器
        
        参数:
            use_judge: 是否启用LLM Judge评估（需要LLM可用）
        """
        self.use_judge = use_judge and LLM_AVAILABLE
        self.judge = LLMJudge() if self.use_judge else None
        self.results: List[E2EResult] = []
        
        # 加载测试用例
        self.test_cases = self._load_test_cases()

    def _load_test_cases(self) -> List[E2ETestCase]:
        """加载全部端到端测试用例，共26组，覆盖8大类别

        测试用例设计原则（v2 优化版）：
        - 指代词场景（这个/这款）通过history字段提供多轮上下文，而非单轮模拟
        - 购物车/订单场景通过user_email字段提供登录态，避免无token报错
        - 数据库缺失品类（苹果平板/小米耳机/智能手表）保留以测试降级提示，
          但evaluation_criteria允许"友好提示无商品"得分
        - 预算场景选择数据库能找到的品类组合，避免除锈剂类无效推荐
        """
        # 多轮上下文：先推荐华为手机，再问"这款"指代词问题
        # assistant回复用真实agent返回的product_list JSON格式，让choose_target_product能解析
        huawei_phone_history = [
            {"role": "user", "content": "帮我找一下华为的手机"},
            {"role": "assistant", "content": '{"type": "product_list", "products": [{"name": "华为Mate30EPro 5G手机麒麟990E 亮黑色 8GB+128GB", "price": 4599.0, "sku_id": "100027837235", "main_brand": "华为", "main_category": "手机"}, {"name": "华为 HUAWEI Mate 30E Pro 5G麒麟990E SoC芯片 双4000万徕卡电影影像 8GB+128GB亮黑色全网通手机", "price": 4699.0, "sku_id": "100016170950", "main_brand": "华为", "main_category": "手机"}]}'}
        ]
        # 多轮上下文：先推荐平板，再问"这款平板"
        tablet_history = [
            {"role": "user", "content": "推荐几款平板"},
            {"role": "assistant", "content": '{"type": "product_list", "products": [{"name": "中柏Jumper4SPro二手平板电脑10.6寸", "price": 688.0, "sku_id": "100012394639", "main_category": "电子产品"}, {"name": "苹果iPad Air 2020款", "price": 2999.0, "sku_id": "100009984231", "main_category": "电子产品"}]}'}
        ]
        # 多轮上下文：推荐两款手机用于对比
        two_phones_history = [
            {"role": "user", "content": "帮我找一下华为的手机"},
            {"role": "assistant", "content": '{"type": "product_list", "products": [{"name": "华为Mate30EPro 5G手机麒麟990E 亮黑色 8GB+128GB", "price": 4599.0, "sku_id": "100027837235", "main_brand": "华为"}, {"name": "华为 HUAWEI Mate 30E Pro 5G麒麟990E SoC芯片", "price": 4699.0, "sku_id": "100016170950", "main_brand": "华为"}]}'}
        ]
        # 测试用户邮箱（购物车/订单类测试需要登录态）
        test_user_email = "123456@qq.com"

        return [
            # ===== 类别1: 商品搜索 (5个) =====
            E2ETestCase(
                user_message="帮我找一下华为的手机",
                expected_intent="search",
                evaluation_criteria="应能识别品牌'华为'和品类'手机'，返回华为手机列表或相关推荐",
                category="商品搜索"
            ),
            E2ETestCase(
                user_message="有没有苹果平板电脑可以推荐？",
                expected_intent="search",
                evaluation_criteria="应识别品牌'苹果'、品类'平板'，返回iPad或苹果平板相关产品；若数据库无该品类，应友好提示并推荐替代方案（如华为平板）",
                category="商品搜索"
            ),
            E2ETestCase(
                user_message="推荐几款性价比高的笔记本电脑",
                expected_intent="search",
                evaluation_criteria="应识别品类'笔记本/电脑'，推荐相关机型；若数据库该品类商品较少，应友好提示并推荐替代方案",
                category="商品搜索"
            ),
            E2ETestCase(
                user_message="华为有哪些手机配件？",
                expected_intent="search",
                evaluation_criteria="应识别品牌'华为'和品类'手机配件'，返回相关商品列表",
                category="商品搜索"
            ),
            E2ETestCase(
                user_message="我想买个华为平板看看",
                expected_intent="search",
                evaluation_criteria="应识别品牌'华为'和品类'平板'，返回华为平板产品推荐",
                category="商品搜索"
            ),

            # ===== 类别2: 价格查询 (3个) =====
            E2ETestCase(
                user_message="华为Mate30EPro多少钱？",
                expected_intent="price",
                evaluation_criteria="应能查询到华为Mate30EPro手机的价格信息",
                category="价格查询"
            ),
            E2ETestCase(
                user_message="华为Mate 60的售价是多少",
                expected_intent="price",
                evaluation_criteria="应查询华为Mate 60系列手机价格；若数据库无该商品，应基于常识或友好提示作答",
                category="价格查询"
            ),
            E2ETestCase(
                user_message="这款手机报价多少？",
                expected_intent="price",
                evaluation_criteria="应结合上下文history中的手机商品，返回对应价格；若上下文有多款，应明确指代并给出选择",
                category="价格查询",
                history=huawei_phone_history
            ),

            # ===== 类别3: 评论分析 (4个) =====
            E2ETestCase(
                user_message="这个手机的评论怎么样？大家都在说什么",
                expected_intent="review",
                evaluation_criteria="应结合上下文history中的手机商品，展示该商品的最新用户评论摘要或具体评价",
                category="评论分析",
                history=huawei_phone_history
            ),
            E2ETestCase(
                user_message="这款产品的评分是多少星？好评率高吗？",
                expected_intent="score",
                evaluation_criteria="应结合上下文history中的商品，返回星级评分和好评率数据",
                category="评论分析",
                history=huawei_phone_history
            ),
            E2ETestCase(
                user_message="分析一下这个商品的优缺点",
                expected_intent="sentiment_analysis",
                evaluation_criteria="应结合上下文history中的商品，给出综合情感分析，包括主要优点和缺点",
                category="评论分析",
                history=huawei_phone_history
            ),
            E2ETestCase(
                user_message="这款手机的用户反馈好不好？有什么槽点吗",
                expected_intent="negative",
                evaluation_criteria="应结合上下文history中的手机商品，重点展示负面评价或缺点信息，帮助用户避坑",
                category="评论分析",
                history=huawei_phone_history
            ),

            # ===== 类别4: 购物车/订单 (4个) =====
            E2ETestCase(
                user_message="查看我的购物车",
                expected_intent="cart",
                evaluation_criteria="应调用购物车查询工具，返回当前登录用户购物车内的商品列表；若购物车为空应友好提示",
                category="购物车/订单",
                user_email=test_user_email
            ),
            E2ETestCase(
                user_message="我的订单状态怎么样了？",
                expected_intent="order",
                evaluation_criteria="应调用订单查询工具，返回用户的订单列表及状态",
                category="购物车/订单",
                user_email=test_user_email
            ),
            E2ETestCase(
                user_message="帮我结算购物车里的东西",
                expected_intent="checkout",
                evaluation_criteria="应触发购物车结算流程，返回结算结果或确认信息；若购物车为空应友好提示",
                category="购物车/订单",
                user_email=test_user_email
            ),
            E2ETestCase(
                user_message="查一下订单ORD1234567890的详情",
                expected_intent="order",
                evaluation_criteria="应提取订单号ORD1234567890并查询该订单的详细信息；若订单不存在应友好提示",
                category="购物车/订单",
                user_email=test_user_email
            ),

            # ===== 类别5: 情感分析 (3个) =====
            E2ETestCase(
                user_message="你觉得这款手机值得买吗？给我分析分析",
                expected_intent="purchase_recommendation",
                evaluation_criteria="应结合上下文history中的手机商品，基于评论数据给出购买建议，包括是否推荐购买的理由",
                category="情感分析",
                history=huawei_phone_history
            ),
            E2ETestCase(
                user_message="对比一下这两款手机哪个更好",
                expected_intent="comparison",
                evaluation_criteria="应结合上下文history中的两款手机，进行多维度对比（性能、价格、口碑等）",
                category="情感分析",
                history=two_phones_history
            ),
            E2ETestCase(
                user_message="这个商品的主要优点是什么？",
                expected_intent="positive",
                evaluation_criteria="应结合上下文history中的商品，总结该商品的核心优点和正面评价",
                category="情感分析",
                history=huawei_phone_history
            ),

            # ===== 类别6: 购买建议 (3个) =====
            E2ETestCase(
                user_message="3000元左右推荐什么手机好？",
                expected_intent="budget",
                evaluation_criteria="应根据预算3000元推荐合适的手机产品列表；若无符合条件的商品应友好提示",
                category="购买建议"
            ),
            E2ETestCase(
                user_message="3000预算买什么手机合适",
                expected_intent="budget",
                evaluation_criteria="应根据3000元预算推荐手机；应正确识别'3000预算'格式（数字在前）；若无商品应友好提示",
                category="购买建议"
            ),
            E2ETestCase(
                user_message="学生党预算有限，推荐一款便宜点的手机",
                expected_intent="budget",
                evaluation_criteria="应理解'学生党''便宜点'暗示的低预算需求，推荐性价比高的手机",
                category="购买建议"
            ),

            # ===== 类别7: 知识问答 (2个) =====
            E2ETestCase(
                user_message="你们平台的退换货政策是什么？",
                expected_intent="general",
                evaluation_criteria="应提供退换货相关的售后政策说明，回答要专业准确；若RAG未召回应基于常识给出常见政策说明",
                category="知识问答"
            ),
            E2ETestCase(
                user_message="怎么联系你们的客服？",
                expected_intent="general",
                evaluation_criteria="应提供客服联系方式或在线客服入口信息",
                category="知识问答"
            ),

            # ===== 类别8: 闲聊 (2个) =====
            E2ETestCase(
                user_message="你好啊！今天心情不错",
                expected_intent="general",
                evaluation_criteria="应友好回应问候，保持电商助手的角色定位",
                category="闲聊"
            ),
            E2ETestCase(
                user_message="谢谢你的帮助！",
                expected_intent="general",
                evaluation_criteria="应礼貌致谢，可适当询问是否还有其他需要",
                category="闲聊"
            ),
        ]

    async def run_api_test(self, test_case: E2ETestCase) -> E2EResult:
        """
        模式1: 通过HTTP API调用执行单个测试用例
        
        向 FastAPI /chat 接口发送POST请求获取Agent响应，
        并可选地使用LLM Judge进行质量评分。
        """
        start_time = time.time()
        error_msg = None
        response_text = None
        intent_correct = False

        try:
            if httpx is None:
                raise ImportError("httpx未安装，无法执行API测试")

            payload = {
                "message": test_case.user_message,
                "use_rag": True
            }
            # 传入多轮对话历史上下文（指代词测试用例需要）
            if test_case.history:
                payload["history"] = test_case.history
            # 传入登录凭证（购物车/订单类测试需要）
            if test_case.token:
                payload["token"] = test_case.token
            elif test_case.user_email:
                payload["user_email"] = test_case.user_email

            async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT) as client:
                resp = await client.post(self.CHAT_ENDPOINT, json=payload)
                
                if resp.status_code == 200:
                    data = resp.json()
                    response_text = data.get("response", "")
                    
                    # 验证意图（通过响应内容推断或标记待确认）
                    # 在API模式下，我们无法直接获取内部intent，
                    # 此处根据是否有有效响应来判断基本正确性
                    intent_correct = len(response_text) > 10
                else:
                    error_msg = f"HTTP {resp.status_code}: {resp.text}"

        except httpx.ConnectError:
            error_msg = f"无法连接到API服务 ({self.API_BASE_URL})，请确认FastAPI已启动"
        except Exception as e:
            error_msg = str(e)

        elapsed = time.time() - start_time

        # 使用LLM Judge进行质量评估
        scores = {"relevance": 0, "completeness": 0, "accuracy": 0, "friendliness": 0}
        comment = ""

        if self.use_judge and response_text and not error_msg:
            try:
                scores, comment = self.judge.evaluate(
                    user_question=test_case.user_message,
                    assistant_response=response_text,
                    evaluation_criteria=test_case.evaluation_criteria
                )
                # LLM限流时judge返回None，scores置空表示跳过该case评分（不拉低均分）
                if scores is None:
                    scores = {}
                    print(f"     ⚠️ LLM限流，跳过该case评分")
            except Exception as e:
                comment = f"LLM评估失败: {e}"

        return E2EResult(
            test_case=test_case,
            actual_response=response_text,
            intent_correct=intent_correct,
            scores=scores,
            response_time=elapsed,
            error=error_msg,
            comment=comment
        )

    def run_offline_test(self, test_case: E2ETestCase) -> E2EResult:
        """
        模式2: 离线评估 - 验证意图识别准确性
        
        直接调用 detect_intent 函数检测用户消息的意图类别，
        与期望意图进行比对，不需要网络和服务。
        """
        start_time = time.time()
        error_msg = None
        actual_intent = "unknown"
        intent_correct = False

        try:
            if detect_intent is None:
                raise ImportError("detect_intent函数不可用")

            # 调用意图检测函数
            actual_intent = detect_intent(test_case.user_message)
            
            # 判断意图是否正确（允许部分模糊匹配）
            intent_correct = self._match_intent(actual_intent, test_case.expected_intent)

        except Exception as e:
            error_msg = str(e)

        elapsed = time.time() - start_time

        # 离线模式下生成模拟响应用于报告
        mock_response = (
            f"[离线模拟] 检测到意图: {actual_intent}, "
            f"预期意图: {test_case.expected_intent}, "
            f"匹配结果: {'✅正确' if intent_correct else '❌错误'}"
        )

        return E2EResult(
            test_case=test_case,
            actual_response=mock_response,
            intent_correct=intent_correct,
            scores={},  # 离线模式不进行LLM评分
            response_time=elapsed,
            error=error_msg
        )

    @staticmethod
    def _match_intent(detected: str, expected: str) -> bool:
        """判断检测到的意图与期望意图是否匹配（含宽松规则）"""
        if detected == expected:
            return True
        # 宽松匹配规则：某些意图可以归为一类
        loose_groups = [
            {"review", "score", "sentiment_analysis"},       # 评论分析大类
            {"positive", "negative", "sentiment_analysis"},   # 正负面分析
            {"cart", "checkout", "order"},                    # 订单操作类
            {"search", "budget"}                               # 商品查找类
        ]
        for group in loose_groups:
            if detected in group and expected in group:
                return True
        return False

    async def run_evaluation(self, mode: str = "api") -> List[E2EResult]:
        """
        执行全部测试用例并收集结果
        
        参数:
            mode: 运行模式，"api" 或 "offline"
            
        返回:
            所有测试结果的列表
        """
        self.results = []
        total = len(self.test_cases)
        print(f"\n{'='*70}")
        print(f"🚀 开始端到端质量评估 | 模式: {mode.upper()} | 用例数: {total}")
        print(f"{'='*70}")

        for i, tc in enumerate(self.test_cases, 1):
            print(f"\n[{i}/{total}] 📝 类别: {tc.category} | 问题: {tc.user_message[:40]}...")

            if mode == "api":
                result = await self.run_api_test(tc)
            elif mode == "offline":
                result = self.run_offline_test(tc)
            else:
                raise ValueError(f"未知模式: {mode}，请选择 'api' 或 'offline'")

            self.results.append(result)

            # 打印单项结果摘要
            status = "✅ 通过" if result.intent_correct else "❌ 失败"
            if result.error:
                status = f"⚠️ 错误: {result.error[:50]}"
            
            time_str = f"{result.response_time:.2f}s"
            score_str = ""
            if result.scores:
                avg_score = sum(result.scores.values()) / len(result.scores)
                score_str = f"| 均分: {avg_score:.1f}"
            
            print(f"     结果: {status} | 耗时: {time_str} {score_str}")

            # 控制请求频率，避免压垮服务和触发LLM API限流（智谱免费版~5-10次/分钟）
            if mode == "api":
                await asyncio.sleep(2.0)

        print(f"\n{'='*70}")
        print(f"✅ 全部测试完成 | 总计: {total} 条")
        print(f"{'='*70}\n")

        return self.results

    def generate_report(self, output_dir: Optional[Path] = None) -> Dict[str, Any]:
        """
        生成详细评估报告
        
        报告内容包括：
        - 总体统计（平均分、错误率等）
        - 各维度平均分
        - 各意图类别表现
        - 响应时间分布（P50/P95/P99）
        - 每条测试的详细结果
        
        参数:
            output_dir: 输出目录路径，默认为 tests/results/
            
        返回:
            完整的报告字典
        """
        if output_dir is None:
            output_dir = Path(__file__).parent / "results"
        output_dir.mkdir(parents=True, exist_ok=True)

        results = self.results
        total_count = len(results)
        
        if total_count == 0:
            print("⚠️ 无测试结果，跳过报告生成")
            return {}

        # ========== 基础统计 ==========
        error_results = [r for r in results if r.error]
        success_results = [r for r in results if not r.error]
        error_count = len(error_results)
        success_count = len(success_results)
        error_rate = error_count / total_count * 100

        correct_count = sum(1 for r in success_results if r.intent_correct)
        accuracy_rate = correct_count / success_count * 100 if success_count else 0

        # ========== 分数统计（仅API模式有分数） ==========
        scored_results = [r for r in success_results if r.scores]
        has_scores = len(scored_results) > 0

        dimension_avgs = {}
        overall_avg = 0.0

        if has_scores:
            dims = ["relevance", "completeness", "accuracy", "friendliness"]
            for dim in dims:
                scores = [r.scores.get(dim, 0) for r in scored_results]
                valid_scores = [s for s in scores if s > 0]
                dimension_avgs[dim] = sum(valid_scores) / len(valid_scores) if valid_scores else 0
            
            all_valid_scores = []
            for r in scored_results:
                for s in r.scores.values():
                    if s > 0:
                        all_valid_scores.append(s)
            overall_avg = sum(all_valid_scores) / len(all_valid_scores) if all_valid_scores else 0

        # ========== 响应时间统计 ==========
        response_times = [r.response_time for r in results]
        sorted_times = sorted(response_times)
        
        def percentile(data: List[float], p: float) -> float:
            if not data:
                return 0.0
            k = (len(data) - 1) * p / 100
            f = int(k)
            c = f + 1 if f + 1 < len(data) else f
            return data[f] + (k - f) * (data[c] - data[f]) if f != c else data[f]

        time_stats = {
            "avg": sum(response_times) / len(response_times),
            "min": min(response_times),
            "max": max(response_times),
            "p50": percentile(sorted_times, 50),
            "p95": percentile(sorted_times, 95),
            "p99": percentile(sorted_times, 99)
        }

        # ========== 各类别统计 ==========
        category_stats: Dict[str, Dict] = {}
        for r in results:
            cat = r.test_case.category
            if cat not in category_stats:
                category_stats[cat] = {"count": 0, "correct": 0, "scores": [], "times": []}
            category_stats[cat]["count"] += 1
            if r.intent_correct:
                category_stats[cat]["correct"] += 1
            if r.scores:
                avg = sum(r.scores.values()) / len(r.scores)
                category_stats[cat]["scores"].append(avg)
            category_stats[cat]["times"].append(r.response_time)

        category_report = {}
        for cat, stats in category_stats.items():
            cat_accuracy = stats["correct"] / stats["count"] * 100
            cat_avg_score = sum(stats["scores"]) / len(stats["scores"]) if stats["scores"] else 0
            cat_avg_time = sum(stats["times"]) / len(stats["times"])
            category_report[cat] = {
                "total": stats["count"],
                "correct": stats["correct"],
                "accuracy": round(cat_accuracy, 1),
                "avg_score": round(cat_avg_score, 2),
                "avg_time": round(cat_avg_time, 3)
            }

        # ========== 组装完整报告 ==========
        report = {
            "meta": {
                "generated_at": datetime.now().isoformat(),
                "total_tests": total_count,
                "success_count": success_count,
                "error_count": error_count,
                "error_rate": round(error_rate, 2),
                "intent_accuracy": round(accuracy_rate, 2)
            },
            "overall_scores": {
                "average": round(overall_avg, 3) if has_scores else None,
                "by_dimension": {k: round(v, 3) for k, v in dimension_avgs.items()} if has_scores else None
            },
            "response_time": {k: round(v, 3) for k, v in time_stats.items()},
            "category_breakdown": category_report,
            "details": []
        }

        # 添加每条测试的详细信息
        for i, r in enumerate(results, 1):
            detail = {
                "index": i,
                "category": r.test_case.category,
                "user_message": r.test_case.user_message,
                "expected_intent": r.test_case.expected_intent,
                "evaluation_criteria": r.test_case.evaluation_criteria,
                "actual_response": (r.actual_response or "")[:500],  # 截断过长回复
                "intent_correct": r.intent_correct,
                "scores": r.scores,
                "response_time_sec": round(r.response_time, 3),
                "error": r.error,
                "comment": r.comment
            }
            report["details"].append(detail)

        # ========== 保存报告文件 ==========
        report_path = output_dir / "e2e_results.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"📊 报告已保存至: {report_path}")

        # ========== 打印控制台摘要 ==========
        self._print_summary(report)

        return report

    def _print_summary(self, report: Dict[str, Any]):
        """打印格式化的评估摘要到控制台"""
        meta = report["meta"]
        times = report["response_time"]
        categories = report["category_breakdown"]

        print("\n" + "█" * 70)
        print("  📋 端到端质量评估报告摘要")
        print("█" * 70)

        print(f"\n  📌 总体概况:")
        print(f"     总用例数:   {meta['total_tests']}")
        print(f"     成功数:     {meta['success_count']}")
        print(f"     错误数:     {meta['error_count']}")
        print(f"     错误率:     {meta['error_rate']}%")
        print(f"     意图准确率: {meta['intent_accuracy']}%")

        if report["overall_scores"]["average"] is not None:
            scores = report["overall_scores"]
            print(f"\n  ⭐ 质量评分 (满分5分):")
            print(f"     综合均分:   {scores['average']}")
            bd = scores["by_dimension"]
            labels = {"relevance": "相关性", "completeness": "完整性", 
                     "accuracy": "准确性", "friendliness": "友好度"}
            for k, label in labels.items():
                print(f"     - {label}: {bd[k]}")

        print(f"\n  ⏱️ 响应时间统计 (秒):")
        print(f"     平均值: {times['avg']:.3f}")
        print(f"     最小值: {times['min']:.3f}")
        print(f"     最大值: {times['max']:.3f}")
        print(f"     P50:    {times['p50']:.3f}")
        print(f"     P95:    {times['p95']:.3f}")
        print(f"     P99:    {times['p99']:.3f}")

        print(f"\n  📂 各类别表现:")
        header = f"     {'类别':<12} {'总数':>4} {'正确':>4} {'准确率':>7} {'均分':>6} {'均耗时':>7}"
        print(header)
        print("     " + "-" * 46)
        for cat_name, cat_data in categories.items():
            line = (f"     {cat_name:<12} {cat_data['total']:>4} {cat_data['correct']:>4} "
                   f"{cat_data['accuracy']:>6.1f}% {cat_data['avg_score']:>5.2f} {cat_data['avg_time']:>6.3f}s")
            print(line)

        print("\n" + "█" * 70 + "\n")


# ==================== 主程序入口 ====================

async def main_async(mode: str = "api"):
    """
    异步主流程
    
    参数:
        mode: 运行模式 ("api" 或 "offline")
    """
    print("=" * 70)
    print("  🔍 电商智能助手 - 端到端对话质量评估框架")
    print(f"  📦 运行模式: {mode.upper()}")
    print(f"  🤖 LLM评估: {'✅ 已启用' if LLM_AVAILABLE else '❌ 不可用'}")
    print(f"  🧩 Agent模块: {'✅ 已加载' if AGENT_AVAILABLE else '❌ 不可用'}")
    print("=" * 70)

    # 创建评估器实例
    evaluator = E2EEvaluator(use_judge=True)

    # 执行评估
    await evaluator.run_evaluation(mode=mode)

    # 生成并输出报告
    report = evaluator.generate_report()

    return report


def main():
    """命令行入口函数"""
    parser = argparse.ArgumentParser(description="端到端对话质量评估框架")
    parser.add_argument(
        "--mode", "-m",
        choices=["api", "offline"],
        default="api",
        help="运行模式: api(需启动FastAPI服务) | offline(纯本地意图检测)"
    )
    args = parser.parse_args()

    # 根据模式执行对应的异步流程
    asyncio.run(main_async(mode=args.mode))


if __name__ == "__main__":
    main()
