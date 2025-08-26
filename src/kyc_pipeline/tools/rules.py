
from crewai.tools import tool
import json

@tool("fetch_business_rules")
def fetch_business_rules(org_id: str) -> str:
    """Return org rules JSON (stub)."""
    data = {"min_age": 18, "country": "SG", "doc_required": ["passport", "photo"]}
    return json.dumps(data)
