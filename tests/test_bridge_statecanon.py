"""Tests del bridge oficial socratic-engine × state-canon.

Cubren los 4 predicados canon_* del StateCanonBridge con un
JsonStateProvider sobre un fixture JSON local (no toca infra real).

El fixture simula el dominio 'services': 'cache' consistente,
'api' con drift (declarado activo, observado inactivo).
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from socratic_engine import SocraticEngine, Truth
from socratic_engine.bridge_statecanon import (
    StateCanonBridge,
    register_statecanon_bridge,
)

try:
    from state_canon.provider import JsonStateProvider
except ImportError:
    _candidates = [
        Path.home() / "state-canon-mcp",
        Path(__file__).resolve().parent.parent.parent / "state-canon-mcp",
    ]
    for _cand in _candidates:
        if (_cand / "state_canon").is_dir():
            sys.path.insert(0, str(_cand))
            break
    try:
        from state_canon.provider import JsonStateProvider
    except ImportError:
        pytest.skip("state-canon no está instalado ni accesible desde "
                    "~/state-canon-mcp — el bridge no se puede probar aquí",
                    allow_module_level=True)


@pytest.fixture
def provider(tmp_path):
    doc = {
        "services": [
            {"name": "cache", "declared_active": True, "observed_active": True},
            {"name": "api", "declared_active": True, "observed_active": False},
        ]
    }
    p = tmp_path / "state.json"
    p.write_text(json.dumps(doc))
    return JsonStateProvider(str(p))


@pytest.fixture
def bridge(provider):
    engine = SocraticEngine()
    b = StateCanonBridge(engine, provider)
    return engine, b


def test_bridge_registers_prefix(provider):
    engine = SocraticEngine()
    StateCanonBridge(engine, provider)
    for name in ("canon_query", "canon_matches", "canon_field_equals", "canon_drift"):
        assert name in engine.predicates


def test_register_convenience_function(provider):
    engine = SocraticEngine()
    b = register_statecanon_bridge(engine, provider)
    assert isinstance(b, StateCanonBridge)


def test_canon_query_found(bridge):
    engine, _ = bridge
    ev = engine.evaluate({"predicate": "canon_query", "args": ["services", '{"name": "cache"}']})
    assert ev.is_true and ev.certified


def test_canon_query_filter_json_dict(provider):
    # filter como dict Python (no solo string JSON)
    eng = SocraticEngine()
    StateCanonBridge(eng, provider)
    ev = eng.evaluate({"predicate": "canon_query",
                       "args": ["services", {"name": "cache"}]})
    assert ev.is_true and ev.certified


def test_canon_query_no_records(bridge):
    engine, _ = bridge
    ev = engine.evaluate({"predicate": "canon_query",
                          "args": ["services", '{"name": "ghost"}']})
    assert ev.is_unknown and not ev.certified


def test_canon_query_bad_filter(bridge):
    engine, _ = bridge
    # filtro no parseable → UNKNOWN no certificado
    ev = engine.evaluate({"predicate": "canon_query",
                          "args": ["services", "{not json"]})
    assert ev.is_unknown and not ev.certified


def test_canon_query_unknown_domain(bridge):
    engine, _ = bridge
    ev = engine.evaluate({"predicate": "canon_query",
                          "args": ["nonexistent", "{}"]})
    assert ev.is_unknown and not ev.certified


def test_canon_matches_true(bridge):
    engine, _ = bridge
    ev = engine.evaluate({"predicate": "canon_matches",
                          "args": ["services", '{"name": "cache"}',
                                   '{"declared_active": true, "observed_active": true}']})
    assert ev.is_true and ev.certified


def test_canon_matches_false_drift(bridge):
    engine, _ = bridge
    # api: declarado != observado → no matchea el expected completo
    ev = engine.evaluate({"predicate": "canon_matches",
                          "args": ["services", '{"name": "api"}',
                                   '{"declared_active": true, "observed_active": true}']})
    assert ev.is_false and ev.certified


def test_canon_matches_no_evidence(bridge):
    engine, _ = bridge
    ev = engine.evaluate({"predicate": "canon_matches",
                          "args": ["services", '{"name": "ghost"}',
                                   '{"a": 1}']})
    assert ev.is_unknown and not ev.certified


def test_canon_field_equals_true(bridge):
    engine, _ = bridge
    ev = engine.evaluate({"predicate": "canon_field_equals",
                          "args": ["services", '{"name": "cache"}', "observed_active", True]})
    assert ev.is_true and ev.certified


def test_canon_field_equals_false(bridge):
    engine, _ = bridge
    ev = engine.evaluate({"predicate": "canon_field_equals",
                          "args": ["services", '{"name": "api"}', "observed_active", True]})
    assert ev.is_false and ev.certified


def test_canon_field_equals_field_missing(bridge):
    engine, _ = bridge
    ev = engine.evaluate({"predicate": "canon_field_equals",
                          "args": ["services", '{"name": "cache"}', "nope", 1]})
    assert ev.is_unknown and not ev.certified


def test_canon_drift_true_when_consistent(bridge):
    engine, _ = bridge
    ev = engine.evaluate({"predicate": "canon_drift",
                          "args": ["services", '{"name": "cache"}',
                                   "declared_active", "observed_active"]})
    assert ev.is_true and ev.certified
    assert ev.evidence["drift"] == []


def test_canon_drift_false_on_conflict(bridge):
    engine, _ = bridge
    ev = engine.evaluate({"predicate": "canon_drift",
                          "args": ["services", '{"name": "api"}',
                                   "declared_active", "observed_active"]})
    assert ev.is_false and ev.certified
    assert len(ev.evidence["drift"]) == 1
    assert ev.evidence["drift"][0]["name"] == "api"


def test_canon_drift_no_evidence(bridge):
    engine, _ = bridge
    ev = engine.evaluate({"predicate": "canon_drift",
                          "args": ["services", '{"name": "ghost"}',
                                   "declared_active", "observed_active"]})
    assert ev.is_unknown and not ev.certified


def test_bridge_engine_composition(bridge):
    """El bridge compone: AND sobre canon_field_equals detecta consistencia."""
    engine, _ = bridge
    ev = engine.evaluate({"op": "AND", "children": [
        {"predicate": "canon_field_equals",
         "args": ["services", '{"name": "cache"}', "observed_active", True]},
        {"predicate": "canon_field_equals",
         "args": ["services", '{"name": "cache"}', "declared_active", True]},
    ]})
    assert ev.is_true and ev.certified


def test_bridge_dialectical_drift(bridge):
    """DIALECTICAL_AND sobre el drift de 'api': la contradicción certificada
    (declarado TRUE, observado FALSE) → UNKNOWN certificado con metadata."""
    engine, _ = bridge
    ev = engine.evaluate({"op": "DIALECTICAL_AND", "children": [
        {"predicate": "canon_field_equals",
         "args": ["services", '{"name": "api"}', "declared_active", True]},
        {"predicate": "canon_field_equals",
         "args": ["services", '{"name": "api"}', "observed_active", True]},
    ]})
    assert ev.is_unknown and ev.certified
    assert ev.metadata["dialectical_conflict"] is True


# ── COBERTURA: edge cases del bridge ──

def test_canon_query_filter_none(bridge):
    # filter None → {} → consulta todo el dominio (L70)
    engine, _ = bridge
    ev = engine.evaluate({"predicate": "canon_query", "args": ["services", None]})
    assert ev.is_true and ev.certified


def test_canon_query_filter_list_invalid(bridge):
    # filter tipo lista (no dict ni JSON-string) → None (L80)
    engine, _ = bridge
    ev = engine.evaluate({"predicate": "canon_query",
                          "args": ["services", [1, 2]]})
    assert ev.is_unknown and not ev.certified


def test_canon_query_unknown_filter_field(bridge):
    # campo de filtro desconocido → ValueError del provider → None (L111-112)
    engine, _ = bridge
    ev = engine.evaluate({"predicate": "canon_query",
                          "args": ["services", '{"no_such_field": 1}']})
    assert ev.is_unknown and not ev.certified


def test_canon_matches_invalid_expected(bridge):
    # expected no parseable → UNKNOWN no certificado (L148)
    engine, _ = bridge
    ev = engine.evaluate({"predicate": "canon_matches",
                          "args": ["services", '{"name": "cache"}', "{bad"]})
    assert ev.is_unknown and not ev.certified


def test_canon_field_equals_missing_field(bridge):
    # campo no existe en el record → UNKNOWN no certificado (L165)
    engine, _ = bridge
    ev = engine.evaluate({"predicate": "canon_field_equals",
                          "args": ["services", '{"name": "cache"}', "status", "ok"]})
    assert ev.is_unknown and not ev.certified


def test_canon_field_equals_no_records(bridge):
    # sin records → UNKNOWN no certificado (L165)
    engine, _ = bridge
    ev = engine.evaluate({"predicate": "canon_field_equals",
                          "args": ["services", '{"name": "ghost"}', "status", "ok"]})
    assert ev.is_unknown and not ev.certified


# ── MCP + bridge (opt-in) ──

def test_mcp_no_bridge_no_canon_tool():
    from socratic_engine.mcp_server import SocraticMCP
    mcp = SocraticMCP()
    resp = mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = [t["name"] for t in resp["result"]["tools"]]
    assert "socratic_canon_query" not in names
    # llamar a la tool sin bridge → error
    r = mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": "socratic_canon_query",
                               "arguments": {"domain": "services"}}})
    assert r["error"]["code"] == -32601


def test_mcp_with_bridge_exposes_tool(provider):
    from socratic_engine.mcp_server import SocraticMCP
    mcp = SocraticMCP(provider=provider)
    resp = mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = [t["name"] for t in resp["result"]["tools"]]
    assert "socratic_canon_query" in names


def test_mcp_canon_query_returns_truth(provider):
    from socratic_engine.mcp_server import SocraticMCP
    mcp = SocraticMCP(provider=provider)
    r = mcp.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                    "params": {"name": "socratic_canon_query",
                               "arguments": {"domain": "services",
                                             "filter": '{"name": "cache"}'}}})
    payload = r["result"]["content"][0]["text"]
    import json as _json
    data = _json.loads(payload)
    assert data["truth"] == "TRUE" and data["certified"] is True
