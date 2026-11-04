import json
from unittest import mock

from django.test import SimpleTestCase

from .routing import RoutingConfigError, Target, parse_routing

ROUTING = parse_routing(
    {
        "default_task": "notifications.handle",
        "routes": {
            "user.signup": [{"queue": "email"}, {"queue": "analytics"}],
            "order.created": [{"queue": "orders", "task": "orders.process"}],
        },
    }
)


class ParseRoutingTests(SimpleTestCase):
    def test_default_and_explicit_task(self):
        self.assertEqual(
            ROUTING.targets_for("user.signup"),
            (Target("email", "notifications.handle"), Target("analytics", "notifications.handle")),
        )
        self.assertEqual(ROUTING.targets_for("order.created"), (Target("orders", "orders.process"),))
        self.assertIsNone(ROUTING.targets_for("nope"))

    def test_invalid_configs(self):
        bad = [
            [],
            {"routes": []},
            {"routes": {"a": []}},
            {"routes": {"a": [{"task": "x"}]}},
            {"routes": {"a": [{"queue": ""}]}},
            {"routes": {"a": [{"queue": "q", "extra": 1}]}},
        ]
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(RoutingConfigError):
                parse_routing(raw)


@mock.patch("notifications.views.get_routing", return_value=ROUTING)
@mock.patch("notifications.views.celery_app.send_task")
class ReceiveNotificationTests(SimpleTestCase):
    url = "/notifications/"

    def post(self, body):
        data = body if isinstance(body, (str, bytes)) else json.dumps(body)
        return self.client.post(self.url, data=data, content_type="application/json")

    def test_fan_out(self, send_task, _):
        resp = self.post({"notification_id": "user.signup", "data": {"user": 1}})
        self.assertEqual(resp.status_code, 202)
        body = resp.json()
        self.assertEqual(body["queued_to"], ["email", "analytics"])
        self.assertEqual(send_task.call_count, 2)
        for call, queue in zip(send_task.call_args_list, ["email", "analytics"]):
            self.assertEqual(call.args, ("notifications.handle",))
            self.assertEqual(call.kwargs["queue"], queue)
            kwargs = call.kwargs["kwargs"]
            self.assertEqual(kwargs["event_id"], body["id"])
            self.assertEqual(kwargs["notification_id"], "user.signup")
            self.assertEqual(kwargs["data"], {"user": 1})
            self.assertIn("received_at", kwargs)

    def test_custom_task(self, send_task, _):
        resp = self.post({"notification_id": "order.created"})
        self.assertEqual(resp.status_code, 202)
        send_task.assert_called_once()
        self.assertEqual(send_task.call_args.args, ("orders.process",))
        self.assertEqual(send_task.call_args.kwargs["queue"], "orders")

    def test_bad_requests(self, send_task, _):
        for body in ["not json", [1, 2], {}, {"notification_id": 5}, {"notification_id": ""}]:
            with self.subTest(body=body):
                self.assertEqual(self.post(body).status_code, 400)
        send_task.assert_not_called()

    def test_unknown_id(self, send_task, _):
        self.assertEqual(self.post({"notification_id": "nope"}).status_code, 404)
        send_task.assert_not_called()

    def test_broker_failure(self, send_task, _):
        send_task.side_effect = ConnectionError("broker down")
        resp = self.post({"notification_id": "user.signup"})
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()["queued_to"], [])

    def test_get_not_allowed(self, send_task, _):
        self.assertEqual(self.client.get(self.url).status_code, 405)


@mock.patch("notifications.views.get_routing", return_value=ROUTING)
class LandingPageTests(SimpleTestCase):
    def test_lists_notification_slots(self, _):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Available notifications (2)")
        for text in ["user.signup", "order.created", "email", "analytics", "orders", "orders.process"]:
            self.assertContains(resp, text)
