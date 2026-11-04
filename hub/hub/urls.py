from django.urls import path

from notifications.views import landing, receive_notification

urlpatterns = [
    path("", landing, name="landing"),
    path("notifications/", receive_notification, name="receive-notification"),
]
