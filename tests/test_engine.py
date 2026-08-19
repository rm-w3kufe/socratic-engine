"""Tests del núcleo: trivaluado, certificación, trace inverso, builder."""

import pytest

from socratic_engine import (
    SocraticEngine,
    SocraticTreeBuilder,
    PredicateCache,
    PredicateResult,
    Truth,
    cached,
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


# ── PREDICADOS PRAGMÁTICOS (v0.2.0): tendencias + feedback loops ──

def test_trend_up_monotonic(engine):
    ev = engine.evaluate({"predicate": "trend_up", "args": [[1, 2, 3, 4]]})
    assert ev.is_true and ev.certified


def test_trend_up_noise_drop_is_false(engine):
    # sube 1→4 pero cae a 0 (rango 4, caída 4 > 4/3) → ruido, no tendencia
    ev = engine.evaluate({"predicate": "trend_up", "args": [[1, 2, 3, 4, 0]]})
    assert ev.is_false and ev.certified


def test_trend_up_insufficient_is_unknown(engine):
    ev = engine.evaluate({"predicate": "trend_up", "args": [[1]]})
    assert ev.is_unknown and not ev.certified


def test_trend_up_non_numeric_is_unknown(engine):
    ev = engine.evaluate({"predicate": "trend_up", "args": [["a", "b"]]})
    assert ev.is_unknown and not ev.certified


def test_trend_up_min_delta_respected(engine):
    # 1→2 sube 1, pero min_delta=5 → FALSE certificado
    ev = engine.evaluate({"predicate": "trend_up", "args": [[1, 2], 5]})
    assert ev.is_false and ev.certified


def test_trend_down_monotonic(engine):
    ev = engine.evaluate({"predicate": "trend_down", "args": [[5, 4, 3, 2]]})
    assert ev.is_true and ev.certified


def test_feedback_loop_detected(engine):
    topo = {"A": ["B"], "B": ["C"], "C": ["A"]}
    ev = engine.evaluate({"predicate": "feedback_loop", "args": [topo, "A"]})
    assert ev.is_true and ev.certified


def test_feedback_loop_absent(engine):
    topo = {"A": ["B"], "B": ["C"], "C": []}
    ev = engine.evaluate({"predicate": "feedback_loop", "args": [topo, "A"]})
    assert ev.is_false and ev.certified


def test_feedback_loop_self_loop_not_counted(engine):
    topo = {"A": ["A"], "B": []}
    ev = engine.evaluate({"predicate": "feedback_loop", "args": [topo, "A"]})
    assert ev.is_false and ev.certified


def test_feedback_loop_invalid_topology_is_unknown(engine):
    ev = engine.evaluate({"predicate": "feedback_loop", "args": [["not", "a", "dict"], "A"]})
    assert ev.is_unknown and not ev.certified


# ── CACHE TTL PARA PREDICADOS COSTOSOS (v0.2.0) ──

def test_cached_predicate_hits_cache(engine):
    calls = []

    @engine.register("costly_probe")
    @cached(ttl=60)
    def costly_probe(name, **kw):
        calls.append(name)
        return PredicateResult(truth=Truth.TRUE, certified=True)

    ev1 = engine.evaluate({"predicate": "costly_probe", "args": ["x"]})
    ev2 = engine.evaluate({"predicate": "costly_probe", "args": ["x"]})
    assert ev1.is_true and ev2.is_true
    assert len(calls) == 1, "segunda llamada debe venir del cache"


def test_cached_predicate_distinct_args_no_shared_cache(engine):
    calls = []

    @engine.register("costly_probe2")
    @cached(ttl=60)
    def costly_probe2(name, **kw):
        calls.append(name)
        return PredicateResult(truth=Truth.TRUE, certified=True)

    engine.evaluate({"predicate": "costly_probe2", "args": ["a"]})
    engine.evaluate({"predicate": "costly_probe2", "args": ["b"]})
    assert len(calls) == 2, "args distintos → cache distinto"


def test_cached_predicate_marks_hit_as_cached(engine):
    @engine.register("costly_probe3")
    @cached(ttl=60)
    def costly_probe3(name, **kw):
        return PredicateResult(truth=Truth.TRUE, certified=True,
                               evidence={"from": "live"})

    engine.evaluate({"predicate": "costly_probe3", "args": ["x"]})
    ev = engine.evaluate({"predicate": "costly_probe3", "args": ["x"]})
    assert ev.metadata.get("cached") is True, "hit de cache debe marcarse cached=True"


def test_cached_predicate_ttl_expiry(engine, monkeypatch):
    calls = []

    @engine.register("costly_probe4")
    @cached(ttl=0.05)
    def costly_probe4(name, **kw):
        calls.append(name)
        return PredicateResult(truth=Truth.TRUE, certified=True)

    engine.evaluate({"predicate": "costly_probe4", "args": ["x"]})
    import time as _time
    _time.sleep(0.06)
    engine.evaluate({"predicate": "costly_probe4", "args": ["x"]})
    assert len(calls) == 2, "TTL expirado → re-verificación (evidencia fresca)"


def test_cached_predicate_unknown_not_cached(engine):
    calls = []

    @engine.register("costly_probe5")
    @cached(ttl=60)
    def costly_probe5(name, **kw):
        calls.append(name)
        return PredicateResult(truth=Truth.UNKNOWN, certified=False)

    engine.evaluate({"predicate": "costly_probe5", "args": ["x"]})
    engine.evaluate({"predicate": "costly_probe5", "args": ["x"]})
    assert len(calls) == 2, "UNKNOWN no se cachea — reintentar es la vía a decidir"


# ── BUILDER: paths de error (cobertura tree.py) ──

def test_builder_invalid_json_string():
    with pytest.raises(ValueError, match="JSON inválido"):
        SocraticTreeBuilder(SocraticEngine()).build("{not json")


def test_builder_non_dict_node():
    with pytest.raises(ValueError, match="esperado bool, escalar o dict"):
        SocraticTreeBuilder(SocraticEngine()).build([1, 2, 3])


def test_builder_unknown_operator():
    with pytest.raises(ValueError, match="desconocido"):
        SocraticTreeBuilder(SocraticEngine()).build({"op": "NOPE", "children": []})


def test_builder_operator_requires_children():
    with pytest.raises(ValueError, match="al menos un hijo"):
        SocraticTreeBuilder(SocraticEngine()).build({"op": "AND", "children": []})


def test_builder_implies_arity():
    eng = SocraticEngine()
    with pytest.raises(ValueError, match="exactamente 2"):
        SocraticTreeBuilder(eng).build({"op": "IMPLIES", "children": [
            {"predicate": "ctx_has", "args": ["$ctx", "a"]},
        ]})


def test_builder_unknown_predicate():
    eng = SocraticEngine()
    with pytest.raises(ValueError, match="no registrado|predicado"):
        SocraticTreeBuilder(eng).build({"predicate": "ghost", "args": []})


def test_builder_missing_predicate_and_op():
    with pytest.raises(ValueError, match="predicate.*op|op.*predicate|nodo debe"):
        SocraticTreeBuilder(SocraticEngine()).build({"foo": "bar"})


def test_builder_nested_kwargs_validated():
    eng = SocraticEngine()
    @eng.register("w")
    def w(x, **kw):
        return True
    # kwargs no-nodo con dict de datos → válido (alineado con engine: un
    # dict de datos sin 'predicate'/'op' se pasa tal cual, no se valida)
    tree = {"predicate": "w", "args": [True], "kwargs": {"data": {"id": 1}}}
    assert SocraticTreeBuilder(eng).build(tree) == tree
    # kwargs con dict NODO → sí se valida (predicado debe existir)
    with pytest.raises(ValueError, match="no registrado"):
        SocraticTreeBuilder(eng).build(
            {"predicate": "w", "args": [True],
             "kwargs": {"inner": {"predicate": "ghost", "args": []}}})


# ── COBERTURA: paths de error y edge cases del engine ──

def test_type_regex_missing_type_unknown(engine):
    ev = engine.evaluate({"predicate": "type_regex", "args": ["", "SPEC-.*"]})
    assert ev.is_unknown and not ev.certified


def test_type_regex_invalid_pattern_false_uncertified(engine):
    ev = engine.evaluate({"predicate": "type_regex", "args": ['SPEC-1', '([']})
    assert ev.is_false and not ev.certified


def test_type_regex_match_true(engine):
    ev = engine.evaluate({"predicate": "type_regex", "args": ["SPEC-42", r"SPEC-\d+"]})
    assert ev.is_true and ev.certified


def test_doc_has_status_present(engine):
    doc = {"statuses": ["validated", "pending"], "name": "x"}
    ev = engine.evaluate({"predicate": "doc_has_status", "args": [doc, "validated"]})
    assert ev.is_true and ev.certified


def test_doc_has_status_absent(engine):
    doc = {"statuses": ["validated"], "name": "x"}
    ev = engine.evaluate({"predicate": "doc_has_status", "args": [doc, "pending"]})
    assert ev.is_false and ev.certified


def test_not_requires_exactly_one_child(engine):
    with pytest.raises(ValueError, match="NOT"):
        engine.evaluate({"op": "NOT", "children": [
            {"predicate": "ctx_has", "args": ["$ctx", "a"]},
            {"predicate": "ctx_has", "args": ["$ctx", "b"]},
        ]})


def test_implies_requires_two_children(engine):
    with pytest.raises(ValueError, match="IMPLIES"):
        engine.evaluate({"op": "IMPLIES", "children": [
            {"predicate": "ctx_has", "args": ["$ctx", "a"]},
        ]})


def test_implies_semantics():
    eng = SocraticEngine()
    @eng.register("mk")
    def mk(truth_name, **kw):
        t = {"TRUE": Truth.TRUE, "FALSE": Truth.FALSE,
             "UNKNOWN": Truth.UNKNOWN}[truth_name]
        return PredicateResult(truth=t, certified=(t != Truth.UNKNOWN))
    def impl(a, b):
        return eng.evaluate({"op": "IMPLIES", "children": [
            {"predicate": "mk", "args": [a]},
            {"predicate": "mk", "args": [b]},
        ]}).truth
    assert impl("FALSE", "FALSE") == Truth.TRUE  # ex falso quodlibet
    assert impl("TRUE", "TRUE") == Truth.TRUE
    assert impl("TRUE", "FALSE") == Truth.FALSE
    assert impl("UNKNOWN", "TRUE") == Truth.TRUE
    assert impl("UNKNOWN", "FALSE") == Truth.UNKNOWN


def test_xor_semantics():
    eng = SocraticEngine()
    @eng.register("mkx")
    def mkx(truth_name, **kw):
        t = {"TRUE": Truth.TRUE, "FALSE": Truth.FALSE,
             "UNKNOWN": Truth.UNKNOWN}[truth_name]
        return PredicateResult(truth=t, certified=(t != Truth.UNKNOWN))
    def xr(a, b):
        return eng.evaluate({"op": "XOR", "children": [
            {"predicate": "mkx", "args": [a]},
            {"predicate": "mkx", "args": [b]},
        ]}).truth
    assert xr("TRUE", "FALSE") == Truth.TRUE
    assert xr("TRUE", "TRUE") == Truth.FALSE
    assert xr("FALSE", "FALSE") == Truth.FALSE
    assert xr("UNKNOWN", "TRUE") == Truth.UNKNOWN


def test_unknown_operator(engine):
    with pytest.raises(ValueError, match="Operador no implementado|desconocido"):
        engine.evaluate({"op": "FOO", "children": [
            {"predicate": "ctx_has", "args": ["$ctx", "a"]}]})


def test_inject_context(engine):
    @engine.register("sees_ctx")
    def sees_ctx(_context, **kw):
        return PredicateResult(
            truth=Truth.TRUE if _context.get("type") == "SPEC-1" else Truth.FALSE,
            certified=True)
    ev = engine.evaluate({"predicate": "sees_ctx", "inject_context": True},
                         {"type": "SPEC-1"})
    assert ev.is_true and ev.certified


def test_predicate_returns_non_bool_non_result(engine):
    @engine.register("bad_pred")
    def bad_pred(**kw):
        return "string"
    with pytest.raises(TypeError, match="bool o PredicateResult"):
        engine.evaluate({"predicate": "bad_pred"})


def test_cached_non_serializable_args_no_cache(engine):
    calls = []
    @engine.register("nonser")
    @cached(ttl=60)
    def nonser(obj, **kw):
        calls.append(1)
        return PredicateResult(truth=Truth.TRUE, certified=True)
    class Weird:  # no serializable
        pass
    engine.evaluate({"predicate": "nonser", "args": [Weird()]})
    engine.evaluate({"predicate": "nonser", "args": [Weird()]})
    assert len(calls) == 2  # args no serializables → sin cache


def test_failure_trace_str():
    from socratic_engine import FailureTrace
    t = FailureTrace(path=["op:AND", "predicate:x"], source="x",
                     truth=Truth.UNKNOWN, certified=False,
                     evidence=None, reason="evidencia insuficiente")
    s = str(t)
    assert "✗" in s and "op:AND" in s and "predicate:x" in s


# ── COBERTURA: _identify_guilty_children paths restantes ──

def test_implies_diagnose_ante_false_no_guilt():
    eng = SocraticEngine()
    @eng.register("mkf")
    def mkf(val, **kw):
        t = {"T": Truth.TRUE, "F": Truth.FALSE}[val]
        return PredicateResult(truth=t, certified=True)
    # IMPLIES: antecedente FALSE → TRUE automático, sin culpables
    tree = {"op": "IMPLIES", "children": [
        {"predicate": "mkf", "args": ["F"]},
        {"predicate": "mkf", "args": ["T"]},
    ]}
    ev = eng.evaluate(tree)
    assert ev.is_true and ev.certified
    assert eng.diagnose(tree) == []


def test_implies_diagnose_uncertified_consequent_guilty():
    eng = SocraticEngine()
    @eng.register("mkc")
    def mkc(val, **kw):
        t = {"T": Truth.TRUE, "F": Truth.FALSE, "U": Truth.UNKNOWN}[val]
        return PredicateResult(truth=t, certified=(t != Truth.UNKNOWN))
    @eng.register("opinion")
    def opinion(**kw):
        return PredicateResult(truth=Truth.TRUE, certified=False)
    # consecuente = opinión (no certificada) → culpable
    tree = {"op": "IMPLIES", "children": [
        {"predicate": "mkc", "args": ["T"]},
        {"predicate": "opinion"},
    ]}
    ev = eng.evaluate(tree)
    assert not ev.certified
    traces = eng.diagnose(tree)
    assert any("opinion" in t.source or "opinion" in str(t) for t in traces)


def test_implies_diagnose_uncertified_antecedent_guilty():
    eng = SocraticEngine()
    @eng.register("mka")
    def mka(val, **kw):
        t = {"T": Truth.TRUE, "F": Truth.FALSE, "U": Truth.UNKNOWN}[val]
        return PredicateResult(truth=t, certified=(t != Truth.UNKNOWN))
    @eng.register("opinion2")
    def opinion2(**kw):
        return PredicateResult(truth=Truth.TRUE, certified=False)
    # antecedente = opinión no certificada, consecuente certificado → ante culpable
    tree = {"op": "IMPLIES", "children": [
        {"predicate": "opinion2"},
        {"predicate": "mka", "args": ["T"]},
    ]}
    ev = eng.evaluate(tree)
    assert not ev.certified
    traces = eng.diagnose(tree)
    assert any("opinion2" in t.source or "opinion2" in str(t) for t in traces)


def test_xor_diagnose_uncertified_children():
    eng = SocraticEngine()
    @eng.register("mkx2")
    def mkx2(val, **kw):
        t = {"T": Truth.TRUE, "F": Truth.FALSE, "U": Truth.UNKNOWN}[val]
        return PredicateResult(truth=t, certified=(t != Truth.UNKNOWN))
    @eng.register("opinion3")
    def opinion3(**kw):
        return PredicateResult(truth=Truth.TRUE, certified=False)
    tree = {"op": "XOR", "children": [
        {"predicate": "mkx2", "args": ["T"]},
        {"predicate": "opinion3"},
    ]}
    ev = eng.evaluate(tree)
    assert not ev.certified
    traces = eng.diagnose(tree)
    assert len(traces) >= 1  # al menos el hijo no certificado


def test_unknown_operator_diagnose_fallback():
    eng = SocraticEngine()
    # operador desconocido en un nodo que no es predicate/op válido
    # el engine lanza ValueError al evaluar, pero _identify_guilty_children
    # con op desconocido → fallback a hijos no certificados (probado vía
    # un árbol con source="op:GHOST" no ocurre en la práctica; cubrimos el
    # fallback con un nodo operator válido cuyo source es op:DIALECTICAL_AND
    # ya cubierto). Aquí probamos que evaluate con op inválido falla:
    with pytest.raises(ValueError):
        eng.evaluate({"op": "GHOST", "children": [
            {"predicate": "ctx_has", "args": ["$ctx", "a"]}]})


# ── COBERTURA: parseador VSL y tree_home ──

def test_parse_vsl_string_keys_and_arrays():
    from socratic_engine.tree import parse_socratic_block
    text = '''socratic("N") = {
      op: "AND",
      children: [
        { predicate: "ctx_has", args: ["$ctx", "type"], home: "a" },
      ],
      else_home: "b",
    }'''
    obj = parse_socratic_block(text)
    assert obj["op"] == "AND"
    assert obj["children"][0]["predicate"] == "ctx_has"
    assert obj["children"][0]["home"] == "a"
    assert obj["else_home"] == "b"


def test_parse_vsl_quoted_values_with_spaces():
    from socratic_engine.tree import parse_socratic_block
    text = 'socratic("N") = { predicate: "inject_ctx", args: ["hello world", "x"] }'
    obj = parse_socratic_block(text)
    assert obj["args"][0] == "hello world"


def test_parse_vsl_int_and_bool_values():
    from socratic_engine.tree import parse_socratic_block
    text = 'socratic("N") = { predicate: "n", kwargs: { limit: 5, verbose: true, flag: false } }'
    obj = parse_socratic_block(text)
    assert obj["kwargs"] == {"limit": 5, "verbose": True, "flag": False}


def test_parse_socratic_no_block_none():
    from socratic_engine.tree import parse_socratic_block
    assert parse_socratic_block("no socratic here") is None
    assert parse_socratic_block('other("x") = {}') is None  # sin "socratic("
    assert parse_socratic_block("socratic sin formato valido") is None


def test_parse_vsl_list_value():
    from socratic_engine.tree import parse_socratic_block
    text = 'socratic("N") = { predicate: "in", args: [["a", "b"], "a"] }'
    obj = parse_socratic_block(text)
    assert obj["args"][0] == ["a", "b"]


def test_tree_home_none_tree_and_unknown_routing():
    from socratic_engine.tree import tree_home
    eng = SocraticEngine()
    # árbol None → None
    assert tree_home(None, "SPEC-1", eng) is None
    # child UNKNOWN → None (no conceder silenciosamente)
    @eng.register("unk_pred")
    def unk_pred(**kw):
        return PredicateResult(truth=Truth.UNKNOWN, certified=False)
    tree = {"children": [{"predicate": "unk_pred", "home": "a"}], "else_home": "b"}
    assert tree_home(tree, "SPEC-1", eng) is None


def test_tree_home_descends_into_subtree():
    from socratic_engine.tree import tree_home
    eng = SocraticEngine()
    @eng.register("t")
    def t(which, **kw):
        return PredicateResult(truth=Truth.TRUE if which == "yes" else Truth.FALSE,
                               certified=True)
    # op TRUE sin home → descender al primer hijo TRUE con home
    tree = {"children": [
        {"op": "AND", "children": [
            {"predicate": "t", "args": ["yes"], "home": "deep"},
            {"predicate": "t", "args": ["yes"]},
        ]},
    ], "else_home": "b"}
    assert tree_home(tree, "SPEC-1", eng) == "deep"


def test_tree_home_else_home_when_no_true():
    from socratic_engine.tree import tree_home
    eng = SocraticEngine()
    @eng.register("no")
    def no(**kw):
        return PredicateResult(truth=Truth.FALSE, certified=True)
    tree = {"children": [{"predicate": "no", "home": "a"}], "else_home": "b"}
    assert tree_home(tree, "SPEC-1", eng) == "b"


def test_tree_home_exception_safe():
    from socratic_engine.tree import tree_home
    eng = SocraticEngine()
    # predicado que lanza ValueError en evaluate → se ignora el hijo
    tree = {"children": [{"predicate": "does_not_exist", "home": "a"}], "else_home": "b"}
    assert tree_home(tree, "SPEC-1", eng) == "b"


# ── COBERTURA: edge cases trend / feedback_loop / cache.clear ──

def test_trend_up_noise_drop_returns_false(engine):
    # serie con caída > 1/3 del rango → ruido, no tendencia → FALSE certificado
    ev = engine.evaluate({"predicate": "trend_up", "args": [[1, 5, 1, 5]]})
    assert ev.is_false and ev.certified


def test_trend_up_insufficient_unknown(engine):
    ev = engine.evaluate({"predicate": "trend_up", "args": [[1]]})
    assert ev.is_unknown and not ev.certified


def test_trend_up_non_numeric_unknown(engine):
    ev = engine.evaluate({"predicate": "trend_up", "args": [["a", "b"]]})
    assert ev.is_unknown and not ev.certified


def test_trend_down_non_numeric_unknown(engine):
    ev = engine.evaluate({"predicate": "trend_down", "args": [["x"]]})
    assert ev.is_unknown and not ev.certified


def test_trend_down_noise_rise_returns_false(engine):
    ev = engine.evaluate({"predicate": "trend_down", "args": [[5, 1, 5, 1]]})
    assert ev.is_false and ev.certified


def test_feedback_loop_self_loop_not_counted(engine):
    # self-loop no es ciclo de feedback (longitud mínima 2)
    ev = engine.evaluate({"predicate": "feedback_loop",
                          "args": [{"a": ["a"]}, "a"]})
    assert ev.is_false and ev.certified


def test_cache_clear(engine):
    calls = []
    @engine.register("cnt")
    @cached(ttl=60)
    def cnt(**kw):
        calls.append(1)
        return PredicateResult(truth=Truth.TRUE, certified=True)
    engine.evaluate({"predicate": "cnt"})
    engine.evaluate({"predicate": "cnt"})
    assert len(calls) == 1
    engine.cache.clear()
    engine.evaluate({"predicate": "cnt"})
    assert len(calls) == 2


def test_cached_args_not_serializable_fallback(engine):
    # objeto no serializable (sin __str__ usable) → sin cache, llama directo
    class Unserializable:
        def __str__(self):
            raise TypeError("no se puede serializar")
    calls = []
    @engine.register("nser2")
    @cached(ttl=60)
    def nser2(**kw):
        calls.append(1)
        return PredicateResult(truth=Truth.TRUE, certified=True)
    engine.evaluate({"predicate": "nser2", "kwargs": {"obj": Unserializable()}})
    engine.evaluate({"predicate": "nser2", "kwargs": {"obj": Unserializable()}})
    assert len(calls) == 2


# ── COBERTURA FINAL: operators, diagnose, tree_home, parser ──

def test_dialectical_and_with_unknown_child_uncertified(engine):
    # DIALECTICAL_AND con hijo UNKNOWN → UNKNOWN no certificado (655)
    @engine.register("u")
    def u(**kw):
        return PredicateResult(truth=Truth.UNKNOWN, certified=False)
    ev = engine.evaluate({"op": "DIALECTICAL_AND", "children": [
        {"predicate": "u"},
        {"predicate": "ctx_has", "args": ["$ctx", "type"]},
    ]})
    assert ev.is_unknown and not ev.certified


def test_evaluate_invalid_node_raises(engine):
    with pytest.raises(ValueError, match="Nodo inválido"):
        engine.evaluate(42)
    with pytest.raises(ValueError, match="Nodo inválido"):
        engine.evaluate("literal")


def test_find_failure_traces_operator_without_op_source(engine):
    # nodo operador cuyo source NO empieza con "op:" → fallback: todos los
    # hijos no-certificados son sospechosos (816)
    from socratic_engine import find_failure_traces
    @engine.register("cert_true")
    def cert_true(**kw):
        return PredicateResult(truth=Truth.TRUE, certified=True)
    @engine.register("uncert_true")
    def uncert_true(**kw):
        return PredicateResult(truth=Truth.TRUE, certified=False)
    # árbol: AND con un hijo no certificado
    ev = engine.evaluate({"op": "AND", "children": [
        {"predicate": "cert_true"},
        {"predicate": "uncert_true"},
    ]})
    assert not ev.certified
    traces = find_failure_traces(ev)
    assert any("uncert_true" in t.source or "uncert_true" in str(t) for t in traces)


def test_leaf_failure_reason_false(engine):
    from socratic_engine import find_failure_traces
    @engine.register("f_leaf")
    def f_leaf(**kw):
        return PredicateResult(truth=Truth.FALSE, certified=False)
    ev = engine.evaluate({"predicate": "f_leaf"})
    traces = find_failure_traces(ev)
    assert any("retornó FALSE" in t.reason for t in traces)


def test_dialectical_guilty_conflict_certified_no_guilt(engine):
    # conflicto dialéctico certificado → NO hay hijos culpables (863-865)
    @engine.register("ct")
    def ct(**kw):
        return PredicateResult(truth=Truth.TRUE, certified=True)
    @engine.register("cf")
    def cf(**kw):
        return PredicateResult(truth=Truth.FALSE, certified=True)
    tree = {"op": "DIALECTICAL_AND", "children": [
        {"predicate": "ct"},
        {"predicate": "cf"},
    ]}
    ev = engine.evaluate(tree)
    assert ev.is_unknown and ev.certified
    assert engine.diagnose(tree) == []


def test_dialectical_guilty_conflict_uncertified_children(engine):
    # conflicto con un hijo NO certificado → culpables = hijos no certificados (866)
    @engine.register("ct2")
    def ct2(**kw):
        return PredicateResult(truth=Truth.TRUE, certified=True)
    @engine.register("uf2")
    def uf2(**kw):
        return PredicateResult(truth=Truth.FALSE, certified=False)
    tree = {"op": "DIALECTICAL_AND", "children": [
        {"predicate": "ct2"},
        {"predicate": "uf2"},
    ]}
    ev = engine.evaluate(tree)
    assert not ev.certified
    traces = engine.diagnose(tree)
    assert any("uf2" in t.source or "uf2" in str(t) for t in traces)


def test_or_guilty_true_uncertified(engine):
    # OR: no hay TRUE certificado, hay TRUE no certificado → culpables = TRUE uncertified (872-876)
    @engine.register("tf")
    def tf(**kw):
        return PredicateResult(truth=Truth.TRUE, certified=False)
    tree = {"op": "OR", "children": [{"predicate": "tf"}]}
    ev = engine.evaluate(tree)
    assert not ev.certified
    traces = engine.diagnose(tree)
    assert len(traces) >= 1


def test_not_guilty_uncertified_child(engine):
    # NOT: hijo no certificado → culpable (882)
    @engine.register("nt")
    def nt(**kw):
        return PredicateResult(truth=Truth.TRUE, certified=False)
    tree = {"op": "NOT", "children": [{"predicate": "nt"}]}
    ev = engine.evaluate(tree)
    assert not ev.certified
    traces = engine.diagnose(tree)
    assert len(traces) >= 1


def test_implies_guilty_wrong_arity(engine):
    # IMPLIES con arity != 2 → culpables = hijos no certificados (886)
    @engine.register("it")
    def it(**kw):
        return PredicateResult(truth=Truth.TRUE, certified=True)
    tree = {"op": "IMPLIES", "children": [
        {"predicate": "it"},
        {"predicate": "it"},
        {"predicate": "it"},
    ]}
    # evaluate lanza por arity inválido → no evaluamos, solo confirmamos que
    # el guard de arity de _evaluate_operator es el que protege
    with pytest.raises(ValueError, match="IMPLIES"):
        engine.evaluate(tree)


def test_xor_guilty_uncertified(engine):
    # XOR: hijo no certificado → culpable (903)
    @engine.register("xt")
    def xt(**kw):
        return PredicateResult(truth=Truth.TRUE, certified=False)
    tree = {"op": "XOR", "children": [{"predicate": "xt"}]}
    ev = engine.evaluate(tree)
    assert not ev.certified
    traces = engine.diagnose(tree)
    assert len(traces) >= 1


# ── COBERTURA FINAL 2: huecos dirigidos ──

def test_type_has_empty_unknown(engine):
    ev = engine.evaluate({"predicate": "type_has", "args": ["", "token"]})
    assert ev.is_unknown and not ev.certified


def test_trend_down_non_numeric_two_elements(engine):
    ev = engine.evaluate({"predicate": "trend_down", "args": [["a", "b"]]})
    assert ev.is_unknown and not ev.certified


def test_trend_down_min_delta_not_met(engine):
    # caída 2 < min_delta 5 → FALSE certificado (420)
    ev = engine.evaluate({"predicate": "trend_down", "args": [[10, 8], 5]})
    assert ev.is_false and ev.certified


def test_feedback_loop_seen_path_skip(engine):
    # grafo con ciclo compartido: el camino (node, nxt) ya visto → continue (474)
    # a → b → a  y  a → c → a: el segundo par a→b ya fue visto
    ev = engine.evaluate({"predicate": "feedback_loop",
                          "args": [{"a": ["b", "c"], "b": ["a"], "c": ["a"]}, "a"]})
    assert ev.is_true and ev.certified


def test_evaluate_literal_true(engine):
    ev = engine.evaluate(True)
    assert ev.is_true and not ev.certified
    ev = engine.evaluate(False)
    assert ev.is_false and not ev.certified


def test_find_failure_traces_returns_empty_for_certified(engine):
    from socratic_engine import find_failure_traces
    @engine.register("ok")
    def ok(**kw):
        return PredicateResult(truth=Truth.TRUE, certified=True)
    ev = engine.evaluate({"predicate": "ok"})
    assert find_failure_traces(ev) == []


def test_tree_home_subtree_true_no_home_continue(engine):
    # op TRUE sin home y sin hijos con home → continue, no return
    from socratic_engine.tree import tree_home
    @engine.register("yes")
    def yes(**kw):
        return PredicateResult(truth=Truth.TRUE, certified=True)
    tree = {"children": [
        {"op": "AND", "children": [{"predicate": "yes"}]},
    ], "else_home": "b"}
    assert tree_home(tree, "SPEC-1", engine) == "b"


def test_tree_home_resolve_non_dict_none(engine):
    from socratic_engine.tree import tree_home
    # _resolve con nodo no-dict → None (220)
    tree = {"children": [42], "else_home": "b"}
    assert tree_home(tree, "SPEC-1", engine) == "b"


def test_tree_home_child_exception_continue(engine):
    from socratic_engine.tree import tree_home
    # hijo con predicado inexistente lanza ValueError → continue (225-226)
    tree = {"children": [
        {"predicate": "ghost_pred", "home": "a"},
        {"predicate": "ctx_has", "args": ["$ctx", "type"], "home": "c"},
    ], "else_home": "b"}
    assert tree_home(tree, "SPEC-1", engine) == "c"


# ── COBERTURA: parser VSL restante ──

def test_parse_vsl_dict_key_quoted_after_comma():
    # dict con key string entre comillas dentro de lista (123-127, 136)
    from socratic_engine.tree import parse_socratic_block
    text = 'socratic("N") = { predicate: "p", kwargs: { "key with space": 1, x: 2 } }'
    obj = parse_socratic_block(text)
    assert obj["kwargs"] == {"key with space": 1, "x": 2}


def test_parse_vsl_nested_dict_with_quoted_key():
    from socratic_engine.tree import parse_socratic_block
    text = 'socratic("N") = { predicate: "p", kwargs: { meta: { "inner": "v", "arr": [1, 2, 3] } } }'
    obj = parse_socratic_block(text)
    assert obj["kwargs"]["meta"]["inner"] == "v"
    assert obj["kwargs"]["meta"]["arr"] == [1, 2, 3]


def test_parse_vsl_array_break_at_end():
    # array sin cierre explícito antes de fin de input (150)
    from socratic_engine.tree import parse_socratic_block
    text = 'socratic("N") = { predicate: "p", args: [1, 2'
    obj = parse_socratic_block(text)
    assert obj["args"] == [1, 2]


def test_parse_vsl_float_bare_word():
    # bare word que no es int → word (word en el parser)
    from socratic_engine.tree import parse_socratic_block
    text = 'socratic("N") = { predicate: p, args: [abc] }'
    obj = parse_socratic_block(text)
    assert obj["predicate"] == "p"
    assert obj["args"] == ["abc"]


def test_parse_socratic_block_no_regex_match():
    from socratic_engine.tree import parse_socratic_block
    # "socratic(" presente pero sin formato "NAME) = {" → None (194/198)
    assert parse_socratic_block("socratic( x ) = {") is None
    assert parse_socratic_block("socratic(NAME) without equals") is None


def test_parse_vsl_value_bare_dict_after_body():
    # body empieza con { pero obj no dict → None
    from socratic_engine.tree import parse_socratic_block
    assert parse_socratic_block('socratic("N") = [1, 2]') is None


# ── COBERTURA: arista duplicada en feedback_loop (474) ──

def test_feedback_loop_duplicate_edge_skip(engine):
    # el MISMO par (node, nxt) aparece 2 veces → continue en seen_paths (474)
    ev = engine.evaluate({"predicate": "feedback_loop",
                          "args": [{"a": ["b", "b"], "b": ["a"]}, "a"]})
    assert ev.is_true and ev.certified


def test_implies_arity_wrong_raises_before_guilty(engine):
    # IMPLIES arity != 2: evaluate lanza en _evaluate_operator — el guard de
    # arity en _identify_guilty_children (886) es inalcanzable vía flujo normal
    with pytest.raises(ValueError, match="IMPLIES"):
        engine.evaluate({"op": "IMPLIES", "children": [
            {"predicate": "ctx_has", "args": ["$ctx", "a"]},
            {"predicate": "ctx_has", "args": ["$ctx", "b"]},
            {"predicate": "ctx_has", "args": ["$ctx", "c"]},
        ]})


# ── COBERTURA FINAL tree.py: parser VSL y tree_home ──

def test_parse_vsl_dict_no_close():
    from socratic_engine.tree import _parse_vsl_value
    # espacio final → el while de skip avanza al final → break (117) + 107
    v, i = _parse_vsl_value('{ a: 1 ', 0)
    assert v == {"a": 1} and i == len('{ a: 1 ')


def test_parse_vsl_no_spaces_keyword():
    from socratic_engine.tree import _parse_vsl_value
    v, i = _parse_vsl_value('{a:1}', 0)     # 136: palabra clave sin espacios
    assert v == {"a": 1} and i == 5


def test_parse_vsl_array_no_close():
    from socratic_engine.tree import _parse_vsl_value
    v, i = _parse_vsl_value('[1, 2 ', 0)    # 150: fin de input en array con espacio
    assert v == [1, 2]


def test_tree_home_resolve_exception_returns_none(engine):
    from socratic_engine.tree import tree_home
    # _resolve con predicado que lanza ValueError → return None (225-226)
    @engine.register("boom")
    def boom(**kw):
        raise ValueError("fallo interno")
    tree = {"children": [
        {"op": "AND", "children": [{"predicate": "boom", "home": "a"}]},
        {"predicate": "ctx_has", "args": ["$ctx", "type"], "home": "c"},
    ], "else_home": "b"}
    # op TRUE lanza en _resolve → None, sigue al siguiente child
    assert tree_home(tree, "SPEC-1", engine) == "c"


def test_tree_home_subtree_returns_first_home(engine):
    from socratic_engine.tree import tree_home
    @engine.register("tr")
    def tr(val, **kw):
        return PredicateResult(truth=Truth.TRUE if val == "y" else Truth.FALSE,
                               certified=True)
    tree = {"children": [
        {"op": "OR", "children": [
            {"predicate": "tr", "args": ["n"], "home": "no"},
            {"predicate": "tr", "args": ["y"], "home": "yes"},
        ]},
    ], "else_home": "b"}
    assert tree_home(tree, "SPEC-1", engine) == "yes"


def test_tree_home_child_unknown_skips_and_no_concede(engine):
    from socratic_engine.tree import tree_home
    @engine.register("unk")
    def unk(**kw):
        return PredicateResult(truth=Truth.UNKNOWN, certified=False)
    @engine.register("fls")
    def fls(**kw):
        return PredicateResult(truth=Truth.FALSE, certified=True)
    tree = {"children": [
        {"predicate": "fls", "home": "a"},
        {"predicate": "unk", "home": "b"},
    ], "else_home": "c"}
    # UNKNOWN presente (aunque ningún TRUE) → None (R9: no conceder silenciosamente)
    assert tree_home(tree, "SPEC-1", engine) is None


# ── COBERTURA: últimos 3 del parser VSL (107, 136, 198) ──

def test_parse_vsl_empty_input():
    from socratic_engine.tree import _parse_vsl_value
    v, i = _parse_vsl_value("", 0)      # 107: entrada vacía
    assert v is None and i == 0
    v, i = _parse_vsl_value("   ", 0)   # 107: solo espacios
    assert v is None and i == 3


def test_parse_vsl_word_key_then_colon_direct():
    from socratic_engine.tree import _parse_vsl_value
    # palabra clave seguida directamente de ':' sin espacio (136: i += 1 tras ':')
    v, i = _parse_vsl_value("{a:1}", 0)
    assert v == {"a": 1} and i == 5


def test_parse_socratic_block_non_dict_body():
    from socratic_engine.tree import parse_socratic_block
    # el regex exige '{' al final de socratic("N") = — el body SIEMPRE empieza
    # con '{', pero si el parse falla y devuelve no-dict... cubrimos el guard
    # 198: para forzarlo necesitamos que _parse_vsl_value devuelva no-dict,
    # lo cual no ocurre con '{' inicial. El guard es defensivo.
    # Probamos el comportamiento observable: un bloque socratic sin '{'
    # después de '=' → el regex no matchea → None (194)
    assert parse_socratic_block('socratic("N") = hello') is None


def test_parse_vsl_spaces_before_colon():
    from socratic_engine.tree import _parse_vsl_value
    # espacios después de la key antes del ':' → while de espacios (L136)
    v, i = _parse_vsl_value('{a :1}', 0)
    assert v == {"a": 1} and i == 6


# ── COBERTURA: OR UNKNOWN/FALSE, find_failure_traces operator, leaf UNKNOWN ──

def test_or_with_unknown_returns_unknown(engine):
    @engine.register("ou")
    def ou(**kw):
        return PredicateResult(truth=Truth.UNKNOWN, certified=False)
    ev = engine.evaluate({"op": "OR", "children": [
        {"predicate": "ou"},
        {"predicate": "ctx_has", "args": ["$ctx", "type"]},
    ]})
    assert ev.is_unknown and not ev.certified


def test_or_all_false_returns_false(engine):
    @engine.register("of")
    def of(**kw):
        return PredicateResult(truth=Truth.FALSE, certified=True)
    ev = engine.evaluate({"op": "OR", "children": [
        {"predicate": "of"},
        {"predicate": "of"},
    ]})
    assert ev.is_false
    # OR solo certifica con TRUE certificado; todos FALSE → no certificado
    assert not ev.certified


def test_find_failure_traces_operator_without_guilty_children(engine):
    # operador no certificado cuyos hijos no producen traces → FailureTrace
    # del operador mismo (825): OR con un hijo UNKNOWN certificado=False y
    # otro FALSE certificado=False — ambos sin reason de "culpa"
    from socratic_engine import find_failure_traces
    @engine.register("uu")
    def uu(**kw):
        return PredicateResult(truth=Truth.UNKNOWN, certified=False)
    @engine.register("ff")
    def ff(**kw):
        return PredicateResult(truth=Truth.FALSE, certified=False)
    ev = engine.evaluate({"op": "OR", "children": [
        {"predicate": "uu"},
        {"predicate": "ff"},
    ]})
    traces = find_failure_traces(ev)
    assert len(traces) >= 1
    assert any("OR" in t.source or "OR" in str(t) for t in traces)


def test_leaf_failure_reason_unknown(engine):
    from socratic_engine import find_failure_traces
    @engine.register("unk_leaf")
    def unk_leaf(**kw):
        return PredicateResult(truth=Truth.UNKNOWN, certified=False)
    ev = engine.evaluate({"predicate": "unk_leaf"})
    traces = find_failure_traces(ev)
    assert any("UNKNOWN" in t.reason for t in traces)


def test_or_all_uncertified_guilty(engine):
    # OR: todos FALSE/UNKNOWN no-certificados → todos culpables (878)
    @engine.register("ouf")
    def ouf(**kw):
        return PredicateResult(truth=Truth.FALSE, certified=False)
    tree = {"op": "OR", "children": [
        {"predicate": "ouf"},
        {"predicate": "ouf"},
    ]}
    ev = engine.evaluate(tree)
    assert not ev.certified
    traces = engine.diagnose(tree)
    assert len(traces) >= 1
