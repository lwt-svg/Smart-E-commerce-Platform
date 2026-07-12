from celery_tasks.main import app
import os
import sys

# 添加项目根目录到 Python 路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

@app.task
def update_vector_db():
    """
    定时任务：完全重建评论向量库
    """
    from build_sentiment_reviews_db import build_sentiment_vector_db
    
    print("开始更新评论向量库...")
    build_sentiment_vector_db()
    print("评论向量库更新完成！")
    
    return {"status": "success", "message": "向量库更新完成"}