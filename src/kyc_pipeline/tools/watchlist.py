# src/tools/watchlist.py
from __future__ import annotations
from crewai.tools import tool
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import json, os, time, uuid, logging, math, sqlite3

DEFAULT_SQLITE = "./kyc_local.db"
_pg_dsn = os.getenv("WATCHLIST_PG_DSN", "")
_db_from_dsn = _pg_dsn.replace("sqlite:///", "", 1) if _pg_dsn.startswith("sqlite:///") else None
DB_PATH = os.getenv("WATCHLIST_SQLITE_PATH", _db_from_dsn or DEFAULT_SQLITE)

EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")
EMBED_DIMS  = int(os.getenv("EMBED_DIMS", "1536"))
TOP_K       = int(os.getenv("WATCHLIST_TOPK", "5"))
HIGH_RISK_SIM   = float(os.getenv("RISK_HIGH_SIM", "0.92"))
MEDIUM_RISK_SIM = float(os.getenv("RISK_MEDIUM_SIM", "0.85"))
LOW_RISK_SIM    = float(os.getenv("RISK_LOW_SIM", "0.75"))

logger = logging.getLogger("fraudcheck.watchlist")
logger.setLevel(logging.INFO)

@dataclass
class EmbeddingResult:
    vector: Optional[List[float]]
    provider: str
    model: str

def _embed_openai(text: str) -> List[float]:
    from openai import OpenAI
    client = OpenAI()
    resp = client.embeddings.create(model=EMBED_MODEL, input=text)
    return resp.data[0].embedding

def _embed_via_router(text: str) -> Optional[List[float]]:
    """
    Try to get an embedding from router.py, supporting multiple router styles:
      - router.get_embedding(text, model=...)
      - router.embed(text, model=...)
      - router.LLMRouter().embed(text, model=...)
      - router.LLMRouter().embedding(text, model=...)
      - router.LLMRouter().embeddings(input=..., model=...)
    Return: list[float] or None if router is unavailable/failed.
    """
    try:
        import router

        # 1) module-level helpers
        if hasattr(router, "get_embedding") and callable(router.get_embedding):
            return router.get_embedding(text=text, model=EMBED_MODEL)
        if hasattr(router, "embed") and callable(router.embed):
            return router.embed(text=text, model=EMBED_MODEL)

        # 2) class-based router
        if hasattr(router, "LLMRouter"):
            r = router.LLMRouter()

            # common names
            for attr in ("embed", "embedding"):
                if hasattr(r, attr) and callable(getattr(r, attr)):
                    return getattr(r, attr)(text=text, model=EMBED_MODEL)

            # some routers mimic OpenAI-style "embeddings.create"
            if hasattr(r, "embeddings"):
                emb_api = getattr(r, "embeddings")
                # support both callable and object with .create
                if callable(emb_api):
                    out = emb_api(input=text, model=EMBED_MODEL)
                elif hasattr(emb_api, "create") and callable(emb_api.create):
                    out = emb_api.create(input=text, model=EMBED_MODEL)
                else:
                    out = None
                if out is not None:
                    # try common shapes: {"data":[{"embedding":[...]}]} or direct list
                    if isinstance(out, dict) and "data" in out and out["data"]:
                        maybe = out["data"][0].get("embedding")
                        if isinstance(maybe, list):
                            return maybe
                    if isinstance(out, list) and out and isinstance(out[0], (float, int)):
                        return list(out)
    except Exception as e:
        logger.warning("LLMRouter embedding failed or not available: %s", e)
    return None

def _embed(text: str) -> EmbeddingResult:
    text = (text or "").strip()
    if not text:
        return EmbeddingResult(None, "openai", EMBED_MODEL)
    vec = _embed_via_router(text)
    if vec is not None:
        return EmbeddingResult(vec, "router(openai)", EMBED_MODEL)
    return EmbeddingResult(_embed_openai(text), "openai", EMBED_MODEL)

def _normalize(s: Optional[str]) -> str:
    return (s or "").strip()

SQLITE_DDL_ENTITY = """
                    CREATE TABLE IF NOT EXISTS watchlist_entity (
                                                                    entity_id   TEXT PRIMARY KEY,
                                                                    full_name   TEXT NOT NULL,
                                                                    id_number   TEXT,
                                                                    address     TEXT,
                                                                    email       TEXT,
                                                                    source      TEXT NOT NULL DEFAULT 'LOCAL',
                                                                    notes       TEXT,
                                                                    embedding   TEXT  -- JSON array
                    );
                    """

def _open_sqlite() -> sqlite3.Connection:
    from pathlib import Path
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute(SQLITE_DDL_ENTITY)
    conn.commit()
    return conn

def _seed_if_empty(conn: sqlite3.Connection, min_rows: int = 20) -> None:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM watchlist_entity;")
    row = cur.fetchone()
    count = int(row[0]) if row else 0
    if count >= min_rows:
        return

    demo = [
        ("Rahul Menon", "SGP1234567Z", "Jurong West, Singapore", "rahul@example.com", "Known mule recruiter"),
        ("Aisha Karim", "SGP7654321X", "Tampines, Singapore", "aisha@example.com", "Chargeback ring"),
        ("Global Remit Co.", "UEN201912345A", "Raffles Place, Singapore", "ops@globalremit.example", "Dormant shell"),
        ("Wei Liang", "SGP9988776K", "Woodlands, Singapore", "weiliang@example.com", "Structuring alerts"),
        ("Priya N", "SGP4455667Q", "Hougang, Singapore", "priya@example.com", "Synthetic IDs"),
        ("Ivan Petrov", "RUS5566778P", "Moscow, RU", "ivan@example.ru", "PEP associate"),
        ("Maria Santos", "PHL1122334M", "Quezon City, PH", "maria@example.ph", "Watch notice"),
        ("John Smith", "USA8899001A", "San Mateo, US", "john@example.com", "High-risk merchant ties"),
        ("Nguyen An", "VNM3344556B", "Hanoi, VN", "an@example.vn", "Cash mule"),
        ("Chen Li", "CHN7788990C", "Shenzhen, CN", "chenli@example.cn", "Known alias"),
        ("Ahmed Z", "ARE5566443D", "Dubai, AE", "ahmed@example.ae", "Sanctions screening"),
        ("Olivia Brown", "GBR4433221E", "London, UK", "olivia@example.uk", "Chargeback disputes"),
        ("Carlos Ruiz", "MEX6655442F", "Mexico City, MX", "carlos@example.mx", "Smurfing pattern"),
        ("Hiro Tanaka", "JPN2211334G", "Osaka, JP", "hiro@example.jp", "Layering behavior"),
        ("Siti Rahmah", "MYS9988776H", "Johor, MY", "siti@example.my", "Watch notice"),
        ("Liu Wei", "CHN1122445J", "Beijing, CN", "liu.wei@example.cn", "Controlled entity"),
        ("Arun Varma", "IND5566778K", "Bengaluru, IN", "arun@example.in", "High-risk counterparties"),
        ("Sasha Ivanova", "UKR3322114L", "Kyiv, UA", "sasha@example.ua", "PEP associate"),
        ("Peter Chan", "HKG7788990M", "Kowloon, HK", "peter@example.hk", "Shell company links"),
        ("Fatima Noor", "PAK1239876N", "Karachi, PK", "fatima@example.pk", "Investigative lead"),
        ("Global Trade LLC", "UEN202012345B", "Raffles Place, Singapore", "contact@globaltrade.example", "Dormant"),
        ("OceanPay Ltd", "UEN201812300Z", "Tanjong Pagar, Singapore", "support@oceanpay.example", "Chargeback cluster")
    ]

    def _embed_text(full_name, id_number, address, email):
        return " | ".join([full_name, id_number, address, email])

    # Insert with embeddings
    for (full_name, id_number, address, email, notes) in demo:
        eid = str(uuid.uuid4())
        
        try:
            emb = _embed(_embed_text(full_name, id_number, address, email)).vector
        except Exception as e:
            logger.warning("Seeding: embedding failed; inserting without vector: %s", e)
            emb = None

        conn.execute(
            "INSERT OR REPLACE INTO watchlist_entity(entity_id, full_name, id_number, address, email, source, notes, embedding) VALUES (?,?,?,?,?,?,?,?)",
            (eid, full_name, id_number, address, email, "SEED", notes, json.dumps(emb))
        )
    conn.commit()

def _sqlite_exact_like(conn, name_q: str, id_q: str):
    cur = conn.cursor()
    exact_rows = []
    if id_q:
        cur.execute("""
                    SELECT entity_id, full_name, id_number, source, notes, 1.0 AS score, 'ID_EXACT' AS match_type
                    FROM watchlist_entity WHERE LOWER(id_number)=LOWER(?)
                        LIMIT 10;
                    """, (id_q,))
        exact_rows = [dict(r) for r in cur.fetchall()]
    if name_q and not exact_rows:
        cur.execute("""
                    SELECT entity_id, full_name, id_number, source, notes, 0.95 AS score, 'NAME_EXACT' AS match_type
                    FROM watchlist_entity WHERE LOWER(full_name)=LOWER(?)
                        LIMIT 10;
                    """, (name_q,))
        exact_rows = [dict(r) for r in cur.fetchall()] or exact_rows
    loose_rows = []
    if name_q:
        cur.execute("""
                    SELECT entity_id, full_name, id_number, source, notes, 0.70 AS score, 'NAME_LIKE' AS match_type
                    FROM watchlist_entity WHERE LOWER(full_name) LIKE LOWER(?)
                        LIMIT 10;
                    """, (f"%{name_q}%",))
        loose_rows = [dict(r) for r in cur.fetchall()]
    return exact_rows, loose_rows

def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    num = sum(x*y for x, y in zip(a, b))
    den = math.sqrt(sum(x*x for x in a)) * math.sqrt(sum(y*y for y in b))
    if den == 0:
        return 0.0
    return num / den

def _sqlite_vector(conn, query_vec: Optional[List[float]]):
    if query_vec is None:
        return []
    cur = conn.cursor()
    cur.execute("""
                SELECT entity_id, full_name, id_number, source, notes, embedding
                FROM watchlist_entity
                WHERE embedding IS NOT NULL
                    LIMIT 5000;
                """)
    rows = []
    for r in cur.fetchall():
        try:
            emb = json.loads(r["embedding"]) if r["embedding"] else None
        except Exception:
            emb = None
        score = _cosine(query_vec, emb) if emb else 0.0
        rows.append({
            "entity_id": r["entity_id"],
            "full_name": r["full_name"],
            "id_number": r["id_number"],
            "source": r["source"],
            "notes": r["notes"],
            "score": score,
            "match_type": "VECTOR"
        })
    rows.sort(key=lambda x: -x["score"])
    return rows[:TOP_K]

def _merge_and_score(exact_rows, loose_rows, vector_rows):
    best: Dict[str, Dict[str, Any]] = {}
    def keep(row):
        eid = str(row["entity_id"])
        cur = best.get(eid)
        if (cur is None) or (float(row["score"]) > float(cur["score"])):
            best[eid] = dict(row)
    for r in exact_rows + loose_rows + vector_rows:
        keep(r)
    matches = sorted(best.values(), key=lambda x: (-float(x["score"]), x.get("full_name","")))
    top_score = float(matches[0]["score"]) if matches else 0.0
    hard_exact = any(m["match_type"] in ("ID_EXACT","NAME_EXACT") for m in matches)
    return matches, top_score, hard_exact

@tool("watchlist_search")
def watchlist_search(
        name: str = "",
        id_number: str = "",
        address: str = "",
        email: str = "",
        requester_ref: str = ""
) -> str:
    """
    FraudCheck/Watchlist lookup (SQLite-only).

    Args:
        name: Person or entity full name to check.
        id_number: Government ID / registration number to check.
        address: Optional address text to add signal for vector search.
        email: Optional email text to add signal for vector search.
        requester_ref: Optional caller identifier (for tracing/logs only).

    Returns:
        JSON string with:
          - query: Echo of the inputs.
          - embedding: {provider, model, dims, used}
          - top_score: float similarity (0..1)
          - matches: list of {entity_id, full_name, id_number, source, score, match_type, notes}
          - explanation: reasoning + thresholds + backend info

    Behavior:
        - Auto-creates the SQLite DB and the `watchlist_entity` table on first call.
        - Seeds >=20 demo entities with embeddings if table is empty.
        - Matching strategy: exact ID -> exact NAME -> LIKE NAME -> vector cosine over JSON embeddings.
        - No audit writes (POC mode).
    """
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    logger.info("[%s] watchlist_search name=%r id=%r db=%s", ts, name, id_number, DB_PATH)

    embed_text = " | ".join([s for s in [name, id_number, address, email] if s]).strip()
    emb_vec = None
    provider = "openai"
    if embed_text:
        try:
            # Prefer router if available; fallback to OpenAI
            res = _embed(embed_text)
            emb_vec = res.vector
            provider = res.provider
        except Exception as e:
            logger.warning("Embedding failed; continuing with text-only search: %s", e)
            emb_vec = None
            provider = "disabled"

    conn = _open_sqlite()
    try:
        # Bootstrap + seed if needed
        _seed_if_empty(conn, min_rows=20)

        # Search paths
        exact_rows, loose_rows = _sqlite_exact_like(conn, _normalize(name), _normalize(id_number))
        vector_rows = _sqlite_vector(conn, emb_vec)
        matches, top_score, hard_exact = _merge_and_score(exact_rows, loose_rows, vector_rows)

        payload = {
            "query": {"name": name, "id_number": id_number, "address": address, "email": email, "requester_ref": requester_ref},
            "embedding": {"provider": provider, "model": EMBED_MODEL, "dims": EMBED_DIMS, "used": emb_vec is not None},
            "top_score": round(float(top_score), 4),
            "matches": [
                {
                    "entity_id": str(m["entity_id"]),
                    "full_name": m.get("full_name"),
                    "id_number": m.get("id_number"),
                    "source": m.get("source"),
                    "score": round(float(m.get("score", 0.0)), 4),
                    "match_type": m.get("match_type"),
                    "notes": m.get("notes"),
                }
                for m in matches
            ],
            "explanation": {
                "reasoning": "Exact/LIKE checks + Python cosine similarity over JSON-stored embeddings. Risk is computed downstream.",
                "signals": {
                    "top_score": round(float(top_score), 4),
                    "has_hard_exact": hard_exact,
                    "thresholds": {"HIGH": HIGH_RISK_SIM, "MEDIUM": MEDIUM_RISK_SIM, "LOW": LOW_RISK_SIM},
                    "backend": "sqlite-only",
                    "db_path": DB_PATH,
                },
            },
        }
        return json.dumps(payload, ensure_ascii=False)
    finally:
        conn.close()

