"""Tests del núcleo: trivaluado, certificación, trace inverso, builder."""

import pytest

from socratic_engine import (
    SocraticEngine,
    SocraticTreeBuilder,
    Truth,
    tree_home,
    parse_socratic_block,
)


@pytest.fixture
def engine() -> SocraticEngine:
    return SocraticEngine()


# ── TRIVALUADO: UNKNOWN es tan importante como TRUE/FALSE ──

def test_trivalent_unary(engine):
    t = {"op": "AND", "children": [
        {"predicate": "type_prefix", "args": ["$type", "VSL-LANG-"]},
        {"op": "NOT", "children": [{"predicate": "type_has", "args": ["$type", "INDEX"]}]},
    ]}
    ev = engine.evaluate(t, {"type": "VSL-LANG-GATES-v1.0"})
    assert ev.is_true
    assert ev.certified, "builtins deterministas deben certificar"
    ev2 = engine.evaluate(t, {"type": "VSL-LANGUAGE-INDEX-v1.0"})
    assert ev2.is_false


def test_unknown_propagates(engine):
    @engine.register("maybe")
    def maybe(*a, **k):
        from socratic_engine import PredicateResult
        return PredicateResult(truth=Truth.UNKNOWN, certified=False, source="maybe")

    ev = engine.evaluate({"op": "AND", "children": [
        {"predicate": "type_prefix", "args": ["$type", "VSL-"]},
        {"predicate": "maybe", "args": ["x"]},
    ]}, {"type": "VSL-X"})
    assert ev.is_unknown, "AND con UNKNOWN debe ser UNKNOWN"


def test_empty_type_is_unknown_not_false(engine):
    """Sin sujeto no hay juicio (R10): type_ vacío → UNKNOWN, no FALSE."""
    ev = engine.evaluate(
        {"predicate": "type_glob", "args": ["$type", "*.vsm"]},
        {"type": ""},
    )
    assert ev.is_unknown
    assert not ev.certified


# ── CERTIFICACIÓN: evidencia estructural ≠ opinión (R10) ──

def test_llm_opinion_does_not_certify(engine):
    @engine.register("llm_judge")
    def llm_judge(question, evidence, **kwargs):
        from socratic_engine import PredicateResult
        return PredicateResult(
            truth=Truth.TRUE, certified=False,
            evidence=evidence, source="llm:gpt-4",
            metadata={"question": question, "confidence": 0.85},
        )

    ev = engine.evaluate({"predicate": "llm_judge", "kwargs": {
        "question": "¿Rompe compatibilidad?", "evidence": "cambio"}}, {})
    assert ev.is_true and not ev.certified, "LLM opina pero no certifica (R10)"


# ── TRACE INVERSO (diagnóstico) ──

def test_diagnose_points_to_uncertified_leaf(engine):
    @engine.register("llm_judge")
    def llm_judge(question, evidence, **kwargs):
        from socratic_engine import PredicateResult
        return PredicateResult(truth=Truth.TRUE, certified=False, source="llm:gpt-4")

    tree = {"op": "AND", "children": [
        {"predicate": "type_prefix", "args": ["$type", "VSL-"]},
        {"predicate": "llm_judge", "kwargs": {"question": "¿OK?", "evidence": "cambio"}},
    ]}
    diag = engine.diagnose(tree, {"type": "VSL-X"})
    assert len(diag) >= 1
    assert any("llm" in t.path[-1] or "llm" in t.source for t in diag), \
        "el trace inverso debe señalar al llm_judge como causa"


# ── BUILDER: validación estructural ──

def test_builder_accepts_valid_tree(engine):
    builder = SocraticTreeBuilder(engine)
    built = builder.build({"op": "OR", "children": [
        {"predicate": "type_prefix", "args": ["$type", "THEORY-VC-"]},
    ]})
    assert engine.evaluate(built, {"type": "THEORY-VC-01"}).is_true


def test_builder_rejects_unknown_predicate(engine):
    builder = SocraticTreeBuilder(engine)
    with pytest.raises(ValueError) as e:
        builder.build({"op": "AND", "children": [{"predicate": "no_such", "args": []}]})
    assert "no_such" in str(e.value)


def test_builder_rejects_not_with_two_children(engine):
    builder = SocraticTreeBuilder(engine)
    with pytest.raises(ValueError) as e:
        builder.build({"op": "NOT", "children": [True, False]})
    assert "NOT" in str(e.value)


# ── TREE_HOME: home del primer TRUE; UNKNOWN → '?' visible (R9) ──

def test_tree_home_first_true_wins(engine):
    t = {"op": "OR", "children": [
        {"predicate": "type_prefix", "args": ["$type", "THEORY-VC-"], "home": "s3-control"},
        {"predicate": "type_prefix", "args": ["$type", "THEORY-AP-"], "home": "s4-intelligence"},
    ]}
    assert tree_home(t, "THEORY-VC-01", engine) == "s3-control"
    assert tree_home(t, "THEORY-AP-01", engine) == "s4-intelligence"


def test_tree_home_no_match_returns_none_visible_question(engine):
    t = {"op": "OR", "children": [
        {"predicate": "type_prefix", "args": ["$type", "THEORY-VC-"], "home": "s3-control"},
    ]}
    assert tree_home(t, "THEORY-DYN-01", engine) is None, "no match → '?' visible"


def test_tree_home_unknown_not_else_silent(engine):
    """UNKNOWN en un hijo NO cae al else_home silencioso — devuelve None."""
    t = {"op": "OR", "children": [
        {"predicate": "type_prefix", "args": ["$type", "THEORY-VC-"], "home": "s3-control"},
    ], "else_home": "sandbox"}
    assert tree_home(t, "", engine) is None, "sin TYPE → UNKNOWN, no else silencioso"


def test_tree_home_descends_into_true_subtree(engine):
    """Sub-árbol TRUE sin home propio → desciende al home de su primer hijo TRUE."""
    t = {"op": "OR", "children": [
        {"op": "AND", "children": [
            {"predicate": "type_prefix", "args": ["$type", "THEORY-"]},
            {"predicate": "type_has", "args": ["$type", "VC"], "home": "s3-control"},
        ]},
    ], "else_home": "system"}
    assert tree_home(t, "THEORY-VC-01", engine) == "s3-control"


# ── PARSER VSL: árboles anidados declarados ──

def test_parse_socratic_block_nested():
    text = '''
socratic("CLASS-TREE-CLASSIFY") = {
  op: AND,
  children: [
    { predicate: "ctx_has", args: ["$ctx", "type"], },
    { op: OR, children: [
      { predicate: "type_prefix", args: ["$type", "VSL-LANG-"], home: "vsl-language" },
    ], },
  ],
  else_home: "system",
}
'''
    tree = parse_socratic_block(text)
    assert tree is not None
    assert tree["op"] == "AND"
    assert tree["children"][0]["predicate"] == "ctx_has"
    assert tree["children"][1]["op"] == "OR"
    assert tree["children"][1]["children"][0]["home"] == "vsl-language"
    assert tree["else_home"] == "system"


def test_parse_socratic_block_no_block_returns_none():
    assert parse_socratic_block("no socratic here") is None