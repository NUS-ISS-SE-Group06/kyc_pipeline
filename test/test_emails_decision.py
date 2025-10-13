# tests/test_emails_decision_tool.py
import os
import importlib
import inspect

import pytest

MODULE_PATH = "kyc_pipeline.tools.emails_decision"


def test_tool_is_importable():
    mod = importlib.import_module(MODULE_PATH)
    assert hasattr(mod, "send_decision_email")


def test_run_signature_accepts_decision_and_explanation():
    mod = importlib.import_module(MODULE_PATH)
    tool = mod.send_decision_email
    # CrewAI Tool exposes .run that forwards to the registered function
    sig = inspect.signature(tool.run)
    # We only need it to accept at least 2 positional args
    params = list(sig.parameters.values())
    assert len(params) >= 2


def test_stub_path_is_deterministic_when_provider_unset(monkeypatch: pytest.MonkeyPatch):
    """With no EMAIL_PROVIDER configured, tool should return a stable stub id."""
    mod = importlib.import_module(MODULE_PATH)
    tool = mod.send_decision_email

    # Clear provider to force stub
    monkeypatch.delenv("EMAIL_PROVIDER", raising=False)

    res = tool.run("Approve", "All KYC checks passed", None)
    assert isinstance(res, str)
    # by default our implementation returns "email-stub"
    assert res.startswith("email-stub")


def test_smtp_provider_without_creds_falls_back_to_stub(monkeypatch: pytest.MonkeyPatch):
    """If SMTP provider selected but creds are missing, we still return a stub id."""
    mod = importlib.import_module(MODULE_PATH)
    tool = mod.send_decision_email

    # Force SMTP but remove creds
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
    for k in ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_SENDER", "DEFAULT_TO"]:
        monkeypatch.delenv(k, raising=False)

    res = tool.run("Reject", "Watchlist match", "user@example.com")
    assert isinstance(res, str)
    # our implementation uses this specific marker when SMTP config is incomplete
    assert res in {"email-stub:missing-smtp-config", "email-stub"}