"""Mailer consumer app.

Consumes the "mailer" queue and handles the "okrugiceva.bin_reminder"
notification (see config/routing.json).
"""
import os

from celery import Celery
from celery.utils.log import get_task_logger

import mailer

app = Celery("mailer_worker", broker=os.environ.get("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//"))
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

logger = get_task_logger(__name__)


@app.task(
    name="mailer.send_bin_reminder",
    bind=True,
    autoretry_for=(OSError,),  # network/SMTP connection problems
    retry_backoff=30,
    retry_kwargs={"max_retries": 5},
)
def send_bin_reminder(self, event_id, notification_id, data, received_at):
    """Send the bin-change reminder. Always sends; the emitter decides when to trigger it."""
    emails = mailer.get_emails()
    replacer = mailer.get_replacer()

    logger.info("[%s] recipients=%d replacer=%r", event_id, len(emails), replacer)
    if not emails:
        logger.warning("[%s] no recipients found in the sheet; nothing sent", event_id)
        return {"sent": False, "reason": "no recipients"}

    msg = mailer.build_message(emails, replacer)
    mailer.send_message(msg)
    logger.info("[%s] reminder sent to %d recipients (%s)", event_id, len(emails), msg["Message-ID"])
    return {"sent": True, "recipients": len(emails), "replacer": replacer}
