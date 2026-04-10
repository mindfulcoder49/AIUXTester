"""
utils/email.py — thin async wrapper around smtplib.

Requires SMTP_HOST to be set in config; silently no-ops if it isn't.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import config

logger = logging.getLogger("aiuxtester.email")


def _send_sync(to: str, subject: str, html_body: str, text_body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = config.SMTP_FROM
    msg["To"]      = to
    msg.attach(MIMEText(text_body or html_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        if config.SMTP_USER and config.SMTP_PASSWORD:
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.sendmail(config.SMTP_FROM, [to], msg.as_string())


async def send_email(to: str, subject: str, html_body: str, text_body: str = "") -> None:
    """Send an email. Skips silently if SMTP_HOST is not configured."""
    if not config.SMTP_HOST:
        logger.warning("SMTP_HOST not set — skipping email to %s: %s", to, subject)
        return
    try:
        await asyncio.to_thread(_send_sync, to, subject, html_body, text_body)
        logger.info("Email sent to %s: %s", to, subject)
    except Exception as exc:
        logger.exception("Failed to send email to %s: %s", to, exc)
        raise
