"""Benchmark del evaluador (v0.2.0).

Mide el coste de evaluar árboles de tamaño creciente y el efecto del
cache TTL en predicados costosos. Stdlib only — sin dependencias.

Uso:
    python3 benchmarks/benchmark.py [--tree-size N] [--repeat M]

Salida: tiempos por operación en microsegundos.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from socratic_engine import PredicateResult, SocraticEngine, Truth, cached


def _deep_tree(depth: int) -> dict:
    """Árbol balanceado: profundidad d → 2^d hojas de predicate."""
    if depth == 0:
        return {"predicate": "type_glob", "args": ["$type", "SPEC-*"]}
    return {"op": "AND", "children": [_deep_tree(depth - 1),
                                      _deep_tree(depth - 1)]}


def _wide_tree(leaves: int) -> dict:
    return {"op": "AND", "children": [
        {"predicate": "type_glob", "args": ["$type", "SPEC-*"]}
        for _ in range(leaves)
    ]}


def _timeit(fn, repeat: int = 100) -> float:
    """µs por llamada (mediana de `repeat` corridas)."""
    samples = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1e6)
    samples.sort()
    return samples[len(samples) // 2]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tree-size", type=int, default=10)
    ap.add_argument("--repeat", type=int, default=200)
    args = ap.parse_args()

    eng = SocraticEngine()
    ctx = {"type": "SPEC-1"}

    print(f"engine: socratic-engine (benchmark)\nrepeat: {args.repeat}\n")

    # 1. Árbol balanceado profundo
    for depth in (4, 6, 8, 10, 12):
        tree = _deep_tree(depth)
        leaves = 2 ** depth
        us = _timeit(lambda: eng.evaluate(tree, ctx), args.repeat)
        print(f"deep tree depth={depth:>2} ({leaves:>5} hojas): {us:>8.1f} µs/op")

    # 2. Árbol ancho
    for leaves in (8, 64, 256):
        tree = _wide_tree(leaves)
        us = _timeit(lambda: eng.evaluate(tree, ctx), args.repeat)
        print(f"wide tree {leaves:>4} hojas: {us:>8.1f} µs/op")

    # 3. Cache TTL en predicado costoso (simula I/O ~1ms)
    calls = []

    @eng.register("costly")
    @cached(ttl=60)
    def costly(name, **kw):
        calls.append(name)
        time.sleep(0.001)  # 1ms simulated I/O
        return PredicateResult(truth=Truth.TRUE, certified=True)

    node = {"predicate": "costly", "args": ["x"]}
    # warm-up (primera llamada real)
    eng.evaluate(node, ctx)
    calls.clear()
    t_no_cache = _timeit(lambda: (
        eng.cache.clear(), eng.evaluate(node, ctx))[1], args.repeat)
    calls.clear()
    t_cached = _timeit(lambda: eng.evaluate(node, ctx), args.repeat)
    print(f"\ncostly predicate (1ms I/O): {t_no_cache:>8.1f} µs sin cache "
          f"| {t_cached:>8.1f} µs con cache  "
          f"({t_no_cache / max(t_cached, 1e-6):.1f}x speedup)")

    # 4. Diagnóstico en árbol fallido
    fail_tree = {"op": "AND", "children": [
        {"predicate": "ctx_has", "args": ["$ctx", "missing"]},  # UNKNOWN
        {"predicate": "type_glob", "args": ["$type", "SPEC-*"]},
    ]}
    us = _timeit(lambda: eng.diagnose(fail_tree, ctx), args.repeat)
    print(f"diagnose (1 UNKNOWN leaf): {us:>8.1f} µs/op")

    return 0


if __name__ == "__main__":
    sys.exit(main())