"""Load and validate the notification routing config (routing.json).

Format::

    {
      "default_task": "notifications.handle",
      "routes": {
        "<notification_id>": [{"queue": "<queue>", "task": "<optional task name>"}, ...]
      }
    }
"""
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from django.conf import settings


class RoutingConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Target:
    queue: str
    task: str


@dataclass(frozen=True)
class Routing:
    routes: dict[str, tuple[Target, ...]]

    def targets_for(self, notification_id: str) -> tuple[Target, ...] | None:
        return self.routes.get(notification_id)


def _require_str(value, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RoutingConfigError(f"{where} must be a non-empty string")
    return value


def parse_routing(raw: dict) -> Routing:
    if not isinstance(raw, dict):
        raise RoutingConfigError("routing config must be a JSON object")

    default_task = _require_str(raw.get("default_task", "notifications.handle"), "default_task")

    routes_raw = raw.get("routes")
    if not isinstance(routes_raw, dict):
        raise RoutingConfigError("'routes' must be an object of notification_id -> list of targets")

    routes: dict[str, tuple[Target, ...]] = {}
    for notification_id, targets_raw in routes_raw.items():
        _require_str(notification_id, "notification id")
        if not isinstance(targets_raw, list) or not targets_raw:
            raise RoutingConfigError(f"routes[{notification_id!r}] must be a non-empty list")

        targets = []
        for i, t in enumerate(targets_raw):
            where = f"routes[{notification_id!r}][{i}]"
            if not isinstance(t, dict):
                raise RoutingConfigError(f"{where} must be an object")
            unknown = set(t) - {"queue", "task"}
            if unknown:
                raise RoutingConfigError(f"{where} has unknown keys: {sorted(unknown)}")
            queue = _require_str(t.get("queue"), f"{where}.queue")
            task = _require_str(t.get("task", default_task), f"{where}.task")
            targets.append(Target(queue=queue, task=task))

        routes[notification_id] = tuple(targets)

    return Routing(routes=routes)


def load_routing(path: str | Path) -> Routing:
    path = Path(path)
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError as e:
        raise RoutingConfigError(f"routing config not found: {path}") from e
    except json.JSONDecodeError as e:
        raise RoutingConfigError(f"routing config {path} is not valid JSON: {e}") from e
    return parse_routing(raw)


@lru_cache(maxsize=1)
def get_routing() -> Routing:
    return load_routing(settings.ROUTING_CONFIG)
