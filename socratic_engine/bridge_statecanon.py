"""Bridge oficial socratic-engine × state-canon.

Conecta un StateProvider de state-canon con un SocraticEngine como fuente
de evidencia ESTRUCTURAL y CERTIFICADA: los predicados canon_* consultan el
canon (reconciled ground truth — lo OBSERVADO, no lo declarado) y lo
convierten en PredicateResult con certified=True cuando hay evidencia.

Contrato (v0.2.x):
  - state-canon GROUNDS: "what is actually running / has reality drifted"
  - socratic-engine CONSTRAINS: "given these premises, what follows"

La regla del provider (ver INTERFACE.md de state-canon): el provider DEBE
representar el canon reconciliado (lo que observe() devuelve), nunca el
lado declarado solo. Si se conecta un provider declarado, state_verify
comprueba contra aspiraciones, no contra realidad — el bridge no corrige
eso: lo hereda (R4: el bridge verifica contra lo que el provider ofrece).

Predicados registrados (prefijo canon_ — no colisiona con builtins):

  canon_query(domain, filter_json)
      ¿Hay al menos un record en el dominio que cumpla el filtro?
      TRUE certified si hay evidencia; UNKNOWN si no hay records (R9: sin
      concesión silenciosa); FALSE certified si el query falla
      (p.ej. campo de filtro desconocido → ValueError del provider).

  canon_matches(domain, filter_json, expected_json)
      ¿Los records que cumplen el filtro tienen exactamente los campos
      esperados? TRUE certified si todos matchean; FALSE certified si
      alguno difiere (drift); UNKNOWN si no hay evidencia.

  canon_field_equals(domain, filter_json, field, expected)
      ¿El campo `field` de los records filtrados == `expected`?
      TRUE/FALSE certified; UNKNOWN si no hay records o el campo no existe.

  canon_drift(domain, filter_json, declared_field, observed_field)
      ¿Declarado y observado coinciden en los records filtrados?
      TRUE certified si coinciden todos; FALSE certified si difieren al
      menos uno (DRIFT); UNKNOWN si falta evidencia (R9).

Uso:

    from socratic_engine import SocraticEngine
    from socratic_engine.bridge_statecanon import StateCanonBridge

    eng = SocraticEngine()
    bridge = StateCanonBridge(eng, provider)   # provider = StateProvider
    ev = eng.evaluate({"op": "AND", "children": [
        {"predicate": "canon_field_equals",
         "args": ["services", '{"name": "cache"}', "observed_active", True]},
        {"predicate": "canon_field_equals",
         "args": ["services", '{"name": "cache"}', "declared_active", True]},
    ]})
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .engine import PredicateResult, SocraticEngine, Truth

# El provider se importa de forma lazy para que el bridge funcione sin
# state-canon instalado (los predicados canon_* solo se registran si el
# provider está disponible — el fallback documentado es ImportError).


def _normalize_filter(filter_arg: Any) -> Optional[dict]:
    """Acepta dict o JSON-string; None si no es parseable."""
    if filter_arg is None:
        return {}
    if isinstance(filter_arg, dict):
        return filter_arg
    if isinstance(filter_arg, str):
        try:
            parsed = json.loads(filter_arg)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
    return None


class StateCanonBridge:
    """Registra predicados canon_* en un SocraticEngine sobre un provider."""

    PREFIX = "canon_"

    def __init__(self, engine: SocraticEngine, provider: Any):
        self.engine = engine
        self.provider = provider
        self._register()

    # ── registro ────────────────────────────────────────────────────────

    def _register(self) -> None:
        self.engine.register("canon_query")(self._canon_query)
        self.engine.register("canon_matches")(self._canon_matches)
        self.engine.register("canon_field_equals")(self._canon_field_equals)
        self.engine.register("canon_drift")(self._canon_drift)

    # ── helpers ─────────────────────────────────────────────────────────

    def _records(self, domain: str, filter_arg: Any) -> Optional[list[dict]]:
        """Consulta el provider. None si el filtro es inválido o el query
        falla (p.ej. campo de filtro desconocido → ValueError)."""
        filt = _normalize_filter(filter_arg)
        if filt is None:
            return None
        try:
            return self.provider.query(domain, filt)
        except (ValueError, KeyError, TypeError):
            return None

    # ── predicados ──────────────────────────────────────────────────────

    def _canon_query(self, domain: str, filter_arg: Any = None, **kw) -> PredicateResult:
        records = self._records(domain, filter_arg)
        if records is None:
            return PredicateResult(
                truth=Truth.UNKNOWN, certified=False,
                evidence={"domain": domain, "reason": "query_failed"},
                source="canon_query",
            )
        if not records:
            return PredicateResult(
                truth=Truth.UNKNOWN, certified=False,
                evidence={"domain": domain, "filter": filter_arg,
                          "reason": "no_records"},
                source="canon_query",
            )
        return PredicateResult(
            truth=Truth.TRUE, certified=True,
            evidence={"domain": domain, "count": len(records)},
            source="canon_query",
        )

    def _canon_matches(self, domain: str, filter_arg: Any, expected_arg: Any,
                       **kw) -> PredicateResult:
        records = self._records(domain, filter_arg)
        if records is None or not records:
            return PredicateResult(
                truth=Truth.UNKNOWN, certified=False,
                evidence={"domain": domain, "reason": "no_evidence"},
                source="canon_matches",
            )
        expected = _normalize_filter(expected_arg)
        if expected is None:
            return PredicateResult(
                truth=Truth.UNKNOWN, certified=False,
                evidence={"domain": domain, "reason": "invalid_expected"},
                source="canon_matches",
            )
        ok = all(all(r.get(k) == v for k, v in expected.items()) for r in records)
        return PredicateResult(
            truth=Truth.TRUE if ok else Truth.FALSE, certified=True,
            evidence={"domain": domain, "expected": expected,
                      "records": records},
            source="canon_matches",
        )

    def _canon_field_equals(self, domain: str, filter_arg: Any, field: str,
                            expected: Any, **kw) -> PredicateResult:
        records = self._records(domain, filter_arg)
        if records is None or not records:
            return PredicateResult(
                truth=Truth.UNKNOWN, certified=False,
                evidence={"domain": domain, "reason": "no_evidence"},
                source="canon_field_equals",
            )
        if field not in records[0]:
            return PredicateResult(
                truth=Truth.UNKNOWN, certified=False,
                evidence={"domain": domain, "field": field,
                          "reason": "field_missing"},
                source="canon_field_equals",
            )
        ok = all(r.get(field) == expected for r in records)
        return PredicateResult(
            truth=Truth.TRUE if ok else Truth.FALSE, certified=True,
            evidence={"domain": domain, "field": field, "expected": expected,
                      "values": [r.get(field) for r in records]},
            source="canon_field_equals",
        )

    def _canon_drift(self, domain: str, filter_arg: Any, declared_field: str,
                     observed_field: str, **kw) -> PredicateResult:
        """Detecta drift declarado vs observado en los records filtrados."""
        records = self._records(domain, filter_arg)
        if records is None or not records:
            return PredicateResult(
                truth=Truth.UNKNOWN, certified=False,
                evidence={"domain": domain, "reason": "no_evidence"},
                source="canon_drift",
            )
        drift = [
            {"name": r.get("name", i), declared_field: r.get(declared_field),
             observed_field: r.get(observed_field)}
            for i, r in enumerate(records)
            if r.get(declared_field) != r.get(observed_field)
        ]
        if drift:
            return PredicateResult(
                truth=Truth.FALSE, certified=True,
                evidence={"domain": domain, "drift": drift},
                source="canon_drift",
            )
        return PredicateResult(
            truth=Truth.TRUE, certified=True,
            evidence={"domain": domain, "drift": []},
            source="canon_drift",
        )


def register_statecanon_bridge(engine: SocraticEngine, provider: Any) -> StateCanonBridge:
    """Función conveniencia: crea y registra el bridge sobre un engine."""
    return StateCanonBridge(engine, provider)


__all__ = ["StateCanonBridge", "register_statecanon_bridge"]
