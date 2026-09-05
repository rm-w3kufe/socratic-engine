"""Tests for context predicates: ctx_has, ctx_equals, ctx_contains, ctx_not_has.

Added in v0.2.10 — these predicates enable tree-based evaluation of
context values (tool, command, file, etc.) for the VSF second-order
cybernetics pipeline.
"""
import pytest
from socratic_engine import SocraticEngine, Truth


@pytest.fixture
def engine():
    return SocraticEngine()


# ═══════════════════════════════════════════════════════════════════════════════
# ctx_equals
# ═══════════════════════════════════════════════════════════════════════════════

class TestCtxEquals:
    """ctx_equals(key, expected) — exact value comparison."""

    def test_true_match(self, engine):
        tree = {"predicate": "ctx_equals", "args": ["tool", "bash"], "inject_context": True}
        result = engine.evaluate(tree, context={"tool": "bash"})
        assert result.truth is Truth.TRUE
        assert result.certified is True

    def test_false_no_match(self, engine):
        tree = {"predicate": "ctx_equals", "args": ["tool", "bash"], "inject_context": True}
        result = engine.evaluate(tree, context={"tool": "read"})
        assert result.truth is Truth.FALSE
        assert result.certified is True

    def test_unknown_missing_key(self, engine):
        tree = {"predicate": "ctx_equals", "args": ["tool", "bash"], "inject_context": True}
        result = engine.evaluate(tree, context={"other": "value"})
        assert result.truth is Truth.UNKNOWN
        assert result.certified is False

    def test_legacy_3arg_api(self, engine):
        """3-arg API: ctx_equals($ctx, key, expected) — legacy compat."""
        tree = {"predicate": "ctx_equals", "args": ["$ctx", "tool", "bash"], "inject_context": True}
        result = engine.evaluate(tree, context={"tool": "bash"})
        assert result.truth is Truth.TRUE

    def test_wrong_arity_returns_unknown(self, engine):
        tree = {"predicate": "ctx_equals", "args": ["tool"], "inject_context": True}
        result = engine.evaluate(tree, context={"tool": "bash"})
        assert result.truth is Truth.UNKNOWN

    def test_numeric_value(self, engine):
        tree = {"predicate": "ctx_equals", "args": ["count", 42], "inject_context": True}
        result = engine.evaluate(tree, context={"count": 42})
        assert result.truth is Truth.TRUE

    def test_numeric_mismatch(self, engine):
        tree = {"predicate": "ctx_equals", "args": ["count", 42], "inject_context": True}
        result = engine.evaluate(tree, context={"count": 99})
        assert result.truth is Truth.FALSE


# ═══════════════════════════════════════════════════════════════════════════════
# ctx_contains
# ═══════════════════════════════════════════════════════════════════════════════

class TestCtxContains:
    """ctx_contains(key, substring) — substring for strings, membership for lists."""

    def test_string_contains(self, engine):
        tree = {"predicate": "ctx_contains", "args": ["command", "grep"], "inject_context": True}
        result = engine.evaluate(tree, context={"command": "grep missing file.py"})
        assert result.truth is Truth.TRUE
        assert result.certified is True

    def test_string_not_contains(self, engine):
        tree = {"predicate": "ctx_contains", "args": ["command", "grep"], "inject_context": True}
        result = engine.evaluate(tree, context={"command": "cat file.py"})
        assert result.truth is Truth.FALSE
        assert result.certified is True

    def test_list_contains(self, engine):
        tree = {"predicate": "ctx_contains", "args": ["tags", "python"], "inject_context": True}
        result = engine.evaluate(tree, context={"tags": ["python", "rust"]})
        assert result.truth is Truth.TRUE

    def test_list_not_contains(self, engine):
        tree = {"predicate": "ctx_contains", "args": ["tags", "go"], "inject_context": True}
        result = engine.evaluate(tree, context={"tags": ["python", "rust"]})
        assert result.truth is Truth.FALSE

    def test_unknown_missing_key(self, engine):
        tree = {"predicate": "ctx_contains", "args": ["command", "grep"], "inject_context": True}
        result = engine.evaluate(tree, context={"other": "value"})
        assert result.truth is Truth.UNKNOWN

    def test_legacy_3arg_api(self, engine):
        tree = {"predicate": "ctx_contains", "args": ["$ctx", "command", "grep"], "inject_context": True}
        result = engine.evaluate(tree, context={"command": "grep file"})
        assert result.truth is Truth.TRUE

    def test_empty_string_contains(self, engine):
        tree = {"predicate": "ctx_contains", "args": ["command", ""], "inject_context": True}
        result = engine.evaluate(tree, context={"command": "anything"})
        # empty substring is in everything
        assert result.truth is Truth.TRUE


# ═══════════════════════════════════════════════════════════════════════════════
# ctx_not_has
# ═══════════════════════════════════════════════════════════════════════════════

class TestCtxNotHas:
    """ctx_not_has(key) — inverse of ctx_has."""

    def test_true_when_missing(self, engine):
        tree = {"predicate": "ctx_not_has", "args": ["tool"], "inject_context": True}
        result = engine.evaluate(tree, context={"other": "value"})
        assert result.truth is Truth.TRUE
        assert result.certified is True

    def test_false_when_present(self, engine):
        tree = {"predicate": "ctx_not_has", "args": ["tool"], "inject_context": True}
        result = engine.evaluate(tree, context={"tool": "bash"})
        assert result.truth is Truth.FALSE
        assert result.certified is True

    def test_true_when_empty_string(self, engine):
        tree = {"predicate": "ctx_not_has", "args": ["tool"], "inject_context": True}
        result = engine.evaluate(tree, context={"tool": ""})
        assert result.truth is Truth.TRUE

    def test_true_when_none(self, engine):
        tree = {"predicate": "ctx_not_has", "args": ["tool"], "inject_context": True}
        result = engine.evaluate(tree, context={"tool": None})
        assert result.truth is Truth.TRUE

    def test_legacy_2arg_api(self, engine):
        tree = {"predicate": "ctx_not_has", "args": ["$ctx", "tool"], "inject_context": True}
        result = engine.evaluate(tree, context={"other": "value"})
        assert result.truth is Truth.TRUE

    def test_wrong_arity_returns_unknown(self, engine):
        tree = {"predicate": "ctx_not_has", "args": [], "inject_context": True}
        result = engine.evaluate(tree, context={"tool": "bash"})
        assert result.truth is Truth.UNKNOWN


# ═══════════════════════════════════════════════════════════════════════════════
# ctx_has (existing — regression tests)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCtxHas:
    """ctx_has(key) — existing predicate, regression coverage."""

    def test_true_when_present(self, engine):
        tree = {"predicate": "ctx_has", "args": ["tool"], "inject_context": True}
        result = engine.evaluate(tree, context={"tool": "bash"})
        assert result.truth is Truth.TRUE
        assert result.certified is True

    def test_false_when_missing(self, engine):
        tree = {"predicate": "ctx_has", "args": ["tool"], "inject_context": True}
        result = engine.evaluate(tree, context={"other": "value"})
        assert result.truth is Truth.UNKNOWN  # ctx_has returns UNKNOWN for missing
        assert result.certified is False


# ═══════════════════════════════════════════════════════════════════════════════
# Integration: AND trees with context predicates
# ═══════════════════════════════════════════════════════════════════════════════

class TestCtxIntegration:
    """Full AND trees using multiple context predicates — mirrors RSI predicates."""

    def test_bash_grep_pattern(self, engine):
        """Simulates rsi_bash_grep predicate tree."""
        tree = {
            "op": "AND",
            "children": [
                {"predicate": "ctx_has", "args": ["tool"], "inject_context": True},
                {"predicate": "ctx_equals", "args": ["tool", "bash"], "inject_context": True},
                {"predicate": "ctx_contains", "args": ["command", "grep"], "inject_context": True},
            ],
            "inject_context": True,
        }
        # Match
        result = engine.evaluate(tree, context={"tool": "bash", "command": "grep file"})
        assert result.truth is Truth.TRUE
        assert result.certified is True

        # No match (wrong tool)
        result2 = engine.evaluate(tree, context={"tool": "read", "command": "grep file"})
        assert result2.truth is Truth.FALSE

        # No match (no grep in command)
        result3 = engine.evaluate(tree, context={"tool": "bash", "command": "ls -la"})
        assert result3.truth is Truth.FALSE

    def test_all_predicates_in_and(self, engine):
        """All 4 context predicates in one AND tree."""
        tree = {
            "op": "AND",
            "children": [
                {"predicate": "ctx_has", "args": ["tool"], "inject_context": True},
                {"predicate": "ctx_equals", "args": ["tool", "bash"], "inject_context": True},
                {"predicate": "ctx_contains", "args": ["command", "rm"], "inject_context": True},
                {"predicate": "ctx_not_has", "args": ["dry_run"], "inject_context": True},
            ],
            "inject_context": True,
        }
        # Match: bash + rm + no dry_run
        result = engine.evaluate(tree, context={"tool": "bash", "command": "rm -rf /tmp"})
        assert result.truth is Truth.TRUE

        # No match: has dry_run flag
        result2 = engine.evaluate(tree, context={"tool": "bash", "command": "rm -rf /tmp", "dry_run": True})
        assert result2.truth is Truth.FALSE
