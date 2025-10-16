import json
import os
from pathlib import Path
from datetime import datetime
from kyc_pipeline.tools.runlog import persist_runlog

import pytest


def _call_persist_runlog(**kwargs) -> str:
    """
    Calls persist_runlog regardless of whether it's a plain function
    or a CrewAI Tool (with .run).
    """
    if hasattr(persist_runlog, "run"):
        return persist_runlog.run(**kwargs)  # Tool-wrapped
    return persist_runlog(**kwargs)          # Plain function


def _is_iso_seconds(ts: str) -> bool:
    try:
        dt = datetime.fromisoformat(ts)
        return dt.microsecond == 0
    except Exception:
        return False


def test_writes_and_overwrites(tmp_path: Path, capsys: pytest.CaptureFixture):
    out_dir = tmp_path / "runlogs"
    filename = "runlog.json"

    # First write
    res1_json = _call_persist_runlog(payload_json='{"a":1}', out_dir=str(out_dir), filename=filename)
    res1 = json.loads(res1_json)

    saved = Path(res1["saved_to"])
    assert saved.exists()
    assert saved.read_text(encoding="utf-8") == '{"a":1}'
    assert res1["bytes"] == len('{"a":1}')
    assert res1["overwritten"] is True
    assert _is_iso_seconds(res1["saved_at"])

    # Confirm print
    out = capsys.readouterr().out
    assert "[persist_runlog] overwrote" in out
    assert str(saved) in out

    # Second write (overwrite)
    res2_json = _call_persist_runlog(payload_json="second", out_dir=str(out_dir), filename=filename)
    res2 = json.loads(res2_json)

    assert saved.read_text(encoding="utf-8") == "second"
    assert res2["bytes"] == len("second")
    assert res2["overwritten"] is True
    assert _is_iso_seconds(res2["saved_at"])


def test_handles_non_string_payload(tmp_path: Path):
    payload = {"x": 1, "y": ["a", "b"]}
    res_json = _call_persist_runlog(payload_json=payload, out_dir=str(tmp_path / "logs"), filename="data.json")
    res = json.loads(res_json)

    saved = Path(res["saved_to"])
    assert saved.exists()

    text = saved.read_text(encoding="utf-8")
    assert json.loads(text) == payload
    assert res["bytes"] == len(text)
    assert res["overwritten"] is True
    assert _is_iso_seconds(res["saved_at"])


def test_env_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env_dir = tmp_path / "envlogs"
    env_file = "envrun.json"
    monkeypatch.setenv("RUNLOG_DIR", str(env_dir))
    monkeypatch.setenv("RUNLOG_FILE", env_file)

    res_json = _call_persist_runlog(payload_json="hello", out_dir=str(tmp_path / "ignored"), filename="ignored.json")
    res = json.loads(res_json)

    saved = Path(res["saved_to"])
    assert saved == env_dir / env_file
    assert saved.exists()
    assert saved.read_text(encoding="utf-8") == "hello"
    assert res["bytes"] == len("hello")
    assert res["overwritten"] is True
    assert _is_iso_seconds(res["saved_at"])

    # cleanup env
    monkeypatch.delenv("RUNLOG_DIR", raising=False)
    monkeypatch.delenv("RUNLOG_FILE", raising=False)


def test_creates_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Persist should create nested directory and write the file at the requested path.

    We clear RUNLOG_* env vars so they don't override the explicit out_dir/filename.
    """
    # Ensure test isn't affected by .env or shell exports
    monkeypatch.delenv("RUNLOG_DIR", raising=False)
    monkeypatch.delenv("RUNLOG_FILE", raising=False)

    payload = "x"
    out_dir = tmp_path / "nested" / "deep" / "runlogs"
    filename = "f.json"

    res_json = _call_persist_runlog(
        payload_json=payload,
        out_dir=str(out_dir),
        filename=filename,
    )
    res = json.loads(res_json)

    saved = Path(res["saved_to"])
    assert saved.exists(), f"Expected file to exist: {saved}"
    assert saved.parent == out_dir, f"Expected parent {out_dir}, got {saved.parent}"
    assert saved.name == filename, f"Expected filename {filename}, got {saved.name}"

    contents = saved.read_text(encoding="utf-8")
    assert contents == payload, f"Expected contents '{payload}', got '{contents}'"

    # Metadata checks
    assert res["bytes"] == len(payload), f"Expected {len(payload)} bytes, got {res['bytes']}"
    assert res["overwritten"] is True
    assert _is_iso_seconds(res["saved_at"]), f"saved_at not ISO seconds: {res['saved_at']}"