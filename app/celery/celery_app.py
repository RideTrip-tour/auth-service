from celery import Celery
from kombu import Exchange, Queue

from config import settings

celery_app = Celery(
    "auth",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.account_tasks"],
)

celery_app.conf.update(
    task_queues=(
        Queue("auth", Exchange("auth"), routing_key="auth"),
        Queue("profile", Exchange("profile"), routing_key="profile"),
    ),
    task_default_queue="auth",
    task_default_exchange="auth",
    task_default_routing_key="auth",
    task_routes={
        "auth.*": {"queue": "auth"},
        "profile.*": {"queue": "profile"},
    },
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 3600},
    result_expires=86400,
)
