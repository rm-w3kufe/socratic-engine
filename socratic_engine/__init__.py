"""
socratic_engine — motor socrático recursivo con semántica epistemológica.

Externalized epistemic scaffolding for AI agents. Recursive boolean
certification trees.

El motor evalúa árboles booleanos recursivos (AND/OR/NOT/XOR/IMPLIES) con
lógica TRIVALUADA (TRUE/FALSE/UNKNOWN), certificación de evidencia
(certified: evidencia estructural ≠ opinión) y rastro completo de
razonamiento (explain()/diagnose()).

Agnóstico: no contiene lógica de dominio. Los predicates registrados son
deterministas (type_glob/type_prefix/type_regex/type_has/ctx_has); un LLM
u otro motor puede registrar los suyos, pero solo la evidencia estructural
certifica (R10: el LLM opina, no certifica).

Uso:
    from socratic_engine import SocraticEngine, Truth, TreeExecutor
    eng = SocraticEngine()
    executor = TreeExecutor(eng)
    result = executor.execute({"op": "AND", "children": [
        {"predicate": "type_prefix", "args": ["$type", "VSL-LANG-"]},
    ]}, {"type": "VSL-LANG-GATES-v1.0"})
    # result.truth == Truth.TRUE, result.certified == True

CLI:
    socratic-engine eval-tree <tree.vsm|tree.json> [--context <json>] [--doc-type <TYPE>]
"""

from .engine import (
    Evaluation,
    FailureTrace,
    PredicateCache,
    PredicateResult,
    Predicate,
    SocraticEngine,
    Truth,
    cached,
    find_failure_traces,
)
from .tree import (
    SocraticTreeBuilder,
    TreeExecutor,
    load_tree,
    parse_socratic_block,
    tree_home,
)

__all__ = [
    "Evaluation",
    "FailureTrace",
    "Predicate",
    "PredicateResult",
    "SocraticEngine",
    "SocraticTreeBuilder",
    "TreeExecutor",
    "Truth",
    "find_failure_traces",
    "load_tree",
    "parse_socratic_block",
    "tree_home",
]

__version__ = "0.2.6"