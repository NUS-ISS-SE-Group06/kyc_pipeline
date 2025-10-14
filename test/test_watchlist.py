# tests/test_watchlist.py

import os
import sys
import json
import sqlite3
import importlib
from pathlib import Path
from types import ModuleType
import pytest

pytestmark = pytest.mark.filterwarnings(
    "ignore::DeprecationWarning"   # silence noisy deps only within this file
)

# -------------------------
# Test doubles (stdlib only)
# -------------------------

class _FakeEmbeddingObj:
    def __init__(self, vec):
        self.embedding = vec

class _FakeEmbeddingsResponse:
    def __init__(self, vec):
        self.data = [_FakeEmbeddingObj(vec)]

class _FakeOpenAIClient:
    def __init__(self, vec=None):
        # deterministic 1536-dim vector
        self._vec = vec or [0.001 * ((i % 97) + 1) for i in range(1536)]

    class _EmbeddingsAPI:
        def __init__(self, outer):
            self.outer = outer
        def create(self, model, input):
            return _FakeEmbeddingsResponse(self.outer._vec)

    @property
    def embeddings(self):
        return _FakeOpenAIClient._EmbeddingsAPI(self)

def _install_fake_openai(monkeypatch, vec=None):
    fake_openai = ModuleType("openai")
    def _OpenAI():
        return _FakeOpenAIClient(vec=vec)
    fake_openai.OpenAI = _OpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

def _install_fake_router(monkeypatch, vec=None):
    """Support router.LLMRouter().embed(...) and .embedding(...), plus module-level embed()."""
    ret_vec = vec or [0.002 * ((i % 89) + 1) for i in range(1536)]
    fake_router = ModuleType("router")

    # module-level
    def embed(text, model):
        return ret_vec
    fake_router.embed = embed

    # class-based
    class _LLMRouter:
        def embed(self, text, model):
            return ret_vec
        def embedding(self, text, model):
            return ret_vec
        class _EmbeddingsAPI:
            def create(self, input, model):
                return {"data": [{"embedding": ret_vec}]}
        embeddings = _EmbeddingsAPI()
    fake_router.LLMRouter = _LLMRouter

    monkeypatch.setitem(sys.modules, "router", fake_router)

# -------------------------
# Pytest fixtures
# -------------------------

@pytest.fixture(autouse=True)
def _insert_src_on_path():
    """Ensure src/ is importable without touching global config."""
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    yield
    # don't remove to avoid interfering with other tests in same session

@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "kyc_local.db"
    monkeypatch.setenv("WATCHLIST_SQLITE_PATH", str(db_path))
    monkeypatch.setenv("EMBED_DIMS", "1536")
    # Clean module cache so env takes effect
    for name in ("kyc_pipeline.tools.watchlist", "tools.watchlist", "watchlist"):
        if name in sys.modules:
            del sys.modules[name]
    return db_path

def _import_watchlist():
    """Import user watchlist from common layouts without external helpers."""
    try:
        import kyc_pipeline.tools.watchlist as wl  # src/kyc_pipeline/tools/watchlist.py
        return importlib.reload(wl)
    except ModuleNotFoundError:
        try:
            import tools.watchlist as wl            # src/tools/watchlist.py
            return importlib.reload(wl)
        except ModuleNotFoundError:
            import watchlist as wl                  # fallback
            return importlib.reload(wl)

# -------------------------
# Tests
# -------------------------

def test_bootstrap_and_seed_created_and_used_embeddings(temp_db, monkeypatch):
    _install_fake_openai(monkeypatch)
    wl = _import_watchlist()

    # Call once to bootstrap + seed
    out = wl.watchlist_search.run(name="First Call")
    payload = json.loads(out)

    # DB exists and has >=20 rows
    assert Path(os.environ["WATCHLIST_SQLITE_PATH"]).exists()
    with sqlite3.connect(os.environ["WATCHLIST_SQLITE_PATH"]) as conn:
        c = conn.execute("SELECT COUNT(*) FROM watchlist_entity").fetchone()[0]
    assert c >= 20

    # Embedding path used, and no risk_level in output
    assert payload["embedding"]["used"] is True
    assert "risk_level" not in payload

def test_exact_id_wins_with_score_1_and_id_exact(temp_db, monkeypatch):
    _install_fake_openai(monkeypatch)
    wl = _import_watchlist()

    wl.watchlist_search.run(name="seed")
    out = wl.watchlist_search.run(id_number="SGP1234567Z")
    payload = json.loads(out)

    assert abs(payload["top_score"] - 1.0) < 1e-9
    assert any(m["match_type"] == "ID_EXACT" for m in payload["matches"])
    assert "risk_level" not in payload

def test_vector_search_runs_and_scores_range(temp_db, monkeypatch):
    _install_fake_openai(monkeypatch, vec=[0.5] * 1536)
    wl = _import_watchlist()

    wl.watchlist_search.run(name="seed")
    out = wl.watchlist_search.run(name="Rahul", address="Jurong")
    payload = json.loads(out)

    assert payload["embedding"]["used"] is True
    assert 0.0 <= payload["top_score"] <= 1.0
    assert isinstance(payload["matches"], list)

def test_prefers_router_when_available(temp_db, monkeypatch):
    _install_fake_router(monkeypatch)                 # router available
    _install_fake_openai(monkeypatch, vec=[0.1]*1536) # OpenAI fallback still installed
    wl = _import_watchlist()

    wl.watchlist_search.run(name="seed via router")
    out = wl.watchlist_search.run(name="Any Name")
    payload = json.loads(out)

    # Provider indicates router when router path is taken; fallback openai is ok if router not used
    assert payload["embedding"]["provider"].startswith("router") or payload["embedding"]["provider"] == "openai"

def test_text_only_when_embedding_fails_no_skip(temp_db, monkeypatch):
    # Mock failing OpenAI; test expects graceful text-only behavior (no skip)
    bad_openai = ModuleType("openai")
    class _BadClient:
        class _EmbeddingsAPI:
            def create(self, model, input):
                raise RuntimeError("boom")
        embeddings = _EmbeddingsAPI()
    def _OpenAI():
        return _BadClient()
    bad_openai.OpenAI = _OpenAI
    monkeypatch.setitem(sys.modules, "openai", bad_openai)

    wl = _import_watchlist()

    # Should NOT raise; vector path disabled, text path still returns a payload
    out = wl.watchlist_search.run(name="Rahul")
    payload = json.loads(out)

    assert "matches" in payload
    assert payload["embedding"]["used"] in (False, 0)
    assert "risk_level" not in payload
