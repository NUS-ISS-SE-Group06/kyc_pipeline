import json
import os
from pathlib import Path
from datetime import datetime, timezone

# This is the corrected import path for BaseTool
from crewai.tools import BaseTool

class PersistRunlogTool(BaseTool):
    name: str = "persist_runlog"
    description: str = (
        "Saves a JSON payload to a file, returning a JSON receipt."
        " Overwrites the file if it exists. Creates directories if needed."
    )

    def _run(self, payload_json: str | dict, filename: str | None = None) -> str:
        """
        Saves the run log. The filename is determined by environment variables
        if not explicitly provided.
        """
        if filename:
            out_path = Path(filename)
        else:
            runlog_dir = os.environ.get("RUNLOG_DIR", "runlogs/")
            runlog_file = os.environ.get("RUNLOG_FILE", "runlog.json")
            out_path = Path(runlog_dir) / runlog_file

        out_path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(payload_json, dict):
            content_to_write = json.dumps(payload_json)
        else:
            content_to_write = str(payload_json)

        out_path.write_text(content_to_write, encoding="utf-8")
        
        print(f"[{self.name}] overwrote {out_path} ({len(content_to_write)} bytes)")

        receipt = {
            "saved_to": str(out_path),
            "bytes": len(content_to_write),
            "overwritten": True,
            "saved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        return json.dumps(receipt)

persist_runlog = PersistRunlogTool()

