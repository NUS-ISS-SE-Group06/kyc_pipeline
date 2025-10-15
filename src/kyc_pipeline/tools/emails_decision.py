# src/kyc_pipeline/tools/emails_decision.py


import os
import smtplib
from email.mime.text import MIMEText
from typing import Optional
from crewai.tools import tool

def _send_via_smtp(to: str, subject: str, body_md: str) -> str:
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    pwd  = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_SENDER", user or "no-reply@example.com")

    if not (host and user and pwd and to):
        return "email-stub:missing-smtp-config"

    msg = MIMEText(body_md, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"]   = to

    with smtplib.SMTP(host, port, timeout=10) as s:
        s.starttls()
        s.login(user, pwd)
        s.sendmail(sender, [to], msg.as_string())

    return "smtp-sent"

def _maybe_real_send(to: Optional[str], subject: str, body_md: str) -> str:
    provider = (os.getenv("EMAIL_PROVIDER") or "").lower().strip()
    if provider == "smtp":
        return _send_via_smtp(to or os.getenv("DEFAULT_TO", ""), subject, body_md)
    return "email-stub"

@tool("trigger_decision_email")
def trigger_decision_email(
    decision: Optional[str] = None,
    explanation: Optional[str] = None,
    to: Optional[str] = None,
    **kwargs,
) -> str:
    """
    Send a decision notification email. Tolerant to arg name variants.
    Known aliases handled:
      - decision: 'final_decision', 'finalDecision', 'verdict'
      - explanation: 'reason', 'rationale', 'explain', 'message'
      - to: 'recipient', 'email', 'email_to'
    """
    # --- alias mapping (no exceptions if absent) ---
    if decision is None:
        decision = kwargs.get("final_decision") or kwargs.get("finalDecision") or kwargs.get("verdict")
    if explanation is None:
        explanation = (
            kwargs.get("explanation")
            or kwargs.get("reason")
            or kwargs.get("rationale")
            or kwargs.get("explain")
            or kwargs.get("message")
        )
    if to is None:
        to = kwargs.get("to") or kwargs.get("recipient") or kwargs.get("email") or kwargs.get("email_to")

    # minimal guardrails (don’t crash the agent)
    decision = decision or "UNKNOWN"
    explanation = explanation or "No explanation provided."

    subject = f"KYC Decision: {decision}"
    body_md = f"Decision: {decision}\nReason: {explanation}"
    return _maybe_real_send(to, subject, body_md)
trigger_decision_email.model_rebuild()