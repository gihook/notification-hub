"""Bin-change reminder mailer (Python port of okrugiceva-24/mail-sender/index.js).

Reads tenant emails and today's "replacer" from a Google Sheet and emails
everyone a reminder. When to send is decided by whoever emits the notification.
"""
import html
import os
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from google.oauth2 import service_account
from googleapiclient.discovery import build

SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


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


def parse_emails(rows: list[list[str]]) -> list[str]:
    """First cell of each row, skipping empty cells."""
    return [row[0].strip() for row in rows if row and row[0].strip()]


def parse_replacer(rows: list[list[str]]) -> str:
    """The replacer's name is the first cell of the first row."""
    name = rows[0][0].strip() if rows and rows[0] else ""
    if not name:
        raise ValueError(f"expected the replacer's name in the first cell, got {rows!r}")
    return name


def get_emails() -> list[str]:
    return parse_emails(_sheet_values(env("EMAILS_RANGE", "Stanari!C2:C100")))


def get_replacer() -> str:
    return parse_replacer(_sheet_values(env("REPLACER_RANGE", "Glavna!A5")))


# ---------------------------------------------------------------------- Email


def build_message(recipients: list[str], replacer: str) -> EmailMessage:
    schedule_url = env("SCHEDULE_URL")
    msg = EmailMessage()
    msg["Subject"] = "Podsetnik za menjanje kesa"
    msg["From"] = formataddr((env("MAIL_FROM_NAME", "Okrugiceva 24"), env("MAIL_FROM")))
    msg["To"] = ", ".join(recipients)
    msg["Message-ID"] = make_msgid()
    msg.set_content(
        "Pozdrav,\n\n"
        f"podsećam vas da je danas dan za menjanje kesa u dvorištu. Zadužen za danas je {replacer}. "
        "Ukoliko je zaduženi zauzet neka pusti mail da ga neko odmeni.\n\n"
        f"Raspored možete videti ovde: {schedule_url}\n"
    )
    msg.add_alternative(
        "<p>Pozdrav,</p>\n"
        "<p>podsećam vas da je danas dan za menjanje kesa u dvorištu. "
        f"Zadužen za danas je <b>{html.escape(replacer)}</b>. "
        "Ukoliko je zaduženi zauzet neka pusti mail da ga neko odmeni.</p>\n"
        f'<p>Raspored možete videti <a href="{html.escape(schedule_url)}">ovde</a>.</p>\n',
        subtype="html",
    )
    return msg


def send_message(msg: EmailMessage) -> None:
    host = env("SMTP_HOST", "mailpit")
    port = int(env("SMTP_PORT", "1025"))
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    use_ssl = os.environ.get("SMTP_SSL", "0") == "1"
    starttls = os.environ.get("SMTP_STARTTLS", "0") == "1"

    smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    with smtp_cls(host, port, timeout=30) as smtp:
        if starttls:
            smtp.starttls()
        if user:
            smtp.login(user, password)
        smtp.send_message(msg)
