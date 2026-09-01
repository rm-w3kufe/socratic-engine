"""
Tests for engine_contract.py — Protocol definition and compatibility checks.
"""

import pytest
from socratic_engine import SocraticEngine, Truth
from socratic_engine.engine import Evaluation, PredicateResult
from socratic_engine.engine_contract import (
    SocraticEngineProtocol,
    EvaluationProtocol,
    check_engine_compatibility,
)


# ---------------------------------------------------------------------------
# Protocol satisfaction (structural typing)
# ---------------------------------------------------------------------------

class TestSocraticEngineProtocol:
    """SocraticEngine should satisfy the protocol structurally."""

    def test_real_engine_satisfies_protocol(self):
        """SocraticEngine is a structural subtype of SocraticEngineProtocol."""
        engine = SocraticEngine()
        assert isinstance(engine, SocraticEngineProtocol)

    def test_engine_has_evaluate(self):
        """Engine has evaluate method."""
        engine = SocraticEngine()
        assert hasattr(engine, "evaluate")
        assert callable(engine.evaluate)

    def test_engine_has_predicates(self):
        """Engine has predicates dict."""
        engine = SocraticEngine()
        assert hasattr(engine, "predicates")
        assert isinstance(engine.predicates, dict)

    def test_engine_has_register(self):
        """Engine has register decorator."""
        engine = SocraticEngine()
        assert hasattr(engine, "register")
        assert callable(engine.register)


class TestEvaluationProtocol:
    """Evaluation should satisfy the protocol structurally."""

    def test_real_evaluation_satisfies_protocol(self):
        """Evaluation is a structural subtype of EvaluationProtocol."""
        ev = Evaluation(truth=Truth.TRUE, certified=True, source="test")
        assert isinstance(ev, EvaluationProtocol)

    def test_evaluation_has_truth(self):
        """Evaluation has truth property."""
        ev = Evaluation(truth=Truth.TRUE)
        assert ev.truth == Truth.TRUE

    def test_evaluation_has_certified(self):
        """Evaluation has certified property."""
        ev = Evaluation(truth=Truth.TRUE, certified=True)
        assert ev.certified is True

    def test_evaluation_has_source(self):
        """Evaluation has source property."""
        ev = Evaluation(truth=Truth.TRUE, source="my_pred")
        assert ev.source == "my_pred"

    def test_evaluation_has_convenience(self):
        """Evaluation has is_true/is_false/is_unknown."""
        ev = Evaluation(truth=Truth.TRUE)
        assert ev.is_true is True
        assert ev.is_false is False
        assert ev.is_unknown is False


# ---------------------------------------------------------------------------
# check_engine_compatibility
# ---------------------------------------------------------------------------

class TestCheckCompatibility:
    """check_engine_compatibility should detect issues."""

    def test_real_engine_compatible(self):
        """Real SocraticEngine is compatible."""
        engine = SocraticEngine()
        result = check_engine_compatibility(engine)
        assert result["compatible"] is True
        assert result["missing"] == []

    def test_missing_evaluate(self):
        """Object without evaluate is incompatible."""

        class NoEvaluate:
            predicates = {}
            def register(self, name):
                pass

        result = check_engine_compatibility(NoEvaluate())
        assert result["compatible"] is False
        assert "evaluate" in result["missing"]

    def test_missing_predicates(self):
        """Object without predicates is incompatible."""

        class NoPredicates:
            def evaluate(self, node, ctx=None, **kw):
                pass
            def register(self, name):
                pass

        result = check_engine_compatibility(NoPredicates())
        assert result["compatible"] is False
        assert "predicates" in result["missing"]

    def test_missing_register(self):
        """Object without register is incompatible."""

        class NoRegister:
            predicates = {}
            def evaluate(self, node, ctx=None, **kw):
                pass

        result = check_engine_compatibility(NoRegister())
        assert result["compatible"] is False
        assert "register" in result["missing"]

    def test_old_engine_missing_enforce_limits(self):
        """Old engine without enforce_limits gets a warning."""

        class OldEngine:
            predicates = {}
            def register(self, name):
                pass
            def evaluate(self, node, ctx=None):
                pass

        result = check_engine_compatibility(OldEngine())
        assert result["compatible"] is True  # still compatible
        assert any("enforce_limits" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# Cross-package integration
# ---------------------------------------------------------------------------

class TestContractIntegration:
    """Verify the contract works in cross-package scenarios."""

    def test_observer_can_use_protocol(self):
        """rsi_observer pattern: accept engine as SocraticEngineProtocol."""
        engine = SocraticEngine()

        @engine.register("test_pred")
        def test_pred():
            return True

        # This is the pattern rsi_observer uses
        def observe(engine: SocraticEngineProtocol):
            result = engine.evaluate(
                {"predicate": "test_pred"},
                enforce_limits=True,
            )
            return result

        result = observe(engine)
        assert result.is_true

    def test_predicates_injection_pattern(self):
        """rsi_observer pattern: inject wrapper into predicates dict."""
        engine = SocraticEngine()

        @engine.register("original")
        def original():
            return True

        # Injection pattern (L2 wrapper)
        original_func = engine.predicates.get("original")
        assert original_func is not None

        def wrapper(*a, **kw):
            return original_func(*a, **kw)

        engine.predicates["injected"] = wrapper
        assert "injected" in engine.predicates

        # Cleanup
        del engine.predicates["injected"]
        assert "injected" not in engine.predicates

    def test_evaluate_returns_correct_type(self):
        """evaluate() returns Evaluation, which satisfies EvaluationProtocol."""
        engine = SocraticEngine()
        result = engine.evaluate(True)
        assert isinstance(result, Evaluation)
        assert isinstance(result, EvaluationProtocol)
        assert result.truth == Truth.TRUE
        assert result.certified is False
        assert result.source == "literal"


# ---------------------------------------------------------------------------
# Backward compatibility with old signatures
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    """Contract should work with engines that don't have enforce_limits."""

    def test_old_engine_works_through_contract(self):
        """An engine without enforce_limits still works via **kwargs."""
        engine = SocraticEngine()

        # Remove enforce_limits from evaluate to simulate old version
        original_eval = engine.evaluate

        def old_evaluate(node, context=None, _depth=0, _node_count=0):
            """Old evaluate without enforce_limits."""
            return original_eval(node, context)

        engine.evaluate = old_evaluate

        # Should still work (Protocol uses **kwargs)
        result = engine.evaluate(True)
        assert result.is_true
