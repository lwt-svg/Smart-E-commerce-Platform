from dotenv import load_dotenv
import os

load_dotenv(override=True) #加载配置文件

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
QWEN_API_KEY = os.getenv("QWEN_API_KEY")
ZHIPU_API_KEY=os.getenv("ZHIPU_API_KEY")

DEEPSEEK_BASE_URL=os.getenv("DEEPSEEK_BASE_URL")
QWEN_BASE_URL=os.getenv("QWEN_BASE_URL")
ZHIPU_BASE_URL=os.getenv("ZHIPU_BASE_URL")