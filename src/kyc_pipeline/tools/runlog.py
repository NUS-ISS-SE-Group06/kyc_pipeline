from crewai.tools import tool

@tool("persist_runlog")
def persist_runlog(event: str, corr_id: str, payload_json: str) -> str:
    """Persist a run log (stub). Hook to Postgres later."""
    # Implement INSERT INTO run_logs (...) VALUES (...) when ready.
    return "ok"
