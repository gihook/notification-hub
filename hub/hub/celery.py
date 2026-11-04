"""Publisher-only Celery app.

The hub never executes tasks; it only publishes messages with ``send_task`` so
that separate Celery applications (see ``workers/``) can consume them.
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hub.settings")

app = Celery("hub")
app.config_from_object("django.conf:settings", namespace="CELERY")
