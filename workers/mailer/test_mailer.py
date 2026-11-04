import os
import unittest
from unittest import mock

os.environ.setdefault("MAIL_FROM", "hub@example.com")
os.environ.setdefault("SCHEDULE_URL", "https://example.com/schedule?a=1&b=2")

import mailer  # noqa: E402
import worker  # noqa: E402


class ParsingTests(unittest.TestCase):
    def test_parse_emails_skips_empty(self):
        rows = [["a@x.com"], [], [""], ["  b@x.com "]]
        self.assertEqual(mailer.parse_emails(rows), ["a@x.com", "b@x.com"])

    def test_parse_replacer(self):
        self.assertEqual(mailer.parse_replacer([[" Marko ", "3/7/2026"]]), "Marko")
        self.assertEqual(mailer.parse_replacer([["Marko"]]), "Marko")

    def test_parse_replacer_invalid(self):
        for rows in [[], [[]], [["  "]]]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                mailer.parse_replacer(rows)


class MessageTests(unittest.TestCase):
    @mock.patch.dict(os.environ, {"SCHEDULE_URL": "https://example.com/schedule?a=1&b=2"})
    def test_build_message(self):
        msg = mailer.build_message(["a@x.com", "b@x.com"], "<Marko>")
        self.assertEqual(msg["To"], "a@x.com, b@x.com")
        self.assertEqual(msg["Subject"], "Podsetnik za menjanje kesa")
        html = msg.get_body(("html",)).get_content()
        self.assertIn("<b>&lt;Marko&gt;</b>", html)
        self.assertIn('href="https://example.com/schedule?a=1&amp;b=2"', html)


@mock.patch.object(mailer, "send_message")
@mock.patch.object(mailer, "get_replacer", return_value="Marko")
@mock.patch.object(mailer, "get_emails", return_value=["a@x.com"])
class TaskTests(unittest.TestCase):
    def run_task(self, data=None):
        return worker.send_bin_reminder.apply(
            kwargs={"event_id": "e1", "notification_id": "okrugiceva.bin_reminder", "data": data, "received_at": "now"}
        ).get()

    def test_always_sends(self, _emails, _replacer, send):
        result = self.run_task({"any": "json"})
        self.assertEqual(result, {"sent": True, "recipients": 1, "replacer": "Marko"})
        send.assert_called_once()
        msg = send.call_args.args[0]
        self.assertEqual(msg["To"], "a@x.com")

    def test_no_recipients(self, emails, _replacer, send):
        emails.return_value = []
        self.assertFalse(self.run_task()["sent"])
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
