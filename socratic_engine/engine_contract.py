"""
Engine Contract — explicit Protocol for vsf-rsi ↔ socratic-engine.

Defines the minimal public API that vsf-rsi depends on. Both packages
agree on this interface; internal changes in socratic-engine that respect
this Protocol won't break vsf-rsi.

Usage:
    from socratic_engine.engine_contract import SocraticEngineProtocol

    def my_function(engine: SocraticEngineProtocol):
        result = engine.evaluate(tree, ctx)
        # ... use result.truth, result.certified, etc.

Runtime:
    The Protocol is structural (typing.Protocol), so any object with the
    right methods/attributes satisfies it — no inheritance required.
    vsf-rsi uses feature-detection (inspect.signature) for backward compat
    with older socratic-engine versions.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Protocol, Union, runtime_checkable

from .engine import Evaluation, PredicateResult, Truth


# ---------------------------------------------------------------------------
# Predicate type (what vsf-rsi registers)
# ---------------------------------------------------------------------------

# A predicate returns bool or PredicateResult
Predicate = Callable[..., Union[bool, PredicateResult]]


# ---------------------------------------------------------------------------
# Protocol: what vsf-rsi needs from the engine
# ---------------------------------------------------------------------------

@runtime_checkable
class SocraticEngineProtocol(Protocol):
    """Minimal interface that vsf-rsi depends on.

    This is NOT a base class — it's a structural type. Any object with
    these methods/attributes satisfies the contract, regardless of its
    actual class hierarchy.
    """

    # ── Core evaluation ──────────────────────────────────────────────

    def evaluate(
        self,
        node: Any,
        context: Optional[Dict[str, Any]] = None,
        enforce_limits: bool = False,
        **kwargs: Any,
    ) -> Evaluation:
        """Evaluate a tree node against a context.

        Args:
            node: A tree node (bool, dict with 'predicate'/'op')
            context: Optional context dict for token resolution
            enforce_limits: Opt-in depth/node limits

        Returns:
            Evaluation with truth, certified, source, etc.
        """
        ...

    # ── Predicate registry ───────────────────────────────────────────

    @property
    def predicates(self) -> Dict[str, Predicate]:
        """Map of registered predicate name → callable.

        vsf-rsi accesses this directly for:
        - Checking if a predicate exists: `name in engine.predicates`
        - Getting a predicate: `engine.predicates.get(name)`
        - Injecting wrappers: `engine.predicates[name] = wrapper`
        - Deleting wrappers: `del engine.predicates[name]`
        """
        ...

    def register(self, name: str) -> Callable[[Predicate], Predicate]:
        """Decorator to register a predicate by name.

        Usage:
            @engine.register("my_pred")
            def my_pred(arg1, arg2):
                return True
        """
        ...


# ---------------------------------------------------------------------------
# Evaluation contract (what vsf-rsi reads from results)
# ---------------------------------------------------------------------------

@runtime_checkable
class EvaluationProtocol(Protocol):
    """What vsf-rsi reads from an Evaluation result."""

    @property
    def truth(self) -> Truth:
        """Trivalent logic value."""
        ...

    @property
    def certified(self) -> bool:
        """Whether truth is backed by structural evidence."""
        ...

    @property
    def source(self) -> Optional[str]:
        """Origin of the evaluation (predicate name, operator, literal)."""
        ...

    @property
    def is_true(self) -> bool:
        """Convenience: truth == TRUE."""
        ...

    @property
    def is_false(self) -> bool:
        """Convenience: truth == FALSE."""
        ...

    @property
    def context(self) -> Dict[str, Any]:
        """Context at evaluation time."""
        ...

    @property
    def metadata(self) -> Dict[str, Any]:
        """Additional data (e.g., dialectical conflict info)."""
        ...


# ---------------------------------------------------------------------------
# Helpers for backward compatibility
# ---------------------------------------------------------------------------

def check_engine_compatibility(engine: Any) -> dict:
    """Check if an engine satisfies the protocol.

    Returns:
        dict with 'compatible': bool, 'missing': list of missing attrs,
        'warnings': list of deprecation/future concerns.
    """
    missing = []
    warnings = []

    # Required methods
    if not hasattr(engine, "evaluate"):
        missing.append("evaluate")
    if not hasattr(engine, "predicates"):
        missing.append("predicates")
    if not hasattr(engine, "register"):
        missing.append("register")

    # Check predicates is a dict-like
    if hasattr(engine, "predicates"):
        if not hasattr(engine.predicates, "__contains__"):
            warnings.append("predicates missing __contains__ (in operator)")
        if not hasattr(engine.predicates, "get"):
            warnings.append("predicates missing .get()")
        if not hasattr(engine.predicates, "__setitem__"):
            warnings.append("predicates missing []= (injection won't work)")
        if not hasattr(engine.predicates, "__delitem__"):
            warnings.append("predicates missing del (cleanup won't work)")

    # Check evaluate signature accepts enforce_limits
    if hasattr(engine, "evaluate"):
        try:
            import inspect
            sig = inspect.signature(engine.evaluate)
            if "enforce_limits" not in sig.parameters:
                warnings.append("evaluate() missing enforce_limits param (old version)")
        except (ValueError, TypeError):
            warnings.append("Cannot inspect evaluate() signature")

    return {
        "compatible": len(missing) == 0,
        "missing": missing,
        "warnings": warnings,
    }


__all__ = [
    "SocraticEngineProtocol",
    "EvaluationProtocol",
    "check_engine_compatibility",
    "Predicate",
]
