# tests/test_emails_decision_tool.py
import importlib
import os
from typing import Any, Tuple

import pytest

MODULE_PATH = "kyc_pipeline.tools.emails_decision"


def _resolve_tool() -> Any:
    """
    Returns the tool object regardless of whether the module exports it
    as `trigger_decision_email` (python name) or `send_decision_email`
    with @tool("trigger_decision_email").
    """
    mod = importlib.import_module(MODULE_PATH)

    tool = getattr(mod, "trigger_decision_email", None)
    if tool is None:
        tool = getattr(mod, "send_decision_email", None)

    assert tool is not None, (
        "Could not find a tool object. Expected either "
        "`trigger_decision_email` or `send_decision_email` in "
        f"{MODULE_PATH}"
    )
    return tool


def _base_marker(s: str) -> str:
    """
    Normalize tool return strings to their base marker, ignoring any
    extra annotations (e.g., ' | email-stub:pdf-saved -> ...').
    """
    if not isinstance(s, str):
        return ""
    return s.split(" | ", 1)[0].strip()


def test_tool_is_importable_and_named_correctly():
    tool = _resolve_tool()
    # CrewAI Tool instances have a `.name` that should be the decorator name.
    # We expect the Crew tool name to be "trigger_decision_email".
    assert hasattr(tool, "name")
    assert tool.name == "trigger_decision_email"


def test_run_accepts_runtime_args_without_signature_introspection():
    """
    CrewAI Tool.run is often (*args, **kwargs), so avoid signature assertions.
    Instead, call the tool with typical args and ensure it returns a string.
    """
    tool = _resolve_tool()

    # Clear provider to force stub
    os.environ.pop("EMAIL_PROVIDER", None)

    # Most implementations accept (decision, explanation, [to])
    result = tool.run("Approve", "All KYC checks passed", None)
    assert isinstance(result, str)


def test_stub_path_is_deterministic_when_provider_unset(monkeypatch: pytest.MonkeyPatch):
    """With no EMAIL_PROVIDER configured, tool should return a stable stub id."""
    tool = _resolve_tool()

    # Clear provider to force stub
    monkeypatch.delenv("EMAIL_PROVIDER", raising=False)

    res = tool.run("Approve", "All KYC checks passed", None)
    assert isinstance(res, str)
    # default path should be a stub marker (allow extra annotations)
    assert _base_marker(res).startswith("email-stub")


def test_smtp_provider_without_creds_falls_back_to_stub(monkeypatch: pytest.MonkeyPatch):
    """If SMTP provider is selected but creds are missing, return a stub id."""
    tool = _resolve_tool()

    # Force SMTP but remove creds
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
    for k in ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_SENDER", "DEFAULT_TO"]:
        monkeypatch.delenv(k, raising=False)

    res = tool.run("Reject", "Watchlist match", "user@example.com")
    assert isinstance(res, str)

    # Accept either explicit missing-config marker or generic stub.
    # Normalize first to tolerate extra annotations from the implementation.
    base = _base_marker(res)
    assert base in {"email-stub:missing-smtp-config", "email-stub"}