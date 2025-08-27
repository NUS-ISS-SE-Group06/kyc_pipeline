from crewai.tools import tool

@tool("send_decision_email")
def send_decision_email(to: str, subject: str, body_md: str) -> str:
    """Send email via provider (stub)."""
    # e.g., call SES/Mailgun; here we return a fake message id
    return "msg-001"
