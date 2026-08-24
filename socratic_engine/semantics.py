"""Semantic simplification for socratic trees.

Pre-processor that detects and simplifies pathological tree patterns
BEFORE evaluation. Called from socratic_evaluate after validate_tree_limits.

Patterns handled:
1. NOT chain flattening: NOT(NOT(NOT(P))) -> NOT(P) or P
2. Contradiction detection: AND(A, NOT(A)) -> FALSE
3. Tautology detection: OR(A, NOT(A)) -> TRUE
"""

from __future__ import annotations

from typing import Any


def simplify(node: Any) -> Any:
    """Simplify a tree node. Returns simplified node or a marker dict
    with ``_resolved: True`` and ``truth: bool`` if the tree can be
    resolved without evaluation."""
    if not isinstance(node, dict):
        return node

    op = node.get("op")

    # --- NOT chain flattening ---
    if op == "NOT":
        node = flatten_not_chain(node)
        op = node.get("op")  # re-read after flattening

    # --- Contradiction / Tautology ---
    if op in ("AND", "OR"):
        resolved = detect_contradiction(node)
        if resolved is not None:
            return resolved

        # Recurse into children after contradiction check
        new_children = [_resolve_marker(c) for c in
                        (simplify(c) for c in node.get("children", []))]
        node = {**node, "children": new_children}

        # Re-check after simplifying children (child may have resolved)
        resolved = detect_contradiction(node)
        if resolved is not None:
            return resolved

    return node


def _resolve_marker(child: Any) -> Any:
    """If simplify returned a _resolved marker, convert to boolean literal."""
    if isinstance(child, dict) and child.get("_resolved"):
        return child["truth"]  # True or False
    return child


# ── Pattern 1: NOT chain ──────────────────────────────────────


def flatten_not_chain(node: dict) -> dict:
    """NOT(NOT(NOT(P))) -> NOT(P) if odd depth, P if even depth."""
    depth = 0
    current = node
    while current.get("op") == "NOT":
        children = current.get("children", [])
        if len(children) != 1:
            break  # invalid NOT, let evaluator catch it
        depth += 1
        current = children[0]

    if depth <= 1:
        return node  # no simplification possible

    if depth % 2 == 0:
        return current  # even NOTs cancel out
    else:
        return {"op": "NOT", "children": [current]}  # single NOT remains


# ── Pattern 2: Contradiction / Tautology ─────────────────────


def detect_contradiction(node: dict) -> dict | None:
    """AND(A, NOT(A)) -> FALSE.  OR(A, NOT(A)) -> TRUE.
    Returns ``{"_resolved": True, "truth": bool}`` or None."""
    op = node.get("op")
    if op not in ("AND", "OR"):
        return None

    children = node.get("children", [])
    if len(children) < 2:
        return None

    # O(n^2) pairwise check — acceptable for n < 1000
    for i in range(len(children)):
        for j in range(i + 1, len(children)):
            if _is_negation_pair(children[i], children[j]):
                if op == "AND":
                    return {"_resolved": True, "truth": False}
                else:  # OR
                    return {"_resolved": True, "truth": True}

    return None


def _is_negation_pair(a: Any, b: Any) -> bool:
    """Check if a is NOT(b) or b is NOT(a), using structural equality."""
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False

    # a = NOT(b)?
    if a.get("op") == "NOT":
        a_children = a.get("children", [])
        if len(a_children) == 1 and _shallow_equal(a_children[0], b):
            return True

    # b = NOT(a)?
    if b.get("op") == "NOT":
        b_children = b.get("children", [])
        if len(b_children) == 1 and _shallow_equal(b_children[0], a):
            return True

    return False


def _shallow_equal(a: Any, b: Any) -> bool:
    """Structural equality for tree nodes (no recursion into children of children)."""
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(_shallow_equal(a[k], b[k]) for k in a.keys())
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(_shallow_equal(x, y) for x, y in zip(a, b))
    return a == b
