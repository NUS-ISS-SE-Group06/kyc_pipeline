from crewai.tools import tool
import json

@tool("watchlist_search")
def watchlist_search(name: str = "", id_number: str = "") -> str:
    """Return watchlist matches (stub)."""
    data = {"matches":[{"name":"A. Lovelace","score":0.11}]}
    return json.dumps(data)
