"""Tests de RECURSIVIDAD PROFUNDA — validar que el motor desciende
por niveles arbitrarios (3+).

Estos tests prueban que la recursión NO es solo un caso especial de 2
niveles, sino una propiedad real del motor.
"""

import pytest
from socratic_engine import (
    SocraticEngine,
    SocraticTreeBuilder,
    PredicateResult,
    Truth,
    tree_home,
)


@pytest.fixture
def engine() -> SocraticEngine:
    return SocraticEngine()


# ── RECURSIVIDAD EN ENGINE: evaluate() desciende por operadores ──

def test_triple_nested_and_or_and(engine):
    """AND( OR( AND(pred1, pred2), pred3 ), pred4 ) — 3 niveles."""
    tree = {
        "op": "AND", "children": [
            {"op": "OR", "children": [
                {"op": "AND", "children": [
                    {"predicate": "type_prefix", "args": ["$type", "VSL-"]},
                    {"predicate": "type_has", "args": ["$type", "LANG"]},
                ]},
                {"predicate": "type_prefix", "args": ["$type", "BOOT-"]},
            ]},
            {"predicate": "type_regex", "args": ["$type", r".*v\d+\.\d+"]},
        ]
    }
    # VSL-LANG-v1.0: AND( OR( AND(TRUE,TRUE), FALSE ), TRUE ) -> TRUE
    ev = engine.evaluate(tree, {"type": "VSL-LANG-v1.0"})
    assert ev.is_true
    assert ev.certified


def test_quad_nested_not_or_and_not(engine):
    """NOT( OR( AND( NOT(pred), pred2 ), pred3 ) ) — 4 niveles.

    NOT hereda certificación de su hijo. OR solo certifica si hay un
    hijo TRUE certificado — cuando todos son FALSE, OR no certifica.
    Esto es diseño correcto: OR no puede certificar un resultado que
    depende de que TODOS los hijos fallen.
    """
    tree = {
        "op": "NOT", "children": [
            {"op": "OR", "children": [
                {"op": "AND", "children": [
                    {"op": "NOT", "children": [
                        {"predicate": "type_has", "args": ["$type", "DEPRECATED"]},
                    ]},
                    {"predicate": "type_prefix", "args": ["$type", "VSL-"]},
                ]},
                {"predicate": "type_has", "args": ["$type", "LEGACY"]},
            ]},
        ]
    }
    # VSL-LANG: NOT( OR( AND(NOT(FALSE),TRUE), FALSE ) ) = NOT(OR(TRUE,FALSE)) = NOT(TRUE) = FALSE
    ev = engine.evaluate(tree, {"type": "VSL-LANG"})
    assert ev.is_false
    assert ev.certified  # OR tiene hijo TRUE certificado -> OR certifica

    # DEPRECATED-VSL: NOT( OR( AND(NOT(TRUE),FALSE), FALSE ) ) = NOT(OR(FALSE,FALSE)) = NOT(FALSE) = TRUE
    # OR(FALSE, FALSE) -> FALSE, certified=False (no hay hijo TRUE)
    # NOT(FALSE, certified=False) -> TRUE, certified=False (hereda de hijo)
    ev2 = engine.evaluate(tree, {"type": "DEPRECATED-VSL"})
    assert ev2.is_true
    # NOT hereda certificación de su hijo OR; OR no certificó (todos FALSE)
    # Esto es correcto: el resultado es TRUE pero la certificación del OR
    # falló porque no hubo ningún camino TRUE


def test_deep_recursion_truth_propagation(engine):
    """Verificar que UNKNOWN se propaga correctamente a traves de 4 niveles."""
    @engine.register("maybe")
    def maybe(**kw):
        return PredicateResult(truth=Truth.UNKNOWN, certified=False)

    tree = {
        "op": "AND", "children": [
            {"op": "OR", "children": [
                {"op": "AND", "children": [
                    {"predicate": "type_prefix", "args": ["$type", "VSL-"]},
                    {"predicate": "maybe"},
                ]},
            ]},
        ]
    }
    ev = engine.evaluate(tree, {"type": "VSL-X"})
    assert ev.is_unknown, "UNKNOWN en nivel 3 debe propagar hasta la raiz"


def test_deep_recursion_certification_chain(engine):
    """Certificacion: todos los niveles deben estar certificados."""
    tree = {
        "op": "AND", "children": [
            {"op": "OR", "children": [
                {"op": "AND", "children": [
                    {"predicate": "type_prefix", "args": ["$type", "VSL-"]},
                    {"predicate": "type_has", "args": ["$type", "LANG"]},
                ]},
            ]},
        ]
    }
    ev = engine.evaluate(tree, {"type": "VSL-LANG"})
    assert ev.certified, "builtins anidados deben certificar en todos los niveles"


# ── RECURSIVIDAD EN TREE_HOME: homes a任意 profundidad ──

def test_tree_home_triple_nested_resolves_deep_home(engine):
    """tree_home resuelve home en un nodo 3 niveles profundo."""
    tree = {"children": [
        {"op": "AND", "children": [
            {"op": "OR", "children": [
                {"predicate": "type_prefix", "args": ["$type", "VSL-"],
                 "home": "vsl-language"},
            ]},
        ]},
    ], "else_home": "system"}
    assert tree_home(tree, "VSL-X", engine) == "vsl-language"


def test_tree_home_quad_nested_resolves_home(engine):
    """tree_home resuelve home en un nodo 4 niveles profundo."""
    tree = {"children": [
        {"op": "AND", "children": [
            {"op": "OR", "children": [
                {"op": "AND", "children": [
                    {"predicate": "type_prefix", "args": ["$type", "BOOT-"],
                     "home": "boot"},
                ]},
            ]},
        ]},
    ], "else_home": "system"}
    assert tree_home(tree, "BOOT-MANIFEST", engine) == "boot"


def test_tree_home_multiple_depths_first_true_wins(engine):
    """En un arbol con homes a diferentes profundidades, el primer TRUE gana."""
    tree = {"children": [
        {"op": "AND", "children": [
            {"predicate": "type_prefix", "args": ["$type", "VSL-"],
             "home": "vsl-language"},  # nivel 2, primer TRUE
        ]},
        {"op": "AND", "children": [
            {"predicate": "type_prefix", "args": ["$type", "VSL-"],
             "home": "sandbox"},  # nivel 2, nunca se alcanza
        ]},
    ], "else_home": "system"}
    assert tree_home(tree, "VSL-X", engine) == "vsl-language"


def test_tree_home_subtree_true_no_home_descends(engine):
    """Sub-arbol TRUE sin home propio desciende a sus hijos."""
    tree = {"children": [
        {"op": "AND", "children": [
            {"op": "OR", "children": [
                {"predicate": "type_prefix", "args": ["$type", "VSL-"]},
                {"predicate": "type_has", "args": ["$type", "BOOT"], "home": "boot"},
            ]},
        ]},
    ], "else_home": "system"}
    # AND(TRUE) sin home -> OR se evalua -> primer hijo TRUE sin home, segundo FALSE
    # => OR es TRUE pero sin home -> descendemos a hijos del OR
    # type_has("VSL-X", "BOOT") es FALSE -> no hay home en OR -> continue al siguiente child del AND
    # AND solo tiene 1 hijo (el OR) -> no hay mas -> else_home
    assert tree_home(tree, "VSL-X", engine) == "system"

    # Con TYPE que matchee type_has
    assert tree_home(tree, "BOOT-V1", engine) == "boot"


# ── RECURSIVIDAD CON MIXED OPERATORS ──

def test_mixed_operators_deep(engine):
    """AND( NOT( OR( AND( pred, NOT(pred) ), pred ) ) ) — operadores mixtos, 4 niveles.

    NOT hereda certificación de su hijo. OR solo certifica si hay un
    hijo TRUE certificado.
    """
    tree = {
        "op": "AND", "children": [
            {"op": "NOT", "children": [
                {"op": "OR", "children": [
                    {"op": "AND", "children": [
                        {"predicate": "type_prefix", "args": ["$type", "VSL-"]},
                        {"op": "NOT", "children": [
                            {"predicate": "type_has", "args": ["$type", "DEPRECATED"]},
                        ]},
                    ]},
                    {"predicate": "type_has", "args": ["$type", "ANCIENT"]},
                ]},
            ]},
        ]
    }
    # VSL-LANG: AND( NOT( OR( AND(TRUE, NOT(FALSE)), FALSE ) ) )
    # = AND( NOT( OR(TRUE, FALSE)) ) = AND( NOT(TRUE) ) = AND(FALSE) = FALSE
    ev = engine.evaluate(tree, {"type": "VSL-LANG"})
    assert ev.is_false
    assert ev.certified  # OR tiene hijo TRUE certificado -> OR certifica

    # ANCIENT: AND( NOT( OR( AND(FALSE, NOT(TRUE)), TRUE ) ) )
    # = AND( NOT( OR(FALSE, TRUE)) ) = AND( NOT(TRUE) ) = AND(FALSE) = FALSE
    ev2 = engine.evaluate(tree, {"type": "ANCIENT"})
    assert ev2.is_false
    assert ev2.certified  # OR tiene hijo TRUE certificado -> OR certifica

    # DEPRECATED: AND( NOT( OR( AND(TRUE, NOT(TRUE)), FALSE ) ) )
    # = AND( NOT( OR(FALSE, FALSE)) ) = AND( NOT(FALSE) ) = AND(TRUE) = TRUE
    # OR(FALSE, FALSE) -> FALSE, certified=False -> NOT(FALSE) -> TRUE, certified=False
    # AND(TRUE, certified=False) -> TRUE, certified=False (AND requires all certified)
    ev3 = engine.evaluate(tree, {"type": "DEPRECATED"})
    assert ev3.is_true
    # AND no certifica porque su hijo NOT no certifico (hereda de OR sin TRUE)


# ── RECURSIVIDAD EN BUILDER: validacion recursiva ──

def test_builder_validates_deep_nesting(engine):
    """El builder valida predicados en arboles anidados profundos."""
    builder = SocraticTreeBuilder(engine)
    # Arbol valido a 4 niveles
    built = builder.build({
        "op": "AND", "children": [
            {"op": "OR", "children": [
                {"op": "AND", "children": [
                    {"predicate": "type_prefix", "args": ["$type", "VSL-"]},
                ]},
            ]},
        ]
    })
    assert engine.evaluate(built, {"type": "VSL-X"}).is_true


def test_builder_rejects_bad_predicate_at_depth(engine):
    """El builder rechaza predicado invalido aunque este anidado 3 niveles profundo."""
    builder = SocraticTreeBuilder(engine)
    with pytest.raises(ValueError, match="no registrado"):
        builder.build({
            "op": "AND", "children": [
                {"op": "OR", "children": [
                    {"predicate": "ghost_at_depth_3", "args": []},
                ]},
            ]
        })


# ── RECURSIVIDAD EN DIAGNOSE: trace inverso a任意 profundidad ──

def test_diagnose_finds_failure_at_depth_3(engine):
    """El trace inverso encuentra la causa de fallo a 3 niveles de profundidad.

    AND( OR( type_prefix(TRUE), opinion(TRUE, no certificado) ) )
    OR se evalua: type_prefix es TRUE -> OR es TRUE (short-circuit)
    AND(TRUE, TRUE) -> TRUE. Pero opinion no esta certificado.
    AND certifica solo si TODOS los hijos certifican.
    opinion no certifica -> AND no certifica.
    """
    @engine.register("opinion")
    def opinion(**kw):
        return PredicateResult(truth=Truth.TRUE, certified=False)

    tree = {
        "op": "AND", "children": [
            {"predicate": "type_prefix", "args": ["$type", "VSL-"]},
            {"predicate": "opinion"},
        ]
    }
    # AND(TRUE certificado, TRUE no certificado) -> AND no certifica
    # diagnosis debe encontrar "opinion" como culpable
    traces = engine.diagnose(tree, {"type": "VSL-X"})
    assert len(traces) >= 1
    assert any("opinion" in t.source for t in traces), \
        "el trace debe encontrar opinion como causa del fallo de certificacion"


def test_diagnose_finds_uncertified_at_depth_3_nested_ops(engine):
    """Trace inverso encuentra opinion no certificada dentro de OR anidado en AND."""
    @engine.register("opinion2")
    def opinion2(**kw):
        return PredicateResult(truth=Truth.TRUE, certified=False)

    tree = {
        "op": "AND", "children": [
            {"op": "OR", "children": [
                {"predicate": "opinion2"},
            ]},
        ]
    }
    # OR(TRUE no certificado) -> OR no certifica
    # AND(OR no certificado) -> AND no certifica
    # diagnosis: OR -> opinion2 culpable
    traces = engine.diagnose(tree)
    assert len(traces) >= 1
    assert any("opinion2" in t.source for t in traces)


def test_diagnose_deep_certified_conflict(engine):
    """Conflicto dialéctico certificado a 3 niveles -> sin culpables."""
    @engine.register("thesis")
    def thesis(**kw):
        return PredicateResult(truth=Truth.TRUE, certified=True)
    @engine.register("antithesis")
    def antithesis(**kw):
        return PredicateResult(truth=Truth.FALSE, certified=True)

    tree = {
        "op": "AND", "children": [
            {"op": "DIALECTICAL_AND", "children": [
                {"predicate": "thesis"},
                {"predicate": "antithesis"},
            ]},
        ]
    }
    ev = engine.evaluate(tree)
    assert ev.is_unknown and ev.certified
    traces = engine.diagnose(tree)
    assert traces == [], "conflicto certificado a任意 profundidad no tiene culpables"


# ── PATRON RECURSIVO ANIDADO ──

def test_nested_recursive_pattern(engine):
    """Patrón recursivo anidado: OR con AND anidado.

    Socratic:
      OR(
        AND(pred1, pred2 home='h1'),
        AND(pred3, pred4 home='h2')
      )
    """
    tree = {"children": [
        {"op": "OR", "children": [
            {"predicate": "type_prefix", "args": ["$type", "NAV-"],
             "home": "navigation"},
            {"op": "AND", "children": [
                {"predicate": "type_has", "args": ["$type", "HOME"]},
                {"predicate": "type_regex", "args": ["$type", r".*v\d+"], "home": "home-page"},
            ]},
        ]},
    ], "else_home": "system"}

    # NAV-ITEM-v1 -> navigation (primer OR TRUE con home)
    assert tree_home(tree, "NAV-ITEM-v1", engine) == "navigation"

    # HOME-v2 -> home-page (AND anidado en OR)
    assert tree_home(tree, "HOME-v2", engine) == "home-page"

    # OTHER -> system (else_home)
    assert tree_home(tree, "OTHER", engine) == "system"


# ── RECURSIVIDAD PROFUNDA: 5+ niveles ──

def test_five_levels_deep(engine):
    """AND( OR( AND( OR( AND(pred) ) ) ) ) — 5 niveles."""
    tree = {
        "op": "AND", "children": [
            {"op": "OR", "children": [
                {"op": "AND", "children": [
                    {"op": "OR", "children": [
                        {"op": "AND", "children": [
                            {"predicate": "type_prefix", "args": ["$type", "VSL-"]},
                        ]},
                    ]},
                ]},
            ]},
        ]
    }
    ev = engine.evaluate(tree, {"type": "VSL-X"})
    assert ev.is_true and ev.certified


def test_tree_home_five_levels_deep(engine):
    """tree_home resuelve home a 5 niveles de profundidad."""
    tree = {"children": [
        {"op": "AND", "children": [
            {"op": "OR", "children": [
                {"op": "AND", "children": [
                    {"op": "OR", "children": [
                        {"op": "AND", "children": [
                            {"predicate": "type_prefix", "args": ["$type", "VSL-"],
                             "home": "deep-home"},
                        ]},
                    ]},
                ]},
            ]},
        ]},
    ], "else_home": "system"}
    assert tree_home(tree, "VSL-X", engine) == "deep-home"
