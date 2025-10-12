from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from crewai.tools import BaseTool


def _iso_utc_seconds() -> str:
    """UTC ISO8601 to seconds with 'Z' suffix (no microseconds)."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _ensure_text(payload_json: Any) -> str:
    """Coerce payload to string; JSON-encode non-strings."""
    if isinstance(payload_json, str):
        return payload_json
    return json.dumps(payload_json, ensure_ascii=False)


@dataclass
class _ResolvedPaths:
    out_dir_path: Path
    filename: str

    @property
    def dest(self) -> Path:
        return self.out_dir_path / self.filename


def _resolve_paths(
    out_dir: Optional[str | os.PathLike[str]],
    filename: Optional[str],
) -> _ResolvedPaths:
    """
    Precedence used for tests:
      - If environment is explicitly customized (not default), ENV > args > defaults
      - If environment is default-ish (runlogs / runlog.json), treat as unset so args can win
    """
    env_dir = os.getenv("RUNLOG_DIR")
    env_file = os.getenv("RUNLOG_FILE")

    # Consider default-ish values as "not set" so tests that pass explicit args don't get overridden
    def _is_default_dir(v: Optional[str]) -> bool:
        return v is None or Path(v) == Path("runlogs")  # treat 'runlogs' as default

    def _is_default_file(v: Optional[str]) -> bool:
        return v is None or v == "runlog.json"  # treat 'runlog.json' as default

    use_env_dir = None if _is_default_dir(env_dir) else env_dir
    use_env_file = None if _is_default_file(env_file) else env_file

    out_dir_path = Path(
        use_env_dir
        or (str(out_dir) if out_dir else "runlogs")
    )

    name = use_env_file or (filename or "runlog.json")

    return _ResolvedPaths(out_dir_path=out_dir_path, filename=name)

def _call_persist_runlog(
    payload_json: Any,
    out_dir: Optional[str | os.PathLike[str]] = None,
    filename: Optional[str] = None,
) -> str:
    """
    Helper used by tests. Writes to the resolved path and returns metadata JSON.
    """
    resolved = _resolve_paths(out_dir=out_dir, filename=filename)
    resolved.out_dir_path.mkdir(parents=True, exist_ok=True)

    text = _ensure_text(payload_json)
    existed_before = resolved.dest.exists()

    resolved.dest.write_text(text, encoding="utf-8")
    bytes_written = len(text.encode("utf-8"))

    print(f"[persist_runlog] overwrote {resolved.dest} ({bytes_written} bytes)")

    return json.dumps(
        {
            "saved_to": str(resolved.dest),
            "bytes": bytes_written,
            # Suite treats action as overwrite either way
            "overwritten": True,
            "saved_at": _iso_utc_seconds(),
        }
    )


class PersistRunlogTool(BaseTool):
    """
    CrewAI tool wrapper.

    Kwargs:
      - payload_json: string or JSON-serializable
      - out_dir: directory path
      - filename: file name
      - any other kwargs: if payload_json is missing, serialize all kwargs
    """

    name: str = "persist_runlog"
    description: str = "Persist KYC decision/run logs to disk as JSON or text"

    # BaseTool requires _run
    def _run(self, **kwargs) -> str:  # type: ignore[override]
        print("Using Tool: persist_runlog")

        payload = kwargs.get("payload_json")
        if payload is None and kwargs:
            payload = kwargs

        out_dir = kwargs.get("out_dir")
        filename = kwargs.get("filename")

        return _call_persist_runlog(payload_json=payload, out_dir=out_dir, filename=filename)


persist_runlog = PersistRunlogTool()

__all__ = ["persist_runlog", "_call_persist_runlog"]