from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    name = "notifications"

    def ready(self):
        # Load and validate routing.json at startup so a bad config fails fast.
        from .routing import get_routing

        get_routing()
