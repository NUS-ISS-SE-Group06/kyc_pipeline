from crewai.tools import tool
import json

# --- Test dataset (5 records) ---
_WATCHLIST = [
    {"name": "Ada Lovelace",        "id_number": "ID-001", "source": "OFAC"},
    {"name": "Alan Turing",         "id_number": "ID-002", "source": "EU"},
    {"name": "Grace Hopper",        "id_number": "ID-003", "source": "UN"},
    {"name": "Katherine Johnson",   "id_number": "ID-004", "source": "Local"},
    {"name": "A. Lovelace",         "id_number": "AL-777", "source": "Custom"},
]

def _norm(s: str) -> str:
    return (s or "").strip().lower()

def _name_score(query: str, candidate: str) -> float:
    """Very simple scoring: exact (0.9), case-insensitive equal (0.9), substring (0.6) else 0."""
    q, c = _norm(query), _norm(candidate)
    if not q or not c:
        return 0.0
    if q == c:
        return 0.9
    if q in c or c in q:
        return 0.6
    return 0.0

def _id_score(query: str, candidate: str) -> float:
    """ID scoring: exact (1.0), case-insensitive equal (1.0), substring (0.7) else 0."""
    q, c = _norm(query), _norm(candidate)
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    if q in c or c in q:
        return 0.7
    return 0.0


@tool("watchlist_search")
def watchlist_search(name: str = "", id_number: str = "") -> str:
    """Return watchlist matches by simple plain-text comparison against a small stub dataset."""
    if not name and not id_number:
        raise ValueError("Provide at least name or id_number")

    results = []
    for rec in _WATCHLIST:
        ns = _name_score(name, rec["name"]) if name else 0.0
        is_ = _id_score(id_number, rec["id_number"]) if id_number else 0.0

        # Combine: take max, and add a small bonus if both matched
        score = max(ns, is_)
        if ns > 0 and is_ > 0:
            score = min(1.0, score + 0.1)

        # Only keep reasonably likely matches
        if score >= 0.5:
            results.append({
                "name": rec["name"],
                "id_number": rec["id_number"],
                "source": rec["source"],
                "score": round(score, 2),
            })

    # Sort by score (desc), then name
    results.sort(key=lambda r: (-r["score"], r["name"]))

    payload = {
        "query": {"name": name, "id_number": id_number},
        "matches": results
    }
    return json.dumps(payload)
