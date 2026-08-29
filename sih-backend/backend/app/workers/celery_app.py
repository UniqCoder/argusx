"""
app/workers/celery_app.py — Celery application factory.

Broker: Redis (redis/1)
Result backend: Redis (redis/2)
Redis doubles as both broker and result backend for the prototype.
Per PRD §9.3: only swap to RabbitMQ if queue depth becomes a real problem.

Heavy jobs run here, off the API request path:
  Phase 2: alert_service.notify() task (enqueued on hold decision)
  Phase 3: graph_builder task (multi-hop traversal, Neo4j write)
  Phase 4: registry_refresh task (re-materialise risk scores after new label)
  Phase 5: pdf_report task
"""
from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "unigraph",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.tasks.alerts",
        "app.workers.tasks.graph_builder",
        "app.workers.tasks.registry_refresh",
        # Phase 5: "app.workers.tasks.pdf_report",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,           # re-queue on worker crash
    worker_prefetch_multiplier=1,  # fair dispatch
    broker_connection_timeout=0.2, # short timeout if broker unreachable
    broker_connection_retry_on_startup=False,
    task_publish_retry=False,      # never block the hot path if broker down
)
