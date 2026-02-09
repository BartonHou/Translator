from celery import Celery
from app.settings import settings

celery = Celery(
    "translator",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_time_limit=300,
    task_soft_time_limit=280,
    worker_prefetch_multiplier=1,
)
