import io
import json
import unittest
import urllib.error
from datetime import date
from unittest import mock

import scheduler


class ParseDateTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(scheduler.parse_scheduled_date([[" 10/12/2026 "]]), date(2026, 10, 12))

    def test_invalid(self):
        for rows in [[], [[]], [[""]], [["2026-10-12"]], [["Maja"]]]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                scheduler.parse_scheduled_date(rows)


class BeatScheduleTests(unittest.TestCase):
    def test_daily_at_eight_belgrade(self):
        entry = scheduler.app.conf.beat_schedule["bin-reminder-daily"]
        self.assertEqual(entry["task"], "scheduler.check_bin_reminder")
        self.assertEqual(entry["schedule"].hour, {8})
        self.assertEqual(entry["schedule"].minute, {0})
        self.assertEqual(scheduler.app.conf.timezone, "Europe/Belgrade")


def fake_response(payload: dict):
    response = mock.MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    return response


def http_error(code: int):
    return urllib.error.HTTPError("http://hub", code, "err", {}, io.BytesIO(b'{"error": "x"}'))


@mock.patch.object(scheduler, "today", return_value=date(2026, 10, 12))
@mock.patch.object(scheduler, "get_scheduled_date", return_value=date(2026, 10, 12))
class TaskTests(unittest.TestCase):
    def run_task(self, **kwargs):
        return scheduler.check_bin_reminder.apply(kwargs=kwargs)

    @mock.patch("urllib.request.urlopen", return_value=fake_response({"id": "e1", "queued_to": ["mailer"]}))
    def test_triggers_when_due(self, urlopen, _scheduled, _today):
        result = self.run_task().get()
        self.assertTrue(result["triggered"])
        self.assertEqual(result["hub"]["queued_to"], ["mailer"])
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://hub:8000/notifications/")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(
            json.loads(request.data),
            {"notification_id": "okrugiceva.bin_reminder", "data": {"scheduled_date": "2026-10-12"}},
        )

    @mock.patch("urllib.request.urlopen")
    def test_skips_when_not_due(self, urlopen, _scheduled, today):
        today.return_value = date(2026, 10, 13)
        self.assertFalse(self.run_task().get()["triggered"])
        urlopen.assert_not_called()

    @mock.patch("urllib.request.urlopen", return_value=fake_response({"id": "e1"}))
    def test_today_override(self, urlopen, _scheduled, today):
        today.return_value = date(2026, 1, 1)
        self.assertTrue(self.run_task(today_override="2026-10-12").get()["triggered"])
        urlopen.assert_called_once()

    @mock.patch("urllib.request.urlopen", side_effect=http_error(404))
    def test_4xx_is_not_retried(self, _urlopen, _scheduled, _today):
        with mock.patch.object(scheduler.check_bin_reminder, "retry") as retry:
            with self.assertRaises(scheduler.HubRejected):
                self.run_task().get()
            retry.assert_not_called()

    def test_5xx_and_network_errors_are_retried(self, _scheduled, _today):
        for error in [http_error(503), urllib.error.URLError("connection refused")]:
            with self.subTest(error=error), mock.patch("urllib.request.urlopen", side_effect=error), \
                    mock.patch.object(scheduler.check_bin_reminder, "retry", side_effect=RuntimeError("retry")) as retry:
                with self.assertRaises(RuntimeError):
                    self.run_task().get()
                retry.assert_called_once()
                self.assertIs(retry.call_args.kwargs["exc"], error)


if __name__ == "__main__":
    unittest.main()
