import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",") if h.strip()]

INSTALLED_APPS = [
    "notifications",
]

MIDDLEWARE = []

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
    },
]

ROOT_URLCONF = "hub.urls"
WSGI_APPLICATION = "hub.wsgi.application"

# No database: the hub only forwards notifications to RabbitMQ.
DATABASES = {}

USE_TZ = True
TIME_ZONE = "UTC"

# Path to the JSON file mapping notification ids to queues/tasks.
ROUTING_CONFIG = os.environ.get("ROUTING_CONFIG", str(BASE_DIR.parent / "config" / "routing.json"))

# Celery (publisher only)
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_BROKER_CONNECTION_TIMEOUT = 5
# Fail fast when the broker is down so the endpoint can answer 503.
CELERY_TASK_PUBLISH_RETRY_POLICY = {
    "max_retries": 2,
    "interval_start": 0,
    "interval_step": 0.5,
    "interval_max": 1,
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}
