from langchain_openai import ChatOpenAI
from langchain_core.rate_limiters import InMemoryRateLimiter
from env_utils import  QWEN_API_KEY, QWEN_BASE_URL

#调用大模型的方法
llm = ChatOpenAI(
    model_name = "qwen3-coder-plus",
    temperature=0.5,
    api_key=QWEN_API_KEY,
    base_url=QWEN_BASE_URL,
    max_completion_tokens=256
)

# llm = ChatDeepSeek(
#     model_name = "deepseek-reasoner",
#     temperature=0.5,
#     api_key=DEEPSEEK_API_KEY,
#     api_base=DEEPSEEK_BASE_URL
# )

#自定义类调用大模型
# llm = SimpleQwenWithThinking(
#     api_key=QWEN_API_KEY,
#     model_name="qwen-plus",  
#     temperature=0.5,
#     enable_thinking=True, #启用深度思考
# )

#速率限制
# rate_limiter = InMemoryRateLimiter(
#     requests_per_second=0.1, #10s一次请求
#     check_every_n_seconds=0.1, #每100ms检查一次请求
#     max_bucket_size=10 #控制最大突发容量
# )
# llm = ChatOpenAI(
#     model_name = "qwen3-coder-plus",
#     temperature=1.3,
#     api_key=QWEN_API_KEY,
#     base_url=QWEN_BASE_URL,
#     rate_limiter=rate_limiter
# )