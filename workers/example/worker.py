"""Example consumer app — copy this directory to create a new consumer.

1. Name the task to match the "task" in config/routing.json
   (or "default_task" when a route doesn't set one).
2. Start the worker with -Q set to the queue(s) this app should consume.
"""
import os

from celery import Celery
from celery.utils.log import get_task_logger

app = Celery("example_worker", broker=os.environ.get("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//"))
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_acks_late=True,  # don't lose a notification if the worker dies mid-task
    worker_prefetch_multiplier=1,
)

logger = get_task_logger(__name__)


@app.task(name="notifications.handle")
def handle(event_id, notification_id, data, received_at):
    queue = handle.request.delivery_info.get("routing_key")
    logger.info("[%s] %s (%s) received_at=%s data=%r", queue, notification_id, event_id, received_at, data)
