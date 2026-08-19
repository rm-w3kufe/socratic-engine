"""Tests de integración socratic-engine × state-canon (v0.2.0).

El contrato: socratic-engine evalúa árboles de certificación; state-canon
provee la evidencia (declared vs observed). La integración es por
predicados que consultan el StateProvider — evidencia estructural,
certificada, fresca.

Usa JsonStateProvider con un fixture JSON local (no toca la infra real).
El fixture simula el dominio 'services': declared=TRUE en el modelo pero
observed=FALSE en el sistema → drift → el árbol NO puede certificar.
"""

import json
import sys
from pathlib import Path

import pytest

# socratic-engine en el path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from socratic_engine import PredicateResult, SocraticEngine, Truth

# state-canon: instalado, o accesible desde ~/state-canon-mcp (repo vecino).
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
                    "~/state-canon-mcp — la integración no se puede probar "
                    "aquí",
                    allow_module_level=True)


@pytest.fixture
def provider(tmp_path):
    """Fixture JSON con un servicio 'cache': declarado activo, observado inactivo."""
    doc = {
        "services": [
            {"name": "cache", "declared_active": True, "observed_active": True},
            {"name": "api", "declared_active": True, "observed_active": False},
        ]
    }
    p = tmp_path / "state.json"
    p.write_text(json.dumps(doc))
    return JsonStateProvider(str(p))


def test_query_services_returns_records(provider):
    records = provider.query("services")
    assert len(records) == 2
    assert {r["name"] for r in records} == {"cache", "api"}


def test_engine_predicate_over_statecanon(provider):
    """Un predicado registrado consulta state-canon como fuente de evidencia."""
    engine = SocraticEngine()

    @engine.register("service_declared_active")
    def service_declared_active(name, **kw):
        records = provider.query("services", {"name": name})
        if not records:
            return PredicateResult(truth=Truth.UNKNOWN, certified=False)
        return PredicateResult(
            truth=Truth.TRUE if records[0]["declared_active"] else Truth.FALSE,
            certified=True, evidence={"record": records[0]},
        )

    @engine.register("service_observed_active")
    def service_observed_active(name, **kw):
        records = provider.query("services", {"name": name})
        if not records:
            return PredicateResult(truth=Truth.UNKNOWN, certified=False)
        return PredicateResult(
            truth=Truth.TRUE if records[0]["observed_active"] else Truth.FALSE,
            certified=True, evidence={"record": records[0]},
        )

    # cache: declarado+observado activo → AND TRUE certificado
    ev = engine.evaluate({"op": "AND", "children": [
        {"predicate": "service_declared_active", "args": ["cache"]},
        {"predicate": "service_observed_active", "args": ["cache"]},
    ]})
    assert ev.is_true and ev.certified

    # api: declarado activo pero observado inactivo → contradicción
    # legítima (evidencia en conflicto) → DIALECTICAL_AND da UNKNOWN
    ev = engine.evaluate({"op": "DIALECTICAL_AND", "children": [
        {"predicate": "service_declared_active", "args": ["api"]},
        {"predicate": "service_observed_active", "args": ["api"]},
    ]})
    assert ev.is_unknown and ev.certified
    assert ev.metadata["dialectical_conflict"] is True
    assert ev.metadata["thesis"][0]["source"] == "service_declared_active"
    assert ev.metadata["antithesis"][0]["source"] == "service_observed_active"


def test_engine_predicate_unknown_on_missing_record(provider):
    """Dominio sin evidencia → UNKNOWN (R9: sin concesión silenciosa)."""
    engine = SocraticEngine()

    @engine.register("service_observed_active")
    def service_observed_active(name, **kw):
        records = provider.query("services", {"name": name})
        if not records:
            return PredicateResult(truth=Truth.UNKNOWN, certified=False)
        return PredicateResult(
            truth=Truth.TRUE if records[0]["observed_active"] else Truth.FALSE,
            certified=True, evidence={"record": records[0]},
        )

    ev = engine.evaluate({"predicate": "service_observed_active",
                          "args": ["nonexistent"]})
    assert ev.is_unknown and not ev.certified
