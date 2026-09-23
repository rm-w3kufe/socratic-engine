"""Tests for computation nodes (GAP-03), tree loading, numeric args."""
from __future__ import annotations

import sys

import pytest

from socratic_engine import SocraticEngine, Truth


@pytest.fixture
def engine():
    return SocraticEngine()


def _comp(features, tree):
    return {"computation": {"features": features, "tree": tree}}


def _feat(op, args, out, const=0.0):
    return {"op": op, "args": list(args), "output_name": out,
            "constant_value": const}


def test_computation_basic_gt(engine):
    node = _comp([_feat("add", ["x", "y"], "d0")],
                 {"condition": "d0", "threshold": 1.0, "operator": "gt",
                  "left": True, "right": False})
    ev = engine.evaluate(node, {"x": 0.8, "y": 0.5})
    assert ev.is_true and ev.certified
    assert ev.source == "computation"
    assert ev.evidence["features"]["d0"] == pytest.approx(1.3)


def test_computation_chaining(engine):
    node = _comp([_feat("add", ["x", "y"], "d0"),
                  _feat("mul", ["d0", "x"], "d1")],
                 {"condition": "d1", "threshold": 1.0, "operator": "gt",
                  "left": True, "right": False})
    ev = engine.evaluate(node, {"x": 0.8, "y": 0.5})
    assert ev.evidence["features"]["d1"] == pytest.approx(1.3 * 0.8)
    assert ev.is_true


def test_computation_lt_eq_operators(engine):
    for op, thresh, ctx, exp in [
        ("lt", 1.0, {"x": 0.2}, True),
        ("lt", 0.1, {"x": 0.2}, False),
        ("eq", 0.5, {"x": 0.5}, True),
    ]:
        node = _comp([_feat("add", ["x"], "d0")],
                     {"condition": "d0", "threshold": thresh,
                      "operator": op, "left": True, "right": False})
        ev = engine.evaluate(node, ctx)
        assert ev.truth == (Truth.TRUE if exp else Truth.FALSE), op


def test_computation_unknown_op_yields_zero(engine):
    node = _comp([_feat("no_such_op_xyz", ["x"], "d0")],
                 {"condition": "d0", "threshold": -0.5, "operator": "gt",
                  "left": True, "right": False})
    ev = engine.evaluate(node, {"x": 5.0})
    assert ev.evidence["features"]["d0"] == 0.0
    assert ev.is_true  # 0.0 > -0.5


def test_computation_op_exception_yields_zero(engine):
    # sub with no inputs: a[0] IndexError inside OPERATIONS -> 0.0
    node = _comp([{"op": "sub", "args": [], "output_name": "d0"}],
                 {"condition": "d0", "threshold": 0.0, "operator": "gt",
                  "left": True, "right": False})
    ev = engine.evaluate(node, {})
    assert ev.evidence["features"]["d0"] == 0.0
    assert ev.is_false


def test_computation_non_numeric_ctx_skipped(engine):
    node = _comp([_feat("add", ["x", "y"], "d0")],
                 {"condition": "d0", "threshold": 0.0, "operator": "gt",
                  "left": True, "right": False})
    ev = engine.evaluate(node, {"x": 1.0, "y": "not-a-number",
                                "nested": {"z": 2.0}})
    # y unresolvable -> 0.0; nested dict flattened (z=2.0, unused)
    assert ev.evidence["features"]["d0"] == pytest.approx(1.0)
    assert ev.is_true


def test_computation_missing_keys_default(engine):
    ev = engine.evaluate({"computation": {}}, {"x": 1})
    assert ev.truth in (Truth.TRUE, Truth.FALSE)  # empty tree -> False


def test_genome_tree_leaf_and_bare_values(engine):
    node = _comp([], {"result": True})
    assert engine.evaluate(node, {}).is_true
    node = _comp([], {"result": False})
    assert engine.evaluate(node, {}).is_false


def test_genome_tree_unknown_operator_defaults_gt(engine):
    node = _comp([_feat("threshold", ["x"], "d0")],
                 {"condition": "d0", "threshold": 0.5,
                  "operator": "weird", "left": True, "right": False})
    ev = engine.evaluate(node, {"x": 0.9})
    assert ev.is_true  # falls back to gt: 1.0 > 0.5


def test_computation_fallback_operations_without_genome_module(engine,
                                                              monkeypatch):
    # Force the ImportError fallback: minimal OPERATIONS must still work.
    import builtins
    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "vsf_rsi.rsi_genome_v3":
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    node = _comp([_feat("add", ["x", "y"], "d0"),
                  _feat("square", ["d0"], "d1")],
                 {"condition": "d1", "threshold": 1.0, "operator": "gt",
                  "left": True, "right": False})
    ev = engine.evaluate(node, {"x": 0.8, "y": 0.5})
    assert ev.evidence["features"]["d1"] == pytest.approx(1.3 ** 2)
    assert ev.is_true


def test_numeric_predicate_three_arg_form(engine):
    ev = engine.evaluate(
        {"predicate": "gt", "args": [{"v": 0.9}, "v", 0.5]}, {})
    assert ev.is_true


def test_numeric_predicate_bad_arity_is_unknown(engine):
    # Arity violations surface as UNKNOWN+uncertified (never crash, never
    # guess) — the ValueError path inside numeric predicates.
    ev = engine.evaluate({"predicate": "gt", "args": ["v"]}, {"v": 1})
    assert ev.truth == Truth.UNKNOWN and ev.certified is False
    assert "error" in ev.evidence


def test_tree_loader_paths(tmp_path):
    from socratic_engine.tree import load_tree
    assert load_tree(tmp_path / "missing.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert load_tree(bad) is None
    good = tmp_path / "good.json"
    good.write_text('{"predicate": "ctx_has", "args": ["$ctx", "a"]}')
    assert load_tree(good)["predicate"] == "ctx_has"
    vsm = tmp_path / "t.vsm"
    vsm.write_text('socratic("T") = {\n  predicate: "ctx_has",\n'
                   '  args: ["$ctx", "a"],\n}\n')
    assert load_tree(vsm)["predicate"] == "ctx_has"


def test_tree_executor_validates_and_runs(tmp_path):
    from socratic_engine.tree import TreeExecutor
    ex = TreeExecutor(SocraticEngine())
    tree = {"predicate": "ctx_has", "args": ["$ctx", "a"]}
    out = ex.execute(tree, {"a": 1}, validate=True)
    assert out.truth == Truth.TRUE
    with pytest.raises(ValueError):
        ex.execute({"predicate": "no_such_xyz"}, {}, validate=True)
    with pytest.raises(ValueError):
        ex.execute(tmp_path / "missing.json", {})


def test_bridge_records_value_error_routing():
    from socratic_engine.multi_bridge import MultiBridge

    class ValErr:
        def query(self, domain, filt=None):
            raise ValueError("bad filter")
        def list_domains(self):
            return ["svc"]

    b = MultiBridge()
    b.add_provider("ve", ValErr(), ["svc"])
    e = SocraticEngine()
    b.register(e)
    r = e.evaluate({"predicate": "canon_query", "args": ["svc"]}, {})
    assert r.truth == Truth.UNKNOWN
    assert r.evidence["routing"]["error"] is True
