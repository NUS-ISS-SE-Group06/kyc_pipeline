# src/kyc_pipeline/tools/emails_decision.py

import os
import smtplib
from datetime import datetime
from typing import Optional, Tuple

from email.mime.text import MIMEText
from crewai.tools import tool

# --- PDF generation (ReportLab/Platypus) ---
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

# ------------------ helpers ------------------

def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def _compose_subject_body(decision: str, explanation: str) -> Tuple[str, str]:
    subject = f"KYC Decision: {decision}"
    body_md = f"Decision: {decision}\nReason: {explanation}"
    return subject, body_md

def _pdf_path(prefix: str, decision: str) -> str:
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    safe_dec = "".join(ch for ch in (decision or "UNKNOWN") if ch.isalnum() or ch in ("-", "_"))
    folder = os.path.join("data", "email")
    _ensure_dir(folder)
    return os.path.join(folder, f"{prefix}_{safe_dec}_{ts}.pdf")

def _decision_paragraphs(decision: str, explanation: str, customer_name: Optional[str], application_id: Optional[str]) -> list:
    name = customer_name or "Customer"
    app = f" (Application ID: {application_id})" if application_id else ""
    msg_intro = f"Dear {name},"

    if (decision or "").upper() == "APPROVE":
        body = (
            "We’re pleased to inform you that your Know Your Customer (KYC) verification has been approved"
            f"{app}. You can now continue using our services without interruption."
        )
    elif (decision or "").upper() == "HUMAN_REVIEW":
        body = (
            "Your KYC verification requires a brief manual review"
            f"{app}. This is a standard step to ensure the accuracy and safety of our process."
        )
    elif (decision or "").upper() == "REJECT":
        body = (
            "We regret to inform you that your KYC verification could not be completed successfully"
            f"{app}. This decision is based on our compliance checks."
        )
    else:
        body = (
            "We’re writing regarding the status of your KYC verification"
            f"{app}. Please see the details below."
        )

    details = f"Summary: {explanation or 'No additional details were provided.'}"
    closing = (
        "If you have any questions or believe this decision was made in error, please reply to this message "
        "or contact our support team. We’re here to help."
    )
    signoff = "Sincerely,\nCompliance Team"

    return [msg_intro, body, details, closing, signoff]

def _write_pdf_email(
    pdf_file: str,
    subject: str,
    to: Optional[str],
    decision: str,
    explanation: str,
    customer_name: Optional[str],
    application_id: Optional[str],
) -> str:
    doc = SimpleDocTemplate(pdf_file, pagesize=A4, leftMargin=22*mm, rightMargin=22*mm, topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Small", fontSize=9, textColor=colors.grey))
    styles.add(ParagraphStyle(name="Heading", parent=styles["Heading1"], fontSize=16, leading=20, spaceAfter=6))
    styles.add(ParagraphStyle(name="Body", parent=styles["BodyText"], fontSize=11, leading=16))
    styles.add(ParagraphStyle(name="Mono", parent=styles["BodyText"], fontName="Helvetica", fontSize=10, textColor=colors.black))

    elems = []

    # Header "brand bar"
    header_table = Table(
        [[Paragraph("<b>Compliance Notification</b>", styles["Heading"]),
          Paragraph(datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), styles["Small"])]],
        colWidths=[110*mm, 50*mm]
    )
    header_table.setStyle(TableStyle([
        ("BOTTOMPADDING", (0,0), (-1,0), 6),
        ("ALIGN", (1,0), (1,0), "RIGHT"),
    ]))
    elems.append(header_table)
    elems.append(HRFlowable(color=colors.black, thickness=0.8, width="100%"))
    elems.append(Spacer(1, 8))

    # Meta block
    meta = [
        ["Subject", subject],
        ["To", to or "(stub recipient)"],
        ["Decision", decision or "UNKNOWN"],
    ]
    meta_table = Table(meta, colWidths=[25*mm, 135*mm])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), colors.whitesmoke),
        ("TEXTCOLOR", (0,0), (-1,-1), colors.black),
        ("FONTNAME", (0,0), (-1,-1), "Helvetica"),
        ("FONTSIZE", (0,0), (-1,-1), 10),
        ("ALIGN", (0,0), (0,-1), "LEFT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LINEBELOW", (0,-1), (-1,-1), 0.25, colors.lightgrey),
        ("LEFTPADDING", (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    elems.append(meta_table)
    elems.append(Spacer(1, 10))

    # Body paragraphs
    for i, text in enumerate(_decision_paragraphs(decision, explanation, customer_name, application_id)):
        elems.append(Paragraph(text.replace("\n", "<br/>"), styles["Body"]))
        if i == 0:
            elems.append(Spacer(1, 6))
        else:
            elems.append(Spacer(1, 4))

    elems.append(Spacer(1, 10))
    elems.append(HRFlowable(color=colors.lightgrey, thickness=0.6, width="100%"))
    elems.append(Spacer(1, 4))
    elems.append(Paragraph("This PDF is an autogenerated copy of the decision email.", styles["Small"]))

    doc.build(elems)
    return f"email-stub:pdf-saved -> {pdf_file}"

# ------------------ email sending ------------------

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

def _maybe_send_and_always_pdf(
    to: Optional[str], subject: str, body_md: str,
    decision: str, explanation: str,
    customer_name: Optional[str], application_id: Optional[str]
) -> str:
    """
    If EMAIL_PROVIDER=smtp and SMTP_* are present, send via SMTP.
    Regardless, ALWAYS save a PDF to data/email/.
    """
    provider = (os.getenv("EMAIL_PROVIDER") or "").lower().strip()
    smtp_result = None
    if provider == "smtp":
        smtp_result = _send_via_smtp(to or os.getenv("DEFAULT_TO", ""), subject, body_md)

    pdf_file = _pdf_path("kyc_email", decision)
    pdf_result = _write_pdf_email(pdf_file, subject, to, decision, explanation, customer_name, application_id)

    return (smtp_result or "email-stub") + " | " + pdf_result

# ------------------ public tool ------------------

@tool("trigger_decision_email")
def trigger_decision_email(
    decision: Optional[str] = None,
    explanation: Optional[str] = None,
    to: Optional[str] = None,
    # optional context to personalize the PDF/email:
    customer_name: Optional[str] = None,
    application_id: Optional[str] = None,
    **kwargs,
) -> str:
    """
    Send a decision notification email and ALWAYS save a professional PDF copy to data/email/.
    Aliases accepted:
      - decision: 'final_decision', 'finalDecision', 'verdict'
      - explanation: 'reason', 'rationale', 'explain', 'message'
      - to: 'recipient', 'email', 'email_to'
      - customer_name: 'name', 'customer', 'applicant_name'
      - application_id: 'doc_id', 'application', 'case_id'
    """
    # --- alias mapping (non-fatal if absent) ---
    decision = decision or kwargs.get("final_decision") or kwargs.get("finalDecision") or kwargs.get("verdict") or "UNKNOWN"
    explanation = (
        explanation or kwargs.get("explanation") or kwargs.get("reason")
        or kwargs.get("rationale") or kwargs.get("explain") or kwargs.get("message")
        or "No explanation provided."
    )
    to = to or kwargs.get("to") or kwargs.get("recipient") or kwargs.get("email") or kwargs.get("email_to")
    customer_name = customer_name or kwargs.get("customer_name") or kwargs.get("name") or kwargs.get("customer") or kwargs.get("applicant_name")
    application_id = application_id or kwargs.get("application_id") or kwargs.get("doc_id") or kwargs.get("application") or kwargs.get("case_id")

    subject, body_md = _compose_subject_body(decision, explanation)
    return _maybe_send_and_always_pdf(to, subject, body_md, decision, explanation, customer_name, application_id)

# Ensure pydantic models are rebuilt if CrewAI inspects the tool
trigger_decision_email.model_rebuild()