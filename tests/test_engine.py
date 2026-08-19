"""Tests del núcleo: trivaluado, certificación, trace inverso, builder."""

import pytest

from socratic_engine import (
    SocraticEngine,
    SocraticTreeBuilder,
    PredicateResult,
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

# ── KWARGS CON DICT DE DATOS: datos estructurados no son nodos ──

def test_kwargs_data_dict_is_not_a_node(engine):
    """Un dict de DATOS en kwargs (p.ej. {"id": 123}) se pasa tal cual al
    predicado — NO se evalúa como nodo lógico (regresión quickstart 2026-08-18)."""
    @engine.register("schema_valid")
    def schema_valid(data, **kw):
        from socratic_engine import PredicateResult
        if not data:
            return PredicateResult(truth=Truth.UNKNOWN, certified=False)
        ok = isinstance(data, dict) and "id" in data
        return PredicateResult(
            truth=Truth.TRUE if ok else Truth.FALSE,
            certified=True,
            evidence={"fields_checked": ["id"]},
        )

    tree = {"op": "AND", "children": [
        {"predicate": "schema_valid", "kwargs": {"data": {"id": 123}}},
    ]}
    ev = engine.evaluate(tree)
    assert ev.is_true, "dict de datos debe pasarse como valor, no evaluarse como nodo"
    assert ev.certified


def test_kwargs_nested_node_still_evaluates(engine):
    """Un dict NODO en kwargs (con 'predicate'/'op') SIGUE evaluándose."""
    @engine.register("wrapper")
    def wrapper(inner: bool, **kw):
        return inner

    tree = {"op": "AND", "children": [
        {"predicate": "wrapper", "kwargs": {
            "inner": {"predicate": "type_prefix", "args": ["$type", "VSL-"]},
        }},
    ]}
    ev = engine.evaluate(tree, {"type": "VSL-X"})
    assert ev.is_true, "nodo anidado en kwargs debe evaluarse"


# ── OPERADOR DIALÉCTICO (DIALECTICAL_AND) — v0.2.0 ──

def _mk_pred(engine, name, result):
    """Predicado determinista con truth fijo y certificación True."""
    @engine.register(name)
    def pred(**kw):
        return PredicateResult(truth=result, certified=True,
                               evidence={f"{name}_evidence": True})
    return pred


def test_dialectical_and_all_true(engine):
    _mk_pred(engine, "thesis_a", Truth.TRUE)
    _mk_pred(engine, "thesis_b", Truth.TRUE)
    tree = {"op": "DIALECTICAL_AND", "children": [
        {"predicate": "thesis_a"},
        {"predicate": "thesis_b"},
    ]}
    ev = engine.evaluate(tree)
    assert ev.is_true
    assert ev.certified
    assert not ev.metadata.get("dialectical_conflict")


def test_dialectical_and_all_false(engine):
    _mk_pred(engine, "deny_a", Truth.FALSE)
    _mk_pred(engine, "deny_b", Truth.FALSE)
    tree = {"op": "DIALECTICAL_AND", "children": [
        {"predicate": "deny_a"},
        {"predicate": "deny_b"},
    ]}
    ev = engine.evaluate(tree)
    assert ev.is_false
    assert ev.certified


def test_dialectical_and_conflict_certified_is_unknown_not_rejection(engine):
    """La contradicción certificada NO es rechazo (FALSE) ni aprobación
    (TRUE): es UNKNOWN con la tensión documentada — el nivel superior debe
    sintetizar (tesis + antítesis → síntesis)."""
    _mk_pred(engine, "thesis", Truth.TRUE)
    _mk_pred(engine, "antithesis", Truth.FALSE)
    tree = {"op": "DIALECTICAL_AND", "children": [
        {"predicate": "thesis"},
        {"predicate": "antithesis"},
    ]}
    ev = engine.evaluate(tree)
    assert ev.is_unknown, "conflicto certificado debe ser UNKNOWN, no FALSE"
    assert ev.certified, "la contradicción misma es un hecho certificado"
    assert ev.metadata.get("dialectical_conflict") is True
    assert ev.metadata["thesis"][0]["source"] == "thesis"
    assert ev.metadata["antithesis"][0]["source"] == "antithesis"


def test_dialectical_and_conflict_uncertified_is_unknown_uncertified(engine):
    """Conflicto donde un hijo NO está certificado → UNKNOWN no certificado
    (falta de evidencia, no tensión establecida)."""
    _mk_pred(engine, "thesis_c", Truth.TRUE)
    @engine.register("opinion_c")
    def opinion_c(**kw):
        return PredicateResult(truth=Truth.FALSE, certified=False)  # opinión sin evidencia
    tree = {"op": "DIALECTICAL_AND", "children": [
        {"predicate": "thesis_c"},
        {"predicate": "opinion_c"},
    ]}
    ev = engine.evaluate(tree)
    assert ev.is_unknown
    assert not ev.certified


def test_dialectical_and_conflict_diagnose_points_to_conflict_not_child(engine):
    """El diagnóstico de un conflicto certificado NO señala hijos culpables
    (sería tomar partido); la contradicción es el estado a sintetizar."""
    _mk_pred(engine, "thesis_d", Truth.TRUE)
    _mk_pred(engine, "antithesis_d", Truth.FALSE)
    tree = {"op": "DIALECTICAL_AND", "children": [
        {"predicate": "thesis_d"},
        {"predicate": "antithesis_d"},
    ]}
    ev = engine.evaluate(tree)
    traces = engine.diagnose(tree)
    assert ev.certified
    assert traces == [], "conflicto certificado no es fallo de certificación"
