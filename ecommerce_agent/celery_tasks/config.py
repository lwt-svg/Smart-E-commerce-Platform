from celery import crontab

broker_url = "amqp://guest:guest@localhost:5672//"
result_backend = "redis://localhost:6379/1"

timezone = "Asia/Shanghai"

beat_schedule = {
    "vector_tasks": {
        "task": "celery_tasks.vector_task.tasks.update_vector_db",
        "schedule": crontab(hour=0, minute=0, day_of_month='1,4,7,10,13,16,19,22,25,28'),
    }
}
