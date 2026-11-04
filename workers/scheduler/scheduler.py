"""Scheduler (producer) app.

Celery Beat runs ``check_bin_reminder`` every day at 08:00 Europe/Belgrade.
The task reads the scheduled date from the Google Sheet and, when it is today,
posts the ``okrugiceva.bin_reminder`` notification to the hub. The hub routes
it (config/routing.json) to the mailer, which sends the email.
"""
import json
import os
import urllib.error
import urllib.request
from datetime import date, datetime
from zoneinfo import ZoneInfo

from celery import Celery
from celery.schedules import crontab
from celery.utils.log import get_task_logger
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError as GoogleHttpError

TZ = "Europe/Belgrade"
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

app = Celery("scheduler", broker=os.environ.get("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//"))
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    timezone=TZ,
    task_default_queue="scheduler",
    beat_schedule_filename="/tmp/celerybeat-schedule",
    beat_schedule={
        "bin-reminder-daily": {
            "task": "scheduler.check_bin_reminder",
            "schedule": crontab(hour=8, minute=0),
        },
    },
)

logger = get_task_logger(__name__)


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None or value == "":
        raise RuntimeError(f"missing required environment variable {name}")
    return value


# ---------------------------------------------------------------- Google Sheets


def _sheet_values(range_: str) -> list[list[str]]:
    credentials = service_account.Credentials.from_service_account_file(
        env("GOOGLE_CREDENTIALS_PATH", "/secrets/credentials.json"), scopes=SHEETS_SCOPES
    )
    sheets = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    result = sheets.spreadsheets().values().get(spreadsheetId=env("SPREADSHEET_ID"), range=range_).execute()
    return result.get("values", [])


def parse_scheduled_date(rows: list[list[str]]) -> date:
    """The scheduled date is the first cell of the first row, formatted M/D/YYYY."""
    raw = rows[0][0].strip() if rows and rows[0] else ""
    try:
        return datetime.strptime(raw, "%m/%d/%Y").date()
    except ValueError as e:
        raise ValueError(f"expected a M/D/YYYY date in the first cell, got {rows!r}") from e


def get_scheduled_date() -> date:
    return parse_scheduled_date(_sheet_values(env("REPLACER_DATE_RANGE", "Glavna!B5")))


def today() -> date:
    return datetime.now(ZoneInfo(TZ)).date()


# ------------------------------------------------------------------------ Hub


class HubRejected(Exception):
    """The hub answered 4xx: retrying won't help (e.g. unknown notification id)."""


def post_notification(notification_id: str, data: dict) -> dict:
    body = json.dumps({"notification_id": notification_id, "data": data}).encode()
    request = urllib.request.Request(
        env("HUB_URL", "http://hub:8000/notifications/"),
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as e:
        if 400 <= e.code < 500:
            raise HubRejected(f"hub returned {e.code}: {e.read().decode(errors='replace')}") from e
        raise  # 5xx -> retried by the task


# ----------------------------------------------------------------------- Task


@app.task(name="scheduler.check_bin_reminder", bind=True, max_retries=5)
def check_bin_reminder(self, today_override: str | None = None):
    """Post the bin reminder notification if the sheet's scheduled date is today.

    ``today_override`` (ISO date) is for manual testing only.
    """
    try:
        scheduled = get_scheduled_date()
        current = date.fromisoformat(today_override) if today_override else today()
        result = {"scheduled_date": scheduled.isoformat(), "today": current.isoformat()}

        if scheduled != current:
            logger.info("bin reminder not due: %s", result)
            return {"triggered": False, **result}

        notification_id = env("NOTIFICATION_ID", "okrugiceva.bin_reminder")
        hub_response = post_notification(notification_id, {"scheduled_date": scheduled.isoformat()})
        logger.info("bin reminder triggered: %s hub=%s", result, hub_response)
        return {"triggered": True, **result, "hub": hub_response}
    except (OSError, GoogleHttpError) as e:  # network, hub 5xx (HTTPError is an OSError), Google API errors
        countdown = 30 * 2**self.request.retries
        logger.warning("bin reminder check failed (%s), retrying in %ss", e, countdown)
        raise self.retry(exc=e, countdown=countdown)
