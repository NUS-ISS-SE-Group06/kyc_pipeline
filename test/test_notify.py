import pytest
from kyc_pipeline.tools.notify import send_decision_email  # 👈 adjust module path if needed


@pytest.mark.parametrize(
    "to,subject,body_md",
    [
        ("alice@example.com", "Approved", "# Congrats\nYou’re approved."),
        ("bob@example.com", "Rejected", "## Sorry\nYour request was rejected."),
        ("", "", ""),  # empty strings still return a message id in the stub
    ],
)
def test_send_decision_email_func_returns_message_id(to, subject, body_md):
    """Call the underlying function via .func and verify the deterministic stub output."""
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
    """Ensure Tool.run() path matches the underlying function output."""
    via_func = send_decision_email.func(to, subject, body_md)
    via_run = send_decision_email.run(to, subject, body_md)
    assert via_func == "msg-001"
    assert via_run == "msg-001"
    assert via_run == via_func