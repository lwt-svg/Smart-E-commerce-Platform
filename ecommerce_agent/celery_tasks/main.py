from celery import Celery

app = Celery("celery_tasks")

#加载config配置
app.config_from_object("celery_tasks.config")
#自动加载任务
app.autodiscover_tasks(["celery_tasks.vector_task"])
 