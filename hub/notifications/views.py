import json
import logging
import uuid
from datetime import datetime, timezone

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from hub.celery import app as celery_app

from .routing import get_routing

logger = logging.getLogger(__name__)


def _error(status: int, message: str, **extra) -> JsonResponse:
    return JsonResponse({"error": message, **extra}, status=status)


@require_GET
def landing(request):
    routes = sorted(get_routing().routes.items())
    example_id = routes[0][0] if routes else "your.notification.id"
    return render(
        request,
        "notifications/landing.html",
        {
            "routes": routes,
            "endpoint": request.build_absolute_uri("/notifications/"),
            "example_id": example_id,
        },
    )


@csrf_exempt
@require_POST
def receive_notification(request):
    try:
        body = json.loads(request.body or b"")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _error(400, "request body must be valid JSON")
    if not isinstance(body, dict):
        return _error(400, "request body must be a JSON object")

    notification_id = body.get("notification_id")
    if not isinstance(notification_id, str) or not notification_id:
        return _error(400, "'notification_id' is required and must be a non-empty string")

    targets = get_routing().targets_for(notification_id)
    if targets is None:
        return _error(404, f"unknown notification_id {notification_id!r}")

    event_id = str(uuid.uuid4())
    payload = {
        "event_id": event_id,
        "notification_id": notification_id,
        "data": body.get("data"),
        "received_at": datetime.now(timezone.utc).isoformat(),
    }

    queued_to = []
    for target in targets:
        try:
            celery_app.send_task(target.task, kwargs=payload, queue=target.queue)
        except Exception:
            logger.exception("failed to publish %s (%s) to queue %s", notification_id, event_id, target.queue)
            return _error(503, "failed to publish notification", id=event_id, queued_to=queued_to)
        queued_to.append(target.queue)

    logger.info("published %s (%s) to %s", notification_id, event_id, queued_to)
    return JsonResponse({"id": event_id, "queued_to": queued_to}, status=202)
