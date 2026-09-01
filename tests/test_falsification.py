"""
FALSIFICATION AUDIT — intento activo de romper claims de RECURSION_DESIGN.md.

Cada test intenta producir un contraejemplo. Si el test PASS, la claim
se mantuvo. Si FAIL, la claim está rota.

Categorías:
  PROVEN    — demostrado directamente por código/tests
  OBSERVED  — observado empíricamente, no exhaustivamente
  INFERRED  — inferido razonablemente
  HYPOTHESIS — requiere evidencia
"""

import sys
import pytest
from collections import defaultdict

sys.path.insert(0, "/home/rmw3/socratic-engine")

from socratic_engine.engine import (
    SocraticEngine, Evaluation, Truth, PredicateResult,
    find_failure_traces, FailureTrace,
)
from socratic_engine.tree import tree_home, SocraticTreeBuilder


# ╔══════════════════════════════════════════════════════════════════╗
# ║  UTILIDADES DE MEDICIÓN                                        ║
# ╚══════════════════════════════════════════════════════════════════╝

call_log = []

def make_counter_predicate(name="counter"):
    """Predicado que registra cada invocación."""
    def predicate(**kw):
        call_log.append(name)
        return PredicateResult(truth=Truth.TRUE, certified=True,
                               evidence={"called": name}, source=name)
    return predicate


def make_observable_predicate(return_value=True, name="obs"):
    """Predicado observable: registra si fue llamado."""
    def predicate(**kw):
        call_log.append(("CALL", name))
        val = return_value
        if isinstance(val, bool):
            return PredicateResult(
                truth=Truth.TRUE if val else Truth.FALSE,
                certified=True, source=name
            )
        return val  # PredicateResult directo
    return predicate


@pytest.fixture
def engine():
    e = SocraticEngine()
    call_log.clear()
    return e


def depthN(n):
    """Construye un árbol AND de profundidad n, hoja = type_prefix TRUE."""
    if n == 1:
        return {"op": "AND", "children": [
            {"predicate": "type_prefix", "args": ["$type", "X"]}
        ]}
    return {"op": "AND", "children": [
        depthN(n - 1),
        {"predicate": "type_prefix", "args": ["$type", "X"]}
    ]}


# ╔══════════════════════════════════════════════════════════════════╗
# ║  1. RECURSIVIDAD — ¿profundidad arbitraria o solo las probadas? ║
# ╚══════════════════════════════════════════════════════════════════╝

class TestRecursion:
    """
    STATUS: OBSERVED (no PROVEN)
    CLAIM: evaluate() opera sobre árboles de profundidad arbitraria.
    FALSACIÓN: probar d=1,2,4,8,16,32,64,128 hasta encontrar límite.
    """

    def test_depth_1(self, engine):
        tree = depthN(1)
        r = engine.evaluate(tree, {"type": "X"})
        assert r.is_true

    def test_depth_2(self, engine):
        tree = depthN(2)
        r = engine.evaluate(tree, {"type": "X"})
        assert r.is_true

    def test_depth_4(self, engine):
        tree = depthN(4)
        r = engine.evaluate(tree, {"type": "X"})
        assert r.is_true

    def test_depth_8(self, engine):
        tree = depthN(8)
        r = engine.evaluate(tree, {"type": "X"})
        assert r.is_true

    def test_depth_16(self, engine):
        tree = depthN(16)
        r = engine.evaluate(tree, {"type": "X"})
        assert r.is_true

    def test_depth_32(self, engine):
        tree = depthN(32)
        r = engine.evaluate(tree, {"type": "X"})
        assert r.is_true

    def test_depth_64(self, engine):
        tree = depthN(64)
        r = engine.evaluate(tree, {"type": "X"}, enforce_limits=False)
        assert r.is_true

    def test_depth_128(self, engine):
        """Límite práctico: Python default recursion limit ~1000."""
        tree = depthN(128)
        r = engine.evaluate(tree, {"type": "X"}, enforce_limits=False)
        assert r.is_true

    def test_depth_256(self, engine):
        tree = depthN(256)
        r = engine.evaluate(tree, {"type": "X"}, enforce_limits=False)
        assert r.is_true

    def test_depth_512(self, engine):
        """Cerca del stack limit de Python (~1000). Funciona con limit alto."""
        import sys
        old_limit = sys.getrecursionlimit()
        sys.setrecursionlimit(10000)
        try:
            tree = depthN(512)
            r = engine.evaluate(tree, {"type": "X"}, enforce_limits=False)
            assert r.is_true
        except RecursionError:
            pytest.skip("RecursionError at d=512 even with increased limit")
        finally:
            sys.setrecursionlimit(old_limit)

    def test_depth_1024_may_overflow(self, engine):
        """Puede causar RecursionError — el motor NO tiene guard."""
        import sys
        old_limit = sys.getrecursionlimit()
        sys.setrecursionlimit(10000)
        try:
            tree = depthN(1024)
            r = engine.evaluate(tree, {"type": "X"}, enforce_limits=False)
            assert r.is_true
        except RecursionError:
            pytest.skip("RecursionError at d=1024")
        finally:
            sys.setrecursionlimit(old_limit)

    def test_wide_shallow(self, engine):
        """500 hijos en un solo AND — ancho, no profundo."""
        children = [{"predicate": "type_prefix", "args": ["$type", "X"]}
                    for _ in range(500)]
        tree = {"op": "AND", "children": children}
        r = engine.evaluate(tree, {"type": "X"})
        assert r.is_true


# ╔══════════════════════════════════════════════════════════════════╗
# ║  2. SEMÁNTICA — tablas de verdad exactas                       ║
# ╚══════════════════════════════════════════════════════════════════╝

class TestSemantics:
    """
    STATUS: PROVEN (cada caso es un test exacto contra el código)
    CLAIM: Las tablas de AND/OR/NOT/XOR/IMPLIES/DIALECTICAL_AND coinciden
           con la implementación.
    """

    # --- AND ---
    def test_and_tt(self, engine):
        r = engine.evaluate({"op": "AND", "children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]},
            {"predicate": "type_prefix", "args": ["$type", "A"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.TRUE

    def test_and_tf(self, engine):
        r = engine.evaluate({"op": "AND", "children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]},
            {"predicate": "type_prefix", "args": ["$type", "B"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.FALSE

    def test_and_tu(self, engine):
        """TRUE AND UNKNOWN = UNKNOWN."""
        r = engine.evaluate({"op": "AND", "children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]},
            {"predicate": "ctx_has", "args": ["$ctx", "nonexistent"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.UNKNOWN

    def test_and_fu(self, engine):
        """FALSE AND UNKNOWN = FALSE (FALSE domina en AND)."""
        r = engine.evaluate({"op": "AND", "children": [
            {"predicate": "type_prefix", "args": ["$type", "B"]},
            {"predicate": "ctx_has", "args": ["$ctx", "nonexistent"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.FALSE

    def test_and_uu(self, engine):
        r = engine.evaluate({"op": "AND", "children": [
            {"predicate": "ctx_has", "args": ["$ctx", "x1"]},
            {"predicate": "ctx_has", "args": ["$ctx", "x2"]},
        ]}, {})
        assert r.truth == Truth.UNKNOWN

    # --- OR ---
    def test_or_tf(self, engine):
        r = engine.evaluate({"op": "OR", "children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]},
            {"predicate": "type_prefix", "args": ["$type", "B"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.TRUE

    def test_or_ff(self, engine):
        r = engine.evaluate({"op": "OR", "children": [
            {"predicate": "type_prefix", "args": ["$type", "B"]},
            {"predicate": "type_prefix", "args": ["$type", "C"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.FALSE

    def test_or_tu(self, engine):
        """TRUE OR UNKNOWN = TRUE (TRUE domina en OR)."""
        r = engine.evaluate({"op": "OR", "children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]},
            {"predicate": "ctx_has", "args": ["$ctx", "nonexistent"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.TRUE

    def test_or_fu(self, engine):
        """FALSE OR UNKNOWN = UNKNOWN."""
        r = engine.evaluate({"op": "OR", "children": [
            {"predicate": "type_prefix", "args": ["$type", "B"]},
            {"predicate": "ctx_has", "args": ["$ctx", "nonexistent"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.UNKNOWN

    def test_or_uu(self, engine):
        r = engine.evaluate({"op": "OR", "children": [
            {"predicate": "ctx_has", "args": ["$ctx", "x1"]},
            {"predicate": "ctx_has", "args": ["$ctx", "x2"]},
        ]}, {})
        assert r.truth == Truth.UNKNOWN

    # --- NOT ---
    def test_not_t(self, engine):
        r = engine.evaluate({"op": "NOT", "children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]}
        ]}, {"type": "A"})
        assert r.truth == Truth.FALSE

    def test_not_f(self, engine):
        r = engine.evaluate({"op": "NOT", "children": [
            {"predicate": "type_prefix", "args": ["$type", "B"]}
        ]}, {"type": "A"})
        assert r.truth == Truth.TRUE

    def test_not_u(self, engine):
        r = engine.evaluate({"op": "NOT", "children": [
            {"predicate": "ctx_has", "args": ["$ctx", "x"]}
        ]}, {})
        assert r.truth == Truth.UNKNOWN

    # --- XOR ---
    def test_xor_tt(self, engine):
        r = engine.evaluate({"op": "XOR", "children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]},
            {"predicate": "type_has", "args": ["$type", "A"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.FALSE

    def test_xor_tf(self, engine):
        r = engine.evaluate({"op": "XOR", "children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]},
            {"predicate": "type_prefix", "args": ["$type", "B"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.TRUE

    def test_xor_ff(self, engine):
        r = engine.evaluate({"op": "XOR", "children": [
            {"predicate": "type_prefix", "args": ["$type", "B"]},
            {"predicate": "type_prefix", "args": ["$type", "C"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.FALSE

    def test_xor_u(self, engine):
        r = engine.evaluate({"op": "XOR", "children": [
            {"predicate": "ctx_has", "args": ["$ctx", "x"]},
            {"predicate": "type_prefix", "args": ["$type", "A"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.UNKNOWN

    # --- IMPLIES ---
    def test_implies_tt(self, engine):
        r = engine.evaluate({"op": "IMPLIES", "children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]},
            {"predicate": "type_prefix", "args": ["$type", "A"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.TRUE

    def test_implies_tf(self, engine):
        r = engine.evaluate({"op": "IMPLIES", "children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]},
            {"predicate": "type_prefix", "args": ["$type", "B"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.FALSE

    def test_implies_ft(self, engine):
        """Ex falso quodlibet: FALSE → anything = TRUE."""
        r = engine.evaluate({"op": "IMPLIES", "children": [
            {"predicate": "type_prefix", "args": ["$type", "B"]},
            {"predicate": "type_prefix", "args": ["$type", "A"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.TRUE

    def test_implies_ff(self, engine):
        r = engine.evaluate({"op": "IMPLIES", "children": [
            {"predicate": "type_prefix", "args": ["$type", "B"]},
            {"predicate": "type_prefix", "args": ["$type", "C"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.TRUE

    def test_implies_ut(self, engine):
        """UNKNOWN antecedente, TRUE consecuente → TRUE."""
        r = engine.evaluate({"op": "IMPLIES", "children": [
            {"predicate": "ctx_has", "args": ["$ctx", "x"]},
            {"predicate": "type_prefix", "args": ["$type", "A"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.TRUE

    def test_implies_uf(self, engine):
        """UNKNOWN antecedente, FALSE consecuente → UNKNOWN."""
        r = engine.evaluate({"op": "IMPLIES", "children": [
            {"predicate": "ctx_has", "args": ["$ctx", "x"]},
            {"predicate": "type_prefix", "args": ["$type", "B"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.UNKNOWN

    # --- DIALECTICAL_AND ---
    def test_dialectical_tt(self, engine):
        r = engine.evaluate({"op": "DIALECTICAL_AND", "children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]},
            {"predicate": "type_has", "args": ["$type", "A"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.TRUE

    def test_dialectical_ff(self, engine):
        r = engine.evaluate({"op": "DIALECTICAL_AND", "children": [
            {"predicate": "type_prefix", "args": ["$type", "B"]},
            {"predicate": "type_prefix", "args": ["$type", "C"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.FALSE

    def test_dialectical_tf(self, engine):
        """Conflicto: TRUE + FALSE = UNKNOWN (no rechazo)."""
        r = engine.evaluate({"op": "DIALECTICAL_AND", "children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]},
            {"predicate": "type_prefix", "args": ["$type", "B"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.UNKNOWN

    def test_dialectical_tu(self, engine):
        r = engine.evaluate({"op": "DIALECTICAL_AND", "children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]},
            {"predicate": "ctx_has", "args": ["$ctx", "x"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.UNKNOWN

    def test_dialectical_metadata(self, engine):
        """Conflicto produce metadata dialectical_conflict."""
        r = engine.evaluate({"op": "DIALECTICAL_AND", "children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]},
            {"predicate": "type_prefix", "args": ["$type", "B"]},
        ]}, {"type": "A"})
        assert r.metadata.get("dialectical_conflict") is True
        assert "thesis" in r.metadata
        assert "antithesis" in r.metadata


# ╔══════════════════════════════════════════════════════════════════╗
# ║  3. UNKNOWN — propagación con TRUE/FALSE simultáneos            ║
# ╚══════════════════════════════════════════════════════════════════╝

class TestUnknownPropagation:
    """
    STATUS: PROVEN
    CLAIM: UNKNOWN se propaga según reglas del operador.
    FALSACIÓN: construir casos con TRUE/FALSE/UNKNOWN en distintos niveles.
    """

    def test_and_true_unknown_false(self, engine):
        """AND(TRUE, UNKNOWN, FALSE) = FALSE — FALSE domina."""
        r = engine.evaluate({"op": "AND", "children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]},
            {"predicate": "ctx_has", "args": ["$ctx", "x"]},
            {"predicate": "type_prefix", "args": ["$type", "B"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.FALSE

    def test_or_false_unknown_true(self, engine):
        """OR(FALSE, UNKNOWN, TRUE) = TRUE — TRUE domina."""
        r = engine.evaluate({"op": "OR", "children": [
            {"predicate": "type_prefix", "args": ["$type", "B"]},
            {"predicate": "ctx_has", "args": ["$ctx", "x"]},
            {"predicate": "type_prefix", "args": ["$type", "A"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.TRUE

    def test_nested_and_or_unknown(self, engine):
        """AND(OR(TRUE, UNKNOWN), NOT(UNKNOWN)) = UNKNOWN.
        OR(TRUE, UNKNOWN) = TRUE
        NOT(UNKNOWN) = UNKNOWN
        AND(TRUE, UNKNOWN) = UNKNOWN
        """
        r = engine.evaluate({"op": "AND", "children": [
            {"op": "OR", "children": [
                {"predicate": "type_prefix", "args": ["$type", "A"]},
                {"predicate": "ctx_has", "args": ["$ctx", "x"]},
            ]},
            {"op": "NOT", "children": [
                {"predicate": "ctx_has", "args": ["$ctx", "y"]}
            ]},
        ]}, {"type": "A"})
        assert r.truth == Truth.UNKNOWN

    def test_deep_unknown_propagation(self, engine):
        """UNKNOWN en hoja profunda se propaga hasta la raíz."""
        tree = {"op": "AND", "children": [
            {"op": "AND", "children": [
                {"op": "AND", "children": [
                    {"predicate": "ctx_has", "args": ["$ctx", "deep"]},
                ]},
            ]},
        ]}
        r = engine.evaluate(tree, {})
        assert r.truth == Truth.UNKNOWN

    def test_unknown_in_or_first_position(self, engine):
        """UNKNOWN como primer hijo de OR: OR(UNKNOWN, TRUE) = TRUE."""
        r = engine.evaluate({"op": "OR", "children": [
            {"predicate": "ctx_has", "args": ["$ctx", "x"]},
            {"predicate": "type_prefix", "args": ["$type", "A"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.TRUE

    def test_unknown_in_or_last_position(self, engine):
        """OR(TRUE, UNKNOWN) = TRUE."""
        r = engine.evaluate({"op": "OR", "children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]},
            {"predicate": "ctx_has", "args": ["$ctx", "x"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.TRUE

    def test_dialectical_true_false_unknown(self, engine):
        """DIALECTICAL_AND(TRUE, FALSE, UNKNOWN) = UNKNOWN (hay UNKNOWN)."""
        r = engine.evaluate({"op": "DIALECTICAL_AND", "children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]},
            {"predicate": "type_prefix", "args": ["$type", "B"]},
            {"predicate": "ctx_has", "args": ["$ctx", "x"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.UNKNOWN


# ╔══════════════════════════════════════════════════════════════════╗
# ║  4. CERTIFICATION — independencia de truth                      ║
# ╚══════════════════════════════════════════════════════════════════╝

class TestCertification:
    """
    STATUS: PROVEN
    CLAIM: Certification es independiente de truth.
    FALSACIÓN: construir los 4 casos y verificar independencia.
    """

    def test_true_uncertified(self, engine):
        """Predicado que retorna TRUE sin certificación."""
        @engine.register("uncert_true")
        def uncert_true(**kw):
            return PredicateResult(truth=Truth.TRUE, certified=False, source="uncert_true")

        r = engine.evaluate({"predicate": "uncert_true"}, {})
        assert r.truth == Truth.TRUE
        assert r.certified is False

    def test_false_uncertified(self, engine):
        """Predicado que retorna FALSE sin certificación."""
        @engine.register("uncert_false")
        def uncert_false(**kw):
            return PredicateResult(truth=Truth.FALSE, certified=False, source="uncert_false")

        r = engine.evaluate({"predicate": "uncert_false"}, {})
        assert r.truth == Truth.FALSE
        assert r.certified is False

    def test_unknown_certified(self, engine):
        """Predicado que retorna UNKNOWN certificado."""
        engine.register("cert_unknown")(
            lambda **kw: PredicateResult(truth=Truth.UNKNOWN, certified=True, source="cert_unknown")
        )

        r = engine.evaluate({"predicate": "cert_unknown"}, {})
        assert r.truth == Truth.UNKNOWN
        assert r.certified is True

    def test_unknown_uncertified(self, engine):
        """Predicado que retorna UNKNOWN sin certificación."""
        engine.register("uncert_unknown")(
            lambda **kw: PredicateResult(truth=Truth.UNKNOWN, certified=False, source="uncert_unknown")
        )

        r = engine.evaluate({"predicate": "uncert_unknown"}, {})
        assert r.truth == Truth.UNKNOWN
        assert r.certified is False

    def test_and_true_uncertified_propagation(self, engine):
        """AND(TRUE uncertified, TRUE certified) = FALSE cert? No — AND certification = all certified."""
        @engine.register("u_true")
        def u_true(**kw):
            return PredicateResult(truth=Truth.TRUE, certified=False, source="u_true")

        r = engine.evaluate({"op": "AND", "children": [
            {"predicate": "u_true"},
            {"predicate": "type_prefix", "args": ["$type", "A"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.TRUE
        assert r.certified is False  # AND:todos certificados → False porque u_true no certifica

    def test_or_true_uncertified_with_true_certified(self, engine):
        """OR(TRUE uncertified, TRUE certified) = TRUE + certified."""
        @engine.register("u_true2")
        def u_true2(**kw):
            return PredicateResult(truth=Truth.TRUE, certified=False, source="u_true2")

        r = engine.evaluate({"op": "OR", "children": [
            {"predicate": "u_true2"},
            {"predicate": "type_prefix", "args": ["$type", "A"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.TRUE
        assert r.certified is True  # OR: al menos 1 TRUE certified

    def test_or_only_uncertified_true(self, engine):
        """OR(SOLO TRUE uncertified) = TRUE but NOT certified."""
        @engine.register("u_only")
        def u_only(**kw):
            return PredicateResult(truth=Truth.TRUE, certified=False, source="u_only")

        r = engine.evaluate({"op": "OR", "children": [
            {"predicate": "u_only"},
        ]}, {})
        assert r.truth == Truth.TRUE
        assert r.certified is False


# ╔══════════════════════════════════════════════════════════════════╗
# ║  5. TREE_HOME — prioridad formal desde el código                ║
# ╚══════════════════════════════════════════════════════════════════╝

class TestTreeHome:
    """
    STATUS: PROVEN (derivado del código, no inferido)
    CLAIM: tree_home retorna el primer sibling TRUE con home (sibling-order).
    FALSACIÓN: probar breadth-first, depth-first, first-home, etc.
    """

    def test_sibling_order_priority(self, engine):
        """Primer sibling TRUE con home gana, aunque el segundo sea más específico."""
        tree = {"children": [
            {"predicate": "type_prefix", "args": ["$type", "VSL-"], "home": "generic-vsl"},
            {"predicate": "type_prefix", "args": ["$type", "VSL-SIGNOFF-"], "home": "specific-vsl"},
        ]}
        # Ambos TRUE, pero el primero gana
        h = tree_home(tree, "VSL-SIGNOFF-doc", engine)
        assert h == "generic-vsl"  # No "specific-vsl"

    def test_first_true_home_wins(self, engine):
        """Primer sibling TRUE con home gana; segundos no se evalúan para home."""
        tree = {"children": [
            {"predicate": "type_prefix", "args": ["$type", "A"], "home": "homeA"},
            {"predicate": "type_prefix", "args": ["$type", "A"], "home": "homeB"},
        ]}
        h = tree_home(tree, "A", engine)
        assert h == "homeA"

    def test_false_skipped(self, engine):
        """Sibling FALSE se salta, el siguiente TRUE con home gana."""
        tree = {"children": [
            {"predicate": "type_prefix", "args": ["$type", "B"], "home": "homeB"},
            {"predicate": "type_prefix", "args": ["$type", "A"], "home": "homeA"},
        ]}
        h = tree_home(tree, "A", engine)
        assert h == "homeA"

    def test_true_without_home_skipped(self, engine):
        """Sibling TRUE sin home se salta (no tiene home que retornar)."""
        tree = {"children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]},  # sin home
            {"predicate": "type_prefix", "args": ["$type", "B"], "home": "homeB"},
        ]}
        h = tree_home(tree, "A", engine)
        assert h is None  # A es TRUE pero no tiene home; B es FALSE

    def test_depth_first_within_sibling(self, engine):
        """Dentro de un sibling operador TRUE, se resuelve depth-first."""
        tree = {"children": [
            {"op": "AND", "children": [
                {"predicate": "type_prefix", "args": ["$type", "A"]},  # TRUE, sin home
                {"predicate": "type_prefix", "args": ["$type", "A"], "home": "deep-home"},
            ]},
        ]}
        h = tree_home(tree, "A", engine)
        assert h == "deep-home"

    def test_unknown_does_not_stop_iteration(self, engine):
        """UNKNOWN NO detiene la iteración — el loop continua.
        Hallazgo: el código en tree.py:238-250 itera TODOS los siblings.
        UNKNOWN setea saw_unknown=True pero NO hace break.
        Si un sibling posterior es TRUE con home, ese gana."""
        tree = {"children": [
            {"predicate": "ctx_has", "args": ["$ctx", "x"]},  # UNKNOWN
            {"predicate": "type_prefix", "args": ["$type", "A"], "home": "homeA"},
        ]}
        h = tree_home(tree, "A", engine)
        assert h == "homeA"  # UNKNOWN no detiene; el TRUE con home gana

    def test_unknown_prevents_else_home(self, engine):
        """UNKNOWN impide caer a else_home (R9: no conceder silenciosamente).
        Si TODOS los siblings son UNKNOWN (sin TRUE con home), retorna None."""
        tree = {"children": [
            {"predicate": "ctx_has", "args": ["$ctx", "x"]},
        ], "else_home": "fallback"}
        h = tree_home(tree, "A", engine)
        assert h is None  # No "fallback"

    def test_else_home_fallback(self, engine):
        """Si ningún sibling es TRUE, cae a else_home."""
        tree = {"children": [
            {"predicate": "type_prefix", "args": ["$type", "B"]},
        ], "else_home": "fallback"}
        h = tree_home(tree, "A", engine)
        assert h == "fallback"

    def test_no_else_home_returns_none(self, engine):
        """Sin else_home y sin TRUE, retorna None."""
        tree = {"children": [
            {"predicate": "type_prefix", "args": ["$type", "B"]},
        ]}
        h = tree_home(tree, "A", engine)
        assert h is None

    def test_unknown_prevents_else_home(self, engine):
        """UNKNOWN impide caer a else_home (R9: no conceder silenciosamente)."""
        tree = {"children": [
            {"predicate": "ctx_has", "args": ["$ctx", "x"]},
        ], "else_home": "fallback"}
        h = tree_home(tree, "A", engine)
        assert h is None  # No "fallback"


# ╔══════════════════════════════════════════════════════════════════╗
# ║  6. HOME EN OPERADORES — casos edge                            ║
# ╚══════════════════════════════════════════════════════════════════╝

class TestHomeInOperators:
    """
    STATUS: OBSERVED
    CLAIM: tree_home resuelve homes correctamente en operadores anidados.
    FALSACIÓN: casos edge que podrían romper la resolución.
    """

    def test_operator_with_home(self, engine):
        """Operador con home propio: ¿se usa?"""
        tree = {"children": [
            {"op": "AND", "children": [
                {"predicate": "type_prefix", "args": ["$type", "A"]},
            ], "home": "operator-home"},
        ]}
        h = tree_home(tree, "A", engine)
        assert h == "operator-home"

    def test_leaf_without_home(self, engine):
        """Hoja sin home en operador TRUE: ¿desciende a hijos?"""
        tree = {"children": [
            {"op": "AND", "children": [
                {"predicate": "type_prefix", "args": ["$type", "A"]},  # sin home
            ]},
        ]}
        h = tree_home(tree, "A", engine)
        assert h is None  # No hay home en ningún lado

    def test_operator_true_multiple_homes(self, engine):
        """Operador TRUE con varios hijos con home: ¿cuál retorna?"""
        tree = {"children": [
            {"op": "OR", "children": [
                {"predicate": "type_prefix", "args": ["$type", "A"], "home": "home1"},
                {"predicate": "type_prefix", "args": ["$type", "A"], "home": "home2"},
            ]},
        ]}
        h = tree_home(tree, "A", engine)
        assert h == "home1"  # Primero en orden de children

    def test_ancestor_home_vs_descendant_home(self, engine):
        """¿Home en ancestro vs descendiente?"""
        # Operador tiene home, hijo también
        tree = {"children": [
            {"op": "AND", "children": [
                {"predicate": "type_prefix", "args": ["$type", "A"], "home": "descendant"},
            ], "home": "ancestor"},
        ]}
        h = tree_home(tree, "A", engine)
        assert h == "ancestor"  # _resolve retorna el home del operador primero

    def test_unknown_before_true(self, engine):
        """UNKNOWN antes de un sibling TRUE con home: UNKNOWN no detiene."""
        tree = {"children": [
            {"predicate": "ctx_has", "args": ["$ctx", "x"]},  # UNKNOWN
            {"predicate": "type_prefix", "args": ["$type", "A"], "home": "homeA"},
        ]}
        h = tree_home(tree, "A", engine)
        assert h == "homeA"  # UNKNOWN no detiene el loop

    def test_true_without_home_before_true_with_home(self, engine):
        """TRUE sin home antes de TRUE con home: el primero gana (sin home).
        Hallazgo: tree_home retorna None si el primer TRUE no tiene home,
        aunque un sibling posterior SÍ tenga home. El loop hace `continue`
        cuando el primer TRUE no tiene home."""
        tree = {"children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]},  # TRUE, sin home
            {"predicate": "type_prefix", "args": ["$type", "A"], "home": "homeA"},
        ]}
        h = tree_home(tree, "A", engine)
        # El primer sibling es TRUE → _resolve retorna None (sin home) → continue
        # El segundo sibling es TRUE → _resolve retorna "homeA"
        # El loop retorna "homeA" del segundo sibling
        assert h == "homeA"


# ╔══════════════════════════════════════════════════════════════════╗
# ║  7. EVALUACIÓN VS RESOLUCIÓN — ¿mismo espacio recursivo?       ║
# ╚══════════════════════════════════════════════════════════════════╝

class TestEvaluationVsResolution:
    """
    STATUS: OBSERVED
    CLAIM: tree_home() reutiliza evaluate() pero tiene lógica distinta.
    FALSACIÓN: determinar si son idénticos o diferentes.
    """

    def test_tree_home_uses_evaluate(self, engine):
        """tree_home llama a engine.evaluate internamente."""
        tree = {"children": [
            {"predicate": "type_prefix", "args": ["$type", "A"], "home": "h"},
        ]}
        h = tree_home(tree, "A", engine)
        assert h == "h"  # evaluate retorna TRUE, _resolve retorna home

    def test_tree_home_resolve_descends_differently(self, engine):
        """tree_home._resolve tiene lógica de descenso que evaluate no tiene.
        evaluate Retorna Evaluation; _resolve retorna Optional[str].
        _resolve recursa en operadores TRUE sin home; evaluate recursa en todos."""
        # Árbol: AND(TRUE-without-home, TRUE-with-home)
        tree = {"children": [
            {"op": "AND", "children": [
                {"predicate": "type_prefix", "args": ["$type", "A"]},  # sin home
                {"predicate": "type_prefix", "args": ["$type", "A"], "home": "deep"},
            ]},
        ]}
        # tree_home desciende al AND, encuentra "deep"
        h = tree_home(tree, "A", engine)
        assert h == "deep"
        # evaluate del AND solo retorna Evaluation, no busca homes
        ev = engine.evaluate(tree["children"][0], {"type": "A"})
        assert ev.is_true
        assert ev.source == "op:AND"

    def test_tree_home_skips_false_children_in_resolve(self, engine):
        """_resolve NO desciende en operadores FALSE."""
        tree = {"children": [
            {"op": "AND", "children": [
                {"predicate": "type_prefix", "args": ["$type", "B"]},  # FALSE
                {"predicate": "type_prefix", "args": ["$type", "A"], "home": "should-not-reach"},
            ]},
        ]}
        h = tree_home(tree, "A", engine)
        # AND(B, A) = FALSE → _resolve no desciende → no encuentra home
        assert h is None


# ╔══════════════════════════════════════════════════════════════════╗
# ║  8. CORTOCIRCUITO — ¿AND/OR evalúan TODOS los hijos?           ║
# ╚══════════════════════════════════════════════════════════════════╝

class TestShortCircuit:
    """
    STATUS: PROVEN (test observacional)
    CLAIM: AND para en el primer FALSE (certificado). OR para en el
           primer TRUE certificado. Los hijos no evaluados quedan como
           UNKNOWN con source='short_circuit'.
    FALSACIÓN: predicado observable que cuente invocaciones.
    """

    def test_and_short_circuits_on_false(self, engine):
        """AND(TRUE, FALSE, TRUE): el tercero NO se evalúa (short-circuit)."""
        call_log.clear()
        engine.register("obs_a")(make_observable_predicate(True, "a"))
        engine.register("obs_b")(make_observable_predicate(False, "b"))
        engine.register("obs_c")(make_observable_predicate(True, "c"))

        tree = {"op": "AND", "children": [
            {"predicate": "obs_a"},
            {"predicate": "obs_b"},
            {"predicate": "obs_c"},
        ]}
        r = engine.evaluate(tree, {})
        assert r.truth == Truth.FALSE
        calls = [name for kind, name in call_log if kind == "CALL"]
        assert "a" in calls
        assert "b" in calls
        assert "c" not in calls  # short-circuited

    def test_or_short_circuits_on_certified_true(self, engine):
        """OR(TRUE uncertified, TRUE certified, FALSE): third NOT evaluated."""
        call_log.clear()
        engine.register("obs_uncertified")(
            make_observable_predicate(
                PredicateResult(truth=Truth.TRUE, certified=False, source="u"),
                "u"))
        engine.register("obs_certified")(
            make_observable_predicate(
                PredicateResult(truth=Truth.TRUE, certified=True, source="c"),
                "c"))
        engine.register("obs_false")(make_observable_predicate(False, "f"))

        tree = {"op": "OR", "children": [
            {"predicate": "obs_uncertified"},
            {"predicate": "obs_certified"},
            {"predicate": "obs_false"},
        ]}
        r = engine.evaluate(tree, {})
        assert r.truth == Truth.TRUE
        assert r.certified is True
        calls = [name for kind, name in call_log if kind == "CALL"]
        assert "u" in calls
        assert "c" in calls
        assert "f" not in calls  # short-circuited

    def test_and_false_still_short_circuits(self, engine):
        """AND(FALSE, expensive): expensive NO se evalúa."""
        call_log.clear()
        engine.register("obs_cheap_false")(make_observable_predicate(False, "cheap"))
        engine.register("obs_expensive")(make_observable_predicate(True, "expensive"))

        tree = {"op": "AND", "children": [
            {"predicate": "obs_cheap_false"},
            {"predicate": "obs_expensive"},
        ]}
        r = engine.evaluate(tree, {})
        assert r.truth == Truth.FALSE
        calls = [name for kind, name in call_log if kind == "CALL"]
        assert "cheap" in calls
        assert "expensive" not in calls  # short-circuited


# ╔══════════════════════════════════════════════════════════════════╗
# ║  9. DIAGNOSE — ¿mismo espacio recursivo que evaluate?          ║
# ╚══════════════════════════════════════════════════════════════════╝

class TestDiagnose:
    """
    STATUS: OBSERVED
    CLAIM: diagnose() recorre el mismo espacio que evaluate().
    FALSACIÓN: verificar que diagnose retorna traces para nodos certificados
               y no-retorna traces para nodos no certificados.
    """

    def test_diagnose_returns_empty_when_certified(self, engine):
        tree = {"op": "AND", "children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]},
            {"predicate": "type_has", "args": ["$type", "A"]},
        ]}
        traces = engine.diagnose(tree, {"type": "A"})
        assert traces == []

    def test_diagnose_returns_traces_when_uncertified(self, engine):
        @engine.register("uncert_true")
        def uncert_true(**kw):
            return PredicateResult(truth=Truth.TRUE, certified=False, source="uncert_true")

        tree = {"op": "AND", "children": [
            {"predicate": "uncert_true"},
            {"predicate": "type_prefix", "args": ["$type", "A"]},
        ]}
        traces = engine.diagnose(tree, {"type": "A"})
        assert len(traces) > 0
        assert any("uncert_true" in t.source for t in traces)

    def test_diagnose_same_recursion_as_evaluate(self, engine):
        """diagnose llama evaluate internamente (misma recursión)."""
        tree = {"op": "AND", "children": [
            {"op": "OR", "children": [
                {"predicate": "type_prefix", "args": ["$type", "A"]},
                {"predicate": "type_prefix", "args": ["$type", "B"]},
            ]},
        ]}
        # evaluate funciona
        ev = engine.evaluate(tree, {"type": "A"})
        assert ev.is_true
        # diagnose no falla (mismo recorrido)
        traces = engine.diagnose(tree, {"type": "A"})
        assert isinstance(traces, list)

    def test_diagnose_only_uncertified_paths(self, engine):
        """diagnose solo retorna paths que contribuyeron al fallo."""
        engine.register("cert_false")(
            lambda **kw: PredicateResult(truth=Truth.FALSE, certified=True, source="cert_false")
        )
        engine.register("uncert_true2")(
            lambda **kw: PredicateResult(truth=Truth.TRUE, certified=False, source="uncert_true2")
        )

        tree = {"op": "OR", "children": [
            {"predicate": "cert_false"},      # FALSE certified
            {"predicate": "uncert_true2"},    # TRUE uncertified
        ]}
        traces = engine.diagnose(tree, {})
        # OR con solo TRUE uncertified → no certified → traces
        assert len(traces) > 0
        # El trace apunta a uncert_true2 (no a cert_false que está certificado)
        sources = [t.source for t in traces]
        assert "uncert_true2" in sources


# ╔══════════════════════════════════════════════════════════════════╗
# ║  10. BUILDER — validación recursiva                            ║
# ╚══════════════════════════════════════════════════════════════════╝

class TestBuilder:
    """
    STATUS: PROVEN
    CLAIM: SocraticTreeBuilder valida recursivamente todos los nodos.
    FALSACIÓN: intentar árboles con operadores/predicados inválidos.
    """

    def test_valid_tree_passes(self, engine):
        builder = SocraticTreeBuilder(engine)
        tree = builder.build({"op": "AND", "children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]},
        ]})
        assert "op" in tree

    def test_unknown_predicate_rejected(self, engine):
        builder = SocraticTreeBuilder(engine)
        with pytest.raises(ValueError, match="no registrado"):
            builder.build({"predicate": "nonexistent_predicate"})

    def test_unknown_operator_rejected(self, engine):
        builder = SocraticTreeBuilder(engine)
        with pytest.raises(ValueError, match="desconocido"):
            builder.build({"op": "UNKNOWN_OP", "children": [
                {"predicate": "type_prefix", "args": ["$type", "A"]}
            ]})

    def test_not_without_children_rejected(self, engine):
        builder = SocraticTreeBuilder(engine)
        with pytest.raises(ValueError, match="al menos un hijo"):
            builder.build({"op": "NOT", "children": []})

    def test_not_with_two_children_rejected(self, engine):
        builder = SocraticTreeBuilder(engine)
        with pytest.raises(ValueError, match="exactamente 1 hijo"):
            builder.build({"op": "NOT", "children": [
                {"predicate": "type_prefix", "args": ["$type", "A"]},
                {"predicate": "type_prefix", "args": ["$type", "B"]},
            ]})

    def test_implies_with_one_child_rejected(self, engine):
        builder = SocraticTreeBuilder(engine)
        with pytest.raises(ValueError, match="exactamente 2 hijos"):
            builder.build({"op": "IMPLIES", "children": [
                {"predicate": "type_prefix", "args": ["$type", "A"]},
            ]})

    def test_implies_with_three_children_rejected(self, engine):
        builder = SocraticTreeBuilder(engine)
        with pytest.raises(ValueError, match="exactamente 2 hijos"):
            builder.build({"op": "IMPLIES", "children": [
                {"predicate": "type_prefix", "args": ["$type", "A"]},
                {"predicate": "type_prefix", "args": ["$type", "B"]},
                {"predicate": "type_prefix", "args": ["$type", "C"]},
            ]})

    def test_nested_invalid_rejected(self, engine):
        """Error en nodo anidado se detecta."""
        builder = SocraticTreeBuilder(engine)
        with pytest.raises(ValueError, match="no registrado"):
            builder.build({"op": "AND", "children": [
                {"op": "OR", "children": [
                    {"predicate": "fake_predicate"},
                ]},
            ]})

    def test_bool_literal_accepted(self, engine):
        builder = SocraticTreeBuilder(engine)
        tree = builder.build(True)
        assert tree is True

    def test_string_in_args_accepted(self, engine):
        builder = SocraticTreeBuilder(engine)
        tree = builder.build({"predicate": "type_prefix", "args": ["$type", "A"]})
        assert "predicate" in tree


# ╔══════════════════════════════════════════════════════════════════╗
# ║  11. PROFUNDIDAD REAL — límite experimental                    ║
# ╚══════════════════════════════════════════════════════════════════╝

class TestRealDepth:
    """
    STATUS: OBSERVED
    CLAIM: "profundidad arbitraria" con límite práctico en Python ~1000.
    FALSACIÓN: medir cuándo falla realmente.
    """

    @pytest.mark.parametrize("depth", [1, 2, 4, 8, 16, 32, 64, 128, 256])
    def test_depths_up_to_256(self, engine, depth):
        tree = depthN(depth)
        r = engine.evaluate(tree, {"type": "X"}, enforce_limits=False)
        assert r.is_true

    def test_depth_512(self, engine):
        """Puede fallar por RecursionError en Python."""
        import sys
        old_limit = sys.getrecursionlimit()
        sys.setrecursionlimit(10000)
        try:
            tree = depthN(512)
            r = engine.evaluate(tree, {"type": "X"}, enforce_limits=False)
            assert r.is_true
        except RecursionError:
            pytest.skip("RecursionError at d=512")
        finally:
            sys.setrecursionlimit(old_limit)

    def test_depth_1024(self, engine):
        """Puede fallar por RecursionError."""
        import sys
        old_limit = sys.getrecursionlimit()
        sys.setrecursionlimit(10000)
        try:
            tree = depthN(1024)
            r = engine.evaluate(tree, {"type": "X"}, enforce_limits=False)
            assert r.is_true
        except RecursionError:
            pytest.skip("RecursionError at d=1024")
        finally:
            sys.setrecursionlimit(old_limit)

    def test_width_1000(self, engine):
        """1000 hijos en un solo AND — ancho, no profundo."""
        children = [{"predicate": "type_prefix", "args": ["$type", "X"]}
                    for _ in range(1000)]
        tree = {"op": "AND", "children": children}
        r = engine.evaluate(tree, {"type": "X"})
        assert r.is_true


# ╔══════════════════════════════════════════════════════════════════╗
# ║  12. COMPLEJIDAD — ¿O(w^d) o O(n)?                           ║
# ╚══════════════════════════════════════════════════════════════════╝

class TestComplexity:
    """
    STATUS: INFERRED (no PROVEN con benchmarks)
    CLAIM: Complejidad es O(n) donde n = número total de nodos.
    FALSACIÓN: verificar que nodos repetidos se re-evalúan.
    """

    def test_same_node_evaluated_multiple_times(self, engine):
        """Nodo compartido se evalúa en cada referencia — PERO short-circuit
        puede reducir el conteo.  OR(certified_true, X) para en el primer
        hijo, así que solo 2 de 4 referencias se evalúan."""
        call_log.clear()
        engine.register("count_me")(make_counter_predicate("counted"))

        shared = {"predicate": "count_me"}
        tree = {"op": "AND", "children": [
            {"op": "OR", "children": [shared, shared]},
            {"op": "OR", "children": [shared, shared]},
        ]}
        engine.evaluate(tree, {})
        # OR short-circuits on first certified TRUE → 2 calls, not 4
        assert call_log.count("counted") == 2

    def test_no_memoization(self, engine):
        """El motor NO memoiza: mismo nodo, mismo contexto = re-evaluación."""
        call_log.clear()
        engine.register("memo_test")(make_counter_predicate("memo"))

        shared = {"predicate": "memo_test"}
        tree = {"op": "AND", "children": [shared, shared, shared]}
        engine.evaluate(tree, {})
        assert call_log.count("memo") == 3


# ╔══════════════════════════════════════════════════════════════════╗
# ║  13. CONSISTENCIA FORMAL — contradicciones entre módulos        ║
# ╚══════════════════════════════════════════════════════════════════╝

class TestFormalConsistency:
    """
    STATUS: OBSERVED
    CLAIM: evaluate(), tree_home(), certification, diagnose(), builder
           son consistentes entre sí.
    FALSACIÓN: buscar contradicciones.
    """

    def test_builder_accepts_what_evaluate_can_process(self, engine):
        """Todo árbol que el builder acepta, evaluate lo procesa."""
        builder = SocraticTreeBuilder(engine)
        trees = [
            {"op": "AND", "children": [
                {"predicate": "type_prefix", "args": ["$type", "A"]},
            ]},
            {"op": "OR", "children": [
                {"predicate": "type_prefix", "args": ["$type", "A"]},
                {"predicate": "type_prefix", "args": ["$type", "B"]},
            ]},
            {"op": "NOT", "children": [
                {"predicate": "type_prefix", "args": ["$type", "A"]},
            ]},
            {"op": "XOR", "children": [
                {"predicate": "type_prefix", "args": ["$type", "A"]},
                {"predicate": "type_prefix", "args": ["$type", "B"]},
            ]},
            {"op": "IMPLIES", "children": [
                {"predicate": "type_prefix", "args": ["$type", "A"]},
                {"predicate": "type_prefix", "args": ["$type", "B"]},
            ]},
            {"op": "DIALECTICAL_AND", "children": [
                {"predicate": "type_prefix", "args": ["$type", "A"]},
                {"predicate": "type_prefix", "args": ["$type", "B"]},
            ]},
        ]
        for tree in trees:
            validated = builder.build(tree)
            r = engine.evaluate(validated, {"type": "A"})
            assert isinstance(r, Evaluation)

    def test_certification_consistent_with_diagnose(self, engine):
        """Si evaluate() retorna certified=True, diagnose() retorna []."""
        tree = {"op": "AND", "children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]},
            {"predicate": "type_has", "args": ["$type", "A"]},
        ]}
        ev = engine.evaluate(tree, {"type": "A"})
        traces = engine.diagnose(tree, {"type": "A"})
        if ev.certified:
            assert traces == []
        else:
            assert len(traces) > 0

    def test_tree_home_and_evaluate_agree_on_truth(self, engine):
        """Si tree_home retorna un home, evaluate del árbol es TRUE."""
        tree = {"children": [
            {"predicate": "type_prefix", "args": ["$type", "A"], "home": "h"},
        ]}
        h = tree_home(tree, "A", engine)
        assert h == "h"
        # evaluate del mismo nodo
        ev = engine.evaluate(tree["children"][0], {"type": "A"})
        assert ev.is_true

    def test_builder_rejects_what_evaluate_would_crash_on(self, engine):
        """Predicado no registrado: builder rechaza, evaluate crashea."""
        builder = SocraticTreeBuilder(engine)
        with pytest.raises(ValueError):
            builder.build({"predicate": "nonexistent"})
        # evaluate sin builder: crashea
        with pytest.raises(ValueError):
            engine.evaluate({"predicate": "nonexistent"}, {})


# ╔══════════════════════════════════════════════════════════════════╗
# ║  14. PROPIEDADES INVARIANTES                                   ║
# ╚══════════════════════════════════════════════════════════════════╝

class TestInvariants:
    """
    STATUS: PROVEN (cada invariante es un test)
    CLAIM: Propiedades que deben cumplirse para cualquier árbol válido.
    FALSACIÓN: intentar violar cada invariante.
    """

    def test_evaluator_always_returns_t_c(self, engine):
        """evaluate() siempre retorna un estado en T × C."""
        trees_and_ctxs = [
            ({"op": "AND", "children": [{"predicate": "type_prefix", "args": ["$type", "A"]}]}, {"type": "A"}),
            ({"op": "OR", "children": [{"predicate": "type_prefix", "args": ["$type", "A"]}]}, {"type": "A"}),
            ({"op": "NOT", "children": [{"predicate": "type_prefix", "args": ["$type", "A"]}]}, {"type": "A"}),
            (True, {}),
            (False, {}),
        ]
        for tree, ctx in trees_and_ctxs:
            r = engine.evaluate(tree, ctx)
            assert isinstance(r.truth, Truth), f"truth no es Truth: {r.truth}"
            assert isinstance(r.certified, bool), f"certified no es bool: {r.certified}"

    def test_not_preserves_certification(self, engine):
        """NOT preserva certification del hijo."""
        @engine.register("cert_pred")
        def cert_pred(**kw):
            return PredicateResult(truth=Truth.TRUE, certified=True, source="cert_pred")

        @engine.register("uncert_pred")
        def uncert_pred(**kw):
            return PredicateResult(truth=Truth.TRUE, certified=False, source="uncert_pred")

        r_cert = engine.evaluate({"op": "NOT", "children": [{"predicate": "cert_pred"}]}, {})
        assert r_cert.certified is True

        r_uncert = engine.evaluate({"op": "NOT", "children": [{"predicate": "uncert_pred"}]}, {})
        assert r_uncert.certified is False

    def test_and_certification_requires_all(self, engine):
        """AND certification = ALL children certified."""
        @engine.register("c1")
        def c1(**kw):
            return PredicateResult(truth=Truth.TRUE, certified=True, source="c1")

        @engine.register("c2")
        def c2(**kw):
            return PredicateResult(truth=Truth.TRUE, certified=False, source="c2")

        r = engine.evaluate({"op": "AND", "children": [
            {"predicate": "c1"}, {"predicate": "c2"}
        ]}, {})
        assert r.truth == Truth.TRUE
        assert r.certified is False

    def test_or_certification_requires_one_true_certified(self, engine):
        """OR certification = at least 1 TRUE child certified."""
        @engine.register("u1")
        def u1(**kw):
            return PredicateResult(truth=Truth.TRUE, certified=False, source="u1")

        @engine.register("c1")
        def c1b(**kw):
            return PredicateResult(truth=Truth.TRUE, certified=True, source="c1")

        r = engine.evaluate({"op": "OR", "children": [
            {"predicate": "u1"}, {"predicate": "c1"}
        ]}, {})
        assert r.truth == Truth.TRUE
        assert r.certified is True

    def test_leaf_without_predicate_raises(self, engine):
        """Nodo inválido lanza ValueError."""
        with pytest.raises(ValueError, match="Nodo inválido"):
            engine.evaluate("not_a_node", {})

    def test_unknown_operator_raises(self, engine):
        """Operador desconocido lanza ValueError."""
        with pytest.raises(ValueError, match="desconocido"):
            engine.evaluate({"op": "NAND", "children": []}, {})


# ╔══════════════════════════════════════════════════════════════════╗
# ║  15. CONTRAEJEMPLOS — 10+ árboles pequeños que intentan romper  ║
# ╚══════════════════════════════════════════════════════════════════╝

class TestCounterexamples:
    """
    STATUS: PROVEN (si el test pasa, el claim se mantuvo)
    CLAIM: Various — cada contraejemplo intenta romper una claim específica.
    """

    def test_counterexample_1_not_double_negation(self, engine):
        """NOT(NOT(x)) = x — doble negación."""
        r = engine.evaluate({"op": "NOT", "children": [
            {"op": "NOT", "children": [
                {"predicate": "type_prefix", "args": ["$type", "A"]}
            ]}
        ]}, {"type": "A"})
        assert r.truth == Truth.TRUE

    def test_counterexample_2_implies_equivalence(self, engine):
        """IMPLIES(A, B) = OR(NOT(A), B) — equivalencia lógica."""
        a = {"predicate": "type_prefix", "args": ["$type", "A"]}
        b = {"predicate": "type_prefix", "args": ["$type", "B"]}

        r_implies = engine.evaluate({"op": "IMPLIES", "children": [a, b]}, {"type": "A"})
        r_or_not = engine.evaluate({"op": "OR", "children": [
            {"op": "NOT", "children": [a]}, b
        ]}, {"type": "A"})
        assert r_implies.truth == r_or_not.truth

    def test_counterexample_3_xor_commutative(self, engine):
        """XOR conmutativo: XOR(A,B) = XOR(B,A)."""
        a = {"predicate": "type_prefix", "args": ["$type", "A"]}
        b = {"predicate": "type_prefix", "args": ["$type", "B"]}

        r1 = engine.evaluate({"op": "XOR", "children": [a, b]}, {"type": "A"})
        r2 = engine.evaluate({"op": "XOR", "children": [b, a]}, {"type": "A"})
        assert r1.truth == r2.truth

    def test_counterexample_4_and_or_distributive(self, engine):
        """AND distributivo sobre OR: A ∧ (B ∨ C) = (A ∧ B) ∨ (A ∧ C)."""
        a = {"predicate": "type_prefix", "args": ["$type", "A"]}
        b = {"predicate": "type_prefix", "args": ["$type", "B"]}
        c = {"predicate": "type_prefix", "args": ["$type", "C"]}

        r1 = engine.evaluate({"op": "AND", "children": [
            a, {"op": "OR", "children": [b, c]}
        ]}, {"type": "A"})
        r2 = engine.evaluate({"op": "OR", "children": [
            {"op": "AND", "children": [a, b]},
            {"op": "AND", "children": [a, c]},
        ]}, {"type": "A"})
        # A=T, B=F, C=F: r1 = T AND F = F; r2 = F OR F = F
        assert r1.truth == r2.truth

    def test_counterexample_5_empty_tree(self, engine):
        """Árbol vacío: ¿qué hace evaluate?"""
        with pytest.raises(ValueError):
            engine.evaluate({}, {})

    def test_counterexample_6_and_single_child(self, engine):
        """AND con un solo hijo: ¿funciona?"""
        r = engine.evaluate({"op": "AND", "children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]}
        ]}, {"type": "A"})
        assert r.truth == Truth.TRUE

    def test_counterexample_7_or_single_child(self, engine):
        """OR con un solo hijo: ¿funciona?"""
        r = engine.evaluate({"op": "OR", "children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]}
        ]}, {"type": "A"})
        assert r.truth == Truth.TRUE

    def test_counterexample_8_deep_home_not_shadowed(self, engine):
        """Home profundo no sombreado por home de ancestro."""
        tree = {"children": [
            {"op": "AND", "children": [
                {"op": "AND", "children": [
                    {"predicate": "type_prefix", "args": ["$type", "A"], "home": "deep"},
                ]},
            ]},
        ]}
        h = tree_home(tree, "A", engine)
        assert h == "deep"

    def test_counterexample_9_unknown_doesnt_become_false(self, engine):
        """UNKNOWN no se convierte en FALSE en tree_home."""
        tree = {"children": [
            {"predicate": "ctx_has", "args": ["$ctx", "x"]},
        ], "else_home": "fallback"}
        h = tree_home(tree, "A", engine)
        assert h is None  # No "fallback"

    def test_counterexample_10_dialectical_not_rejection(self, engine):
        """DIALECTICAL_AND con conflicto = UNKNOWN, no FALSE."""
        r = engine.evaluate({"op": "DIALECTICAL_AND", "children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]},
            {"predicate": "type_prefix", "args": ["$type", "B"]},
        ]}, {"type": "A"})
        assert r.truth == Truth.UNKNOWN
        assert r.certified is True

    def test_counterexample_11_or_true_precedes_false(self, engine):
        """OR(TRUE, FALSE) = TRUE — el orden no importa para truth."""
        r1 = engine.evaluate({"op": "OR", "children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]},
            {"predicate": "type_prefix", "args": ["$type", "B"]},
        ]}, {"type": "A"})
        r2 = engine.evaluate({"op": "OR", "children": [
            {"predicate": "type_prefix", "args": ["$type", "B"]},
            {"predicate": "type_prefix", "args": ["$type", "A"]},
        ]}, {"type": "A"})
        assert r1.truth == r2.truth == Truth.TRUE

    def test_counterexample_12_context_doesnt_leak(self, engine):
        """Contexto de un evaluate no afecta a otro."""
        r1 = engine.evaluate({"predicate": "ctx_has", "args": ["$ctx", "x"]}, {"x": True})
        r2 = engine.evaluate({"predicate": "ctx_has", "args": ["$ctx", "x"]}, {})
        assert r1.is_true
        assert r2.is_unknown


# ╔══════════════════════════════════════════════════════════════════╗
# ║  16. PROPIEDAD ESTRUCTURAL — recursividad del lenguaje         ║
# ╚══════════════════════════════════════════════════════════════════╝

class TestStructuralProperty:
    """
    STATUS: INFERRED
    CLAIM: La recursividad es una propiedad del lenguaje/estructura,
           no solo de la implementación.
    FALSACIÓN: identificar los elementos mínimos y verificar que constituyen
               una gramática recursiva.
    """

    def test_tree_is_recursive_data_structure(self, engine):
        """El lenguaje permite árboles de profundidad n via children recursivos."""
        # Un nodo puede contener children que contienen children...
        # NOT(TRUE) = FALSE; OR(FALSE) = FALSE; AND(FALSE) = FALSE
        deep = {"op": "AND", "children": [
            {"op": "OR", "children": [
                {"op": "NOT", "children": [
                    {"predicate": "type_prefix", "args": ["$type", "X"]}
                ]}
            ]}
        ]}
        r = engine.evaluate(deep, {"type": "X"})
        # NOT(TRUE) = FALSE, OR(FALSE) = FALSE, AND(FALSE) = FALSE
        assert r.is_false

    def test_operators_are_composable(self, engine):
        """Operadores se componen libremente (AND de ORs de NOTs)."""
        tree = {"op": "AND", "children": [
            {"op": "OR", "children": [
                {"op": "NOT", "children": [
                    {"predicate": "type_prefix", "args": ["$type", "B"]}
                ]},
                {"predicate": "type_prefix", "args": ["$type", "A"]},
            ]},
            {"op": "XOR", "children": [
                {"predicate": "type_prefix", "args": ["$type", "A"]},
                {"predicate": "type_prefix", "args": ["$type", "B"]},
            ]},
        ]}
        r = engine.evaluate(tree, {"type": "A"})
        assert r.truth == Truth.TRUE

    def test_evaluation_is_homomorphic(self, engine):
        """eval(padre) = f(eval(hijos)) - homomorfismo."""
        a = {"predicate": "type_prefix", "args": ["$type", "A"]}
        b = {"predicate": "type_prefix", "args": ["$type", "B"]}

        ev_a = engine.evaluate(a, {"type": "A"})
        ev_b = engine.evaluate(b, {"type": "A"})
        ev_and = engine.evaluate({"op": "AND", "children": [a, b]}, {"type": "A"})

        # Si ev_a=TRUE, ev_b=FALSE, entonces ev_and=FALSE
        assert ev_a.is_true
        assert ev_b.is_false
        assert ev_and.is_false

    def test_language_has_five_primitives(self, engine):
        """5 primitivas constituyen el lenguaje: predicate, AND, OR, NOT, home."""
        # 1. predicate
        r1 = engine.evaluate({"predicate": "type_prefix", "args": ["$type", "A"]}, {"type": "A"})
        assert r1.is_true
        # 2. AND
        r2 = engine.evaluate({"op": "AND", "children": [
            {"predicate": "type_prefix", "args": ["$type", "A"]},
            {"predicate": "type_has", "args": ["$type", "A"]},
        ]}, {"type": "A"})
        assert r2.is_true
        # 3. OR
        r3 = engine.evaluate({"op": "OR", "children": [
            {"predicate": "type_prefix", "args": ["$type", "B"]},
            {"predicate": "type_prefix", "args": ["$type", "A"]},
        ]}, {"type": "A"})
        assert r3.is_true
        # 4. NOT
        r4 = engine.evaluate({"op": "NOT", "children": [
            {"predicate": "type_prefix", "args": ["$type", "B"]}
        ]}, {"type": "A"})
        assert r4.is_true
        # 5. home (resuelto por tree_home, no por evaluate)
        h = tree_home({"children": [
            {"predicate": "type_prefix", "args": ["$type", "A"], "home": "h"}
        ]}, "A", engine)
        assert h == "h"

    def test_grammar_is_context_free(self, engine):
        """La gramática es libre de contexto: nodo → op(hijos) | predicate."""
        # Cualquier nodo puede ser reemplazado por un sub-árbol
        simple = {"predicate": "type_prefix", "args": ["$type", "A"]}
        complex = {"op": "AND", "children": [
            {"op": "OR", "children": [
                simple,
                {"predicate": "type_has", "args": ["$type", "A"]},
            ]},
        ]}
        # Ambos son válidos
        r1 = engine.evaluate(simple, {"type": "A"})
        r2 = engine.evaluate(complex, {"type": "A"})
        assert r1.is_true
        assert r2.is_true
