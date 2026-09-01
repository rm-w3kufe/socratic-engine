"""Semantic simplification for socratic trees.

Pre-processor that detects and simplifies pathological tree patterns
BEFORE evaluation. Called from socratic_evaluate after validate_tree_limits.

Patterns handled:
1. NOT chain flattening: NOT(NOT(NOT(P))) -> NOT(P) or P
2. Contradiction detection: AND(A, NOT(A)) -> FALSE
3. Tautology detection: OR(A, NOT(A)) -> TRUE
4. Child deduplication: AND(P, P) -> AND(P), OR(P, P) -> OR(P)
5. Absorption: AND(A, OR(A, B)) -> A, OR(A, AND(A, B)) -> A
6. Deep contradiction: AND(tree, NOT(tree)) with nested structures
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

    # --- AND / OR simplifications ---
    if op in ("AND", "OR"):
        # 1. Contradiction / Tautology check (fast path)
        resolved = detect_contradiction(node)
        if resolved is not None:
            return resolved

        # 2. Simplify children recursively
        new_children = [_resolve_marker(c) for c in
                        (simplify(c) for c in node.get("children", []))]
        node = {**node, "children": new_children}

        # 3. Deduplicate children
        node = _dedup_children(node)
        if not isinstance(node, dict):
            # Dedup collapsed to a single non-dict child (e.g., boolean literal)
            return bool(node)
        op = node.get("op")  # re-read after dedup

        # 4. Absorption check
        resolved = detect_absorption(node)
        if resolved is not None:
            return resolved

        # 5. Re-check contradiction after simplification
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
                    return False
                else:  # OR
                    return True

    return None


def _is_negation_pair(a: Any, b: Any) -> bool:
    """Check if a is NOT(b) or b is NOT(a), using recursive structural equality."""
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False

    # a = NOT(b)?
    if a.get("op") == "NOT":
        a_children = a.get("children", [])
        if len(a_children) == 1 and structural_equal(a_children[0], b):
            return True

    # b = NOT(a)?
    if b.get("op") == "NOT":
        b_children = b.get("children", [])
        if len(b_children) == 1 and structural_equal(b_children[0], a):
            return True

    return False


# ── Pattern 3: Child deduplication ────────────────────────────


def _dedup_children(node: dict) -> dict:
    """Remove duplicate children. AND(P, P) -> AND(P)."""
    children = node.get("children", [])
    if len(children) <= 1:
        return node

    seen: list[Any] = []
    for child in children:
        if not any(structural_equal(child, s) for s in seen):
            seen.append(child)

    if len(seen) == len(children):
        return node  # no duplicates found

    if len(seen) == 1:
        # AND(P) -> P, OR(P) -> P
        return seen[0]

    return {**node, "children": seen}


# ── Pattern 4: Absorption ─────────────────────────────────────



def _propagate_context(parent: dict, child: Any) -> Any:
    """If parent had inject_context, propagate to child dict."""
    if isinstance(child, dict) and parent.get("inject_context"):
        return {**child, "inject_context": True}
    return child

def detect_absorption(node: dict) -> dict | None:
    """AND(A, OR(A, B)) -> A.  OR(A, AND(A, B)) -> A.
    Returns simplified node or None."""
    op = node.get("op")
    children = node.get("children", [])

    if op == "AND":
        # Check if any child is an OR containing another child
        for i, child in enumerate(children):
            if isinstance(child, dict) and child.get("op") == "OR":
                or_children = child.get("children", [])
                # Check if any sibling appears in the OR
                for j, sibling in enumerate(children):
                    if i == j:
                        continue
                    if any(structural_equal(sibling, oc) for oc in or_children):
                        # sibling is absorbed: AND(sibling, OR(sibling, ...)) -> sibling
                        return _propagate_context(node, sibling)  # absorption: AND(A, OR(A,...)) → A

    if op == "OR":
        # Check if any child is an AND containing another child
        for i, child in enumerate(children):
            if isinstance(child, dict) and child.get("op") == "AND":
                and_children = child.get("children", [])
                for j, sibling in enumerate(children):
                    if i == j:
                        continue
                    if any(structural_equal(sibling, ac) for ac in and_children):
                        return _propagate_context(node, sibling)  # absorption: AND(A, OR(A,...)) → A

    return None


def _evaluate_literal(node: Any) -> bool:
    """Best-effort truth value for absorption result.
    For predicates we can't evaluate here, return True (safe default
    — absorption is sound regardless of the actual value)."""
    if isinstance(node, bool):
        return node
    if isinstance(node, dict):
        if node.get("op") == "AND":
            return True  # conservative: don't evaluate, absorption is sound
        if node.get("op") == "OR":
            return True
    return True  # predicates: assume TRUE (safe for absorption)


# ── Structural equality (recursive) ───────────────────────────


def structural_equal(a: Any, b: Any) -> bool:
    """Recursive structural equality for tree nodes.
    Compares dicts by key-value pairs, lists by element-wise equality."""
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(structural_equal(a[k], b[k]) for k in a.keys())
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(structural_equal(x, y) for x, y in zip(a, b))
    return a == b
