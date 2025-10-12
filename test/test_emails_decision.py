# tests/test_emails_decision.py
import pytest

# Try both common layouts; adjust if your project uses a different path.
try:
    # e.g. if your code lives at kyc_pipeline/tools/notify.py
    from kyc_pipeline.tools.notify import send_decision_email  # type: ignore
except Exception:  # pragma: no cover
    # e.g. if your code lives at src/tools/notify.py
    from src.tools.notify import send_decision_email  # type: ignore


@pytest.mark.parametrize(
    "to,subject,body_md",
    [
        ("alice@example.com", "Approved", "# Congrats\nYou’re approved."),
        ("bob@example.com", "Rejected", "## Sorry\nYour request was rejected."),
        ("", "", ""),  # empty strings still return a message id in the stub
    ],
)
def test_send_decision_email_func_returns_message_id(to, subject, body_md):
    """
    Call the underlying function via .func and verify the deterministic stub output.
    Your notify.py should look like:

        from crewai.tools import tool

        @tool("send_decision_email")
        def send_decision_email(to: str, subject: str, body_md: str) -> str:
            return "msg-001"
    """
    result = send_decision_email.func(to, subject, body_md)
    assert isinstance(result, str)
    assert result == "msg-001"


@pytest.mark.parametrize(
    "to,subject,body_md",
    [
        ("carol@example.com", "KYC Result", "**Processed**"),
        ("dave@example.com", "Notice", "_Pending review_"),
    ],
)
def test_send_decision_email_run_matches_func(to, subject, body_md):
    """
    Ensure Tool.run() path matches the underlying function output.
    CrewAI's Tool.run generally forwards to the registered callable.
    """
    via_func = send_decision_email.func(to, subject, body_md)
    via_run = send_decision_email.run(to, subject, body_md)
    assert via_func == "msg-001"
    assert via_run == "msg-001"
    assert via_run == via_func