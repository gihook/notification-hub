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


# Email clients ignore <style> blocks and modern CSS, so the HTML uses tables and
# inline styles only. Placeholders are filled with str.format (hence doubled braces).
HTML_TEMPLATE = """\
<!doctype html>
<html lang="sr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>{subject}</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f2;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">Danas je zadužen/a {replacer}.</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f1f5f2;">
  <tr><td align="center" style="padding:32px 16px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
           style="max-width:520px;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #dde5df;
                  font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1f2a24;">
      <tr><td style="background:#2f7a4f;padding:20px 28px;">
        <div style="font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#cfe8d8;">{sender}</div>
        <div style="font-size:22px;font-weight:700;color:#ffffff;margin-top:4px;">&#128465;&#65039; Danas se menjaju kese</div>
      </td></tr>
      <tr><td style="padding:28px 28px 8px;font-size:16px;line-height:1.6;">
        <p style="margin:0 0 16px;">Pozdrav,</p>
        <p style="margin:0 0 20px;">podsećam vas da je danas dan za menjanje kesa u dvorištu.</p>
      </td></tr>
      <tr><td style="padding:0 28px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
               style="background:#eef7f1;border:1px solid #cde5d6;border-radius:10px;">
          <tr><td style="padding:18px 20px;">
            <div style="font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:#4d6b58;">Zadužen/a za danas</div>
            <div style="font-size:24px;font-weight:700;color:#1f5c3a;margin-top:4px;">{replacer}</div>
          </td></tr>
        </table>
      </td></tr>
      <tr><td style="padding:20px 28px 8px;font-size:15px;line-height:1.6;color:#3b4a41;">
        <p style="margin:0;">Ukoliko je zaduženi zauzet, neka pusti mail da ga neko odmeni.</p>
      </td></tr>
      <tr><td align="left" style="padding:20px 28px 28px;">
        <a href="{schedule_url}"
           style="display:inline-block;background:#2f7a4f;color:#ffffff;text-decoration:none;font-weight:600;
                  font-size:15px;padding:12px 22px;border-radius:8px;">Pogledaj raspored</a>
      </td></tr>
      <tr><td style="padding:16px 28px;border-top:1px solid #e6ece8;font-size:12px;color:#7a8a80;">
        Ova poruka je poslata automatski.
      </td></tr>
    </table>
  </td></tr>
</table>
</body>
</html>
"""

TEXT_TEMPLATE = """\
Pozdrav,

podsećam vas da je danas dan za menjanje kesa u dvorištu.

Zadužen/a za danas: {replacer}

Ukoliko je zaduženi zauzet, neka pusti mail da ga neko odmeni.

Raspored: {schedule_url}

--
{sender} · ova poruka je poslata automatski.
"""

SUBJECT = "Podsetnik: danas se menjaju kese"


def build_message(recipients: list[str], replacer: str) -> EmailMessage:
    schedule_url = env("SCHEDULE_URL")
    sender = env("MAIL_FROM_NAME", "Okrugiceva 24")

    msg = EmailMessage()
    msg["Subject"] = f"{SUBJECT} ({replacer})"
    msg["From"] = formataddr((sender, env("MAIL_FROM")))
    msg["To"] = ", ".join(recipients)
    msg["Message-ID"] = make_msgid()
    msg.set_content(TEXT_TEMPLATE.format(replacer=replacer, schedule_url=schedule_url, sender=sender))
    msg.add_alternative(
        HTML_TEMPLATE.format(
            subject=html.escape(SUBJECT),
            sender=html.escape(sender),
            replacer=html.escape(replacer),
            schedule_url=html.escape(schedule_url),
        ),
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
