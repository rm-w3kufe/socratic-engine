"""
Regression tests for enforce_limits bypass bugs.

Bug 1: _evaluate_predicate._maybe_eval called self.evaluate(v, ctx) without
       forwarding enforce_limits/_depth/_limit_counter. A deep tree hidden in
       predicate args would bypass limits and cause RecursionError.

Bug 2: _evaluate_operator/_evaluate_short_circuit passed the same _node_count
       to each child (by value), not the accumulated count. A wide tree (many
       siblings) would bypass MAX_NODES because each branch restarted the count.

Fix: _TreeLimitCounter (mutable, shared by reference) replaces _node_count: int.
"""

import pytest
from socratic_engine import SocraticEngine, Truth
from socratic_engine.engine import _TreeLimitCounter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_wide_tree(n_children: int) -> dict:
    """AND with n_children literal children."""
    return {
        "op": "AND",
        "children": [True] * n_children,
    }


def _make_deep_tree(depth: int) -> dict:
    """Nested AND nodes, each with one child, creating a chain of given depth."""
    tree: dict = {"predicate": "leaf"}
    for _ in range(depth):
        tree = {"op": "AND", "children": [tree]}
    return tree


def _make_predicate_arg_tree(depth: int) -> dict:
    """Predicate whose arg is a deeply nested tree (Bug 1 vector)."""
    inner = {"predicate": "leaf"}
    for _ in range(depth):
        inner = {"op": "AND", "children": [inner]}
    return {
        "predicate": "check",
        "args": [inner],
    }


def _registered_engine() -> SocraticEngine:
    """Engine with check + leaf predicates registered via decorator."""
    engine = SocraticEngine()

    @engine.register("check")
    def _check(*a, **kw):
        return True

    @engine.register("leaf")
    def _leaf():
        return True

    return engine


# ---------------------------------------------------------------------------
# Bug 1: deep tree in predicate args bypasses limits
# ---------------------------------------------------------------------------

class TestBypass1_PredicateArgDepth:
    """_maybe_eval must forward enforce_limits to nested args."""

    def test_deep_arg_blocked_with_enforce(self):
        """A 200-level deep tree in a predicate arg must be caught."""
        engine = _registered_engine()
        tree = _make_predicate_arg_tree(200)
        with pytest.raises(ValueError, match="depth"):
            engine.evaluate(tree, enforce_limits=True)

    def test_deep_arg_allowed_without_enforce(self):
        """Without enforce_limits, deep args should not raise."""
        engine = _registered_engine()
        tree = _make_predicate_arg_tree(200)
        result = engine.evaluate(tree, enforce_limits=False)
        assert result.is_true

    def test_predicate_arg_node_count_accumulates(self):
        """Nodes in predicate args count toward MAX_NODES (use wide arg, not deep)."""
        engine = _registered_engine()
        # Wide arg: AND with 10000 True children = 10001 nodes in the arg alone
        wide_arg = {"op": "AND", "children": [True] * 10000}
        tree = {"predicate": "check", "args": [wide_arg]}
        with pytest.raises(ValueError, match="nodes"):
            engine.evaluate(tree, enforce_limits=True)


# ---------------------------------------------------------------------------
# Bug 2: wide sibling tree bypasses MAX_NODES
# ---------------------------------------------------------------------------

class TestBypass2_SiblingNodeCount:
    """Node count must accumulate across siblings, not restart per child."""

    def test_wide_and_blocked(self):
        """AND with 10001 children must hit MAX_NODES."""
        engine = SocraticEngine()
        tree = _make_wide_tree(10001)
        with pytest.raises(ValueError, match="nodes"):
            engine.evaluate(tree, enforce_limits=True)

    def test_wide_and_allowed_under_limit(self):
        """AND with 9999 children should pass."""
        engine = SocraticEngine()
        tree = _make_wide_tree(9999)
        result = engine.evaluate(tree, enforce_limits=True)
        assert result.is_true

    def test_wide_or_blocked(self):
        """OR with 10001 children must hit MAX_NODES."""
        engine = SocraticEngine()
        tree = {"op": "OR", "children": [False] * 10001}
        with pytest.raises(ValueError, match="nodes"):
            engine.evaluate(tree, enforce_limits=True)

    def test_wide_nand_blocked(self):
        """XOR (non-short-circuit) with 10001 children must hit MAX_NODES."""
        engine = SocraticEngine()
        tree = {"op": "XOR", "children": [True] * 10001}
        with pytest.raises(ValueError, match="nodes"):
            engine.evaluate(tree, enforce_limits=True)


# ---------------------------------------------------------------------------
# Combined: deep + wide
# ---------------------------------------------------------------------------

class TestEnforceLimitsCombined:
    """Mixed depth and breadth scenarios."""

    def test_deep_wide_tree_blocked(self):
        """AND containing wide subtrees in each child."""
        engine = _registered_engine()
        # 10 children, each AND with 1100 True children = 10 * 1101 = 11010 + 1 root
        wide_child = {"op": "AND", "children": [True] * 1100}
        tree = {"op": "AND", "children": [wide_child] * 10}
        with pytest.raises(ValueError, match="nodes"):
            engine.evaluate(tree, enforce_limits=True)

    def test_counter_shared_across_methods(self):
        """Verify _TreeLimitCounter is shared by reference across evaluate calls."""
        counter = _TreeLimitCounter(0)
        engine = SocraticEngine()
        tree = _make_wide_tree(5)
        engine.evaluate(tree, enforce_limits=True, _limit_counter=counter)
        # 1 root AND + 5 children = 6 nodes
        assert counter.count == 6

    def test_counter_increments_correctly(self):
        """Counter should not double-count nodes."""
        counter = _TreeLimitCounter(0)
        engine = SocraticEngine()
        tree = {"op": "AND", "children": [True, True]}
        engine.evaluate(tree, enforce_limits=True, _limit_counter=counter)
        assert counter.count == 3

    def test_no_enforce_no_counter(self):
        """Without enforce_limits, no counter is created and no limits apply."""
        engine = SocraticEngine()
        tree = _make_wide_tree(50000)
        result = engine.evaluate(tree, enforce_limits=False)
        assert result.is_true
