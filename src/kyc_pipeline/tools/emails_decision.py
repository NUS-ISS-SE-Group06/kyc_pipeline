
from crewai.tools import tool

@tool("send_decision_email")
def send_decision_email(decision: str, explanation: str) -> str:
    """
    Send a decision notification email (stub).
    In real life, you'd accept `to`, `subject`, `body_md` etc.
    For tests, we only need the tool to exist and be callable.
    """
    # simulate a provider send and return a message id
    return f"email-sent:decision={decision};reason={explanation}"
