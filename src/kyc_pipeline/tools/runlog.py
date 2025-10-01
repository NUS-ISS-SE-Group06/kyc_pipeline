# src/kyc_pipeline/tools/runlog.py
from crewai.tools import tool
from pathlib import Path
from datetime import datetime
import os, json

def _ensure_str(s) -> str:
    if isinstance(s, (dict, list)):
        return json.dumps(s, ensure_ascii=False)
    return str(s)

@tool("persist_runlog")
def persist_runlog(
        payload_json: str,
        out_dir: str = "runlogs",
        filename: str = "runlog.json",   # <- always overwrite this file
) -> str:
    """
    Save the given payload_json STRING into a fixed file, overwriting on each call.

    Args:
      payload_json: JSON string to save (dict/list will be json.dumps'ed).
      out_dir: directory to store the file (default: runlogs). Can override with env RUNLOG_DIR.
      filename: target filename (default: runlog.json). Can override with env RUNLOG_FILE.

    Returns:
      JSON string: {"saved_to": "<path>", "bytes": <len>, "overwritten": true, "saved_at": "<iso8601>"}
    """
    payload_str = _ensure_str(payload_json)

    # Allow env overrides
    out_dir = os.getenv("RUNLOG_DIR", out_dir)
    filename = os.getenv("RUNLOG_FILE", filename)

    # Ensure directory exists
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    file_path = out_path / filename

    # OVERWRITE the same file each time
    with file_path.open("w", encoding="utf-8") as f:
        f.write(payload_str)

    result = {
        "saved_to": str(file_path),
        "bytes": len(payload_str),
        "overwritten": True,
        "saved_at": datetime.now().isoformat(timespec="seconds")
    }
    print(f"[persist_runlog] overwrote {result['saved_to']} ({result['bytes']} bytes)")
    return json.dumps(result, ensure_ascii=False)
