# src/kyc_pipeline/tools/emails_decision.py
from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText
from typing import Optional
from crewai.tools import tool


def _send_via_smtp(to: str, subject: str, body_md: str) -> str:
    """Send email using simple SMTP credentials from env.
    Returns a provider message-id (best effort) or 'smtp-sent'."""
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    pwd  = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_SENDER", user or "no-reply@example.com")

    if not (host and user and pwd and to):
        # Missing config; fall back to stub
        return "email-stub:missing-smtp-config"

    msg = MIMEText(body_md, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"]   = to

    with smtplib.SMTP(host, port, timeout=10) as s:
        s.starttls()
        s.login(user, pwd)
        resp = s.sendmail(sender, [to], msg.as_string())

    # smtplib doesn't expose message-id; return deterministic success marker
    return "smtp-sent"


def _maybe_real_send(to: Optional[str], subject: str, body_md: str) -> str:
    """Try provider based on env; fall back to stub."""
    provider = (os.getenv("EMAIL_PROVIDER") or "").lower().strip()
    if provider == "smtp":
        return _send_via_smtp(to or os.getenv("DEFAULT_TO", ""), subject, body_md)

    # You can add Mailgun/SES branches here in future.
    # Default: deterministic stub
    return "email-stub"


@tool("trigger_decision_email")
def send_decision_email(decision: str, explanation: str, to: Optional[str] = None) -> str:
    """
    Send a decision notification email.

    - If EMAIL_PROVIDER + credentials are configured, sends a real email.
    - Otherwise returns a deterministic stub id so tests remain stable.
    """
    subject = f"KYC Decision: {decision}"
    body_md = f"Decision: {decision}\nReason: {explanation}"
    result_id = _maybe_real_send(to, subject, body_md)
    return result_id
# keep the function name as-is, but export an alias for import convenience
trigger_decision_email = send_decision_email