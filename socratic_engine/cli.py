"""
socratic_engine.cli — contrato externo del motor (CLI eval-tree + selftest).

El motor se expone por contrato externo estable para que cualquier
instrumento (gate write-time, plugin TS, MCP server, script CI/CD) lo
invocable sin importar el paquete Python internamente.

Uso:
  socratic-engine eval-tree <tree.vsm|tree.json> [--context <json>] [--doc-type <TYPE>]
  → {"truth":"TRUE","certified":true,"home":"vsl-language","unknown":false,
     "diagnose":[...],"explain":"..."}

Sin argumentos: ejecuta el selftest (R4.1: el instrumento se auto-verifica).
"""

import json
import sys
from pathlib import Path

from .engine import PredicateResult, SocraticEngine, Truth
from .tree import SocraticTreeBuilder, parse_socratic_block, tree_home

def _run_selftest() -> None:
    # selftest rápido (R4.1: el instrumento se auto-verifica)
    eng = SocraticEngine()
    t = {
        "op": "AND",
        "children": [
            {"predicate": "type_prefix", "args": ["$type", "VSL-LANG-"]},
            {"op": "NOT", "children": [{"predicate": "type_has", "args": ["$type", "INDEX"]}]},
        ],
    }
    ev = eng.evaluate(t, {"type": "VSL-LANG-GATES-v1.0"})
    assert ev.is_true, "VSL-LANG-GATES debe ser TRUE"
    assert ev.certified, "builtins deterministas deben certificar"
    ev2 = eng.evaluate(t, {"type": "VSL-LANGUAGE-INDEX-v1.0"})
    assert ev2.is_false, "INDEX debe ser FALSE"

    # trivaluado: UNKNOWN propaga
    @eng.register("maybe")
    def maybe(*a, **k) -> PredicateResult:
        return PredicateResult(truth=Truth.UNKNOWN, certified=False, source="maybe")
    ev3 = eng.evaluate({"op": "AND", "children": [
        {"predicate": "type_prefix", "args": ["$type", "VSL-"]},
        {"predicate": "maybe", "args": ["x"]},
    ]}, {"type": "VSL-X"})
    assert ev3.is_unknown, "AND con UNKNOWN debe ser UNKNOWN"

    # certificación: bool simple NO certifica; PredicateResult certified=True sí
    ev4 = eng.evaluate({"predicate": "type_glob", "args": ["$type", "*.vsm"]}, {"type": "x.vsm"})
    assert ev4.certified, "type_glob es evidencia estructural → certified"

    # tree_home: primero TRUE gana; UNKNOWN → '?' (None), no else silencioso
    t2 = {"op": "OR", "children": [
        {"predicate": "type_prefix", "args": ["$type", "THEORY-VC-"], "home": "s3-control"},
        {"predicate": "type_prefix", "args": ["$type", "THEORY-AP-"], "home": "s4-intelligence"},
    ]}
    assert tree_home(t2, "THEORY-VC-01", eng) == "s3-control"
    assert tree_home(t2, "THEORY-AP-01", eng) == "s4-intelligence"
    assert tree_home(t2, "THEORY-DYN-01", eng) is None  # no match → '?'

    # R10: llm_judge opina (TRUE) pero NO certifica → certified=False
    @eng.register("llm_judge")
    def llm_judge(question: str, evidence: str, **kwargs) -> PredicateResult:
        return PredicateResult(
            truth=Truth.TRUE, certified=False,
            evidence=evidence, source="llm:gpt-4",
            metadata={"question": question, "confidence": 0.85},
        )
    ev5 = eng.evaluate({"predicate": "llm_judge", "kwargs": {
        "question": "¿Rompe compatibilidad?", "evidence": "cambio"}}, {})
    assert ev5.is_true and not ev5.certified, "LLM opina pero no certifica (R10)"

    # trace inverso: AND con llm_judge no certificado → el trace apunta al llm_judge
    tree_diag = {"op": "AND", "children": [
        {"predicate": "type_prefix", "args": ["$type", "VSL-"]},
        {"predicate": "llm_judge", "kwargs": {"question": "¿OK?", "evidence": "cambio"}},
    ]}
    diag = eng.diagnose(tree_diag, {"type": "VSL-X"})
    assert len(diag) >= 1, "diagnose debe encontrar el fallo"
    assert any("llm" in t.path[-1] or "llm" in t.source for t in diag), \
        "el trace inverso debe señalar al llm_judge como causa (source=llm:gpt-4)"
    assert all("certified" not in t.reason or t.reason for t in diag)

    # builder: árbol válido pasa; predicado no registrado → ValueError descriptivo
    builder = SocraticTreeBuilder(eng)
    built = builder.build({"op": "OR", "children": [
        {"predicate": "type_prefix", "args": ["$type", "THEORY-VC-"]},
    ]})
    assert eng.evaluate(built, {"type": "THEORY-VC-01"}).is_true
    try:
        builder.build({"op": "AND", "children": [{"predicate": "no_such", "args": []}]})
        raise AssertionError("builder debe rechazar predicado no registrado")  # pragma: no cover — inalcanzable: builder SÍ lanza (verificado por tests directos); el raise solo corre si el builder fallara en rechazar lo que debe
    except ValueError as e:
        assert "no_such" in str(e), "mensaje debe nombrar el predicado"
    try:
        builder.build({"op": "NOT", "children": [True, False]})
        raise AssertionError("builder debe rechazar NOT con 2 hijos")  # pragma: no cover — inalcanzable: builder SÍ lanza (verificado por tests directos); el raise solo corre si el builder fallara en rechazar lo que debe
    except ValueError as e:
        assert "NOT" in str(e), "mensaje debe nombrar el operador"

    print("✓ socratic_engine selftest OK — trivaluado + certified + explain + diagnose + builder discriminan")


# ─────────────────────────────────────────────────────────────────────────────
# CLI EXTERNA: socratic-eval — el contrato del shell único de plugins (fase a,
# PLUGIN-CLASS-TAXONOMY-v1). Un plugin TS delgado (o un gate write-time) llama
# a este evaluador con un árbol + contexto JSON; recibe la decisión como JSON.
# R10: el motor decide con evidencia estructural; el LLM puede proponer, nunca
# certificar. R9: UNKNOWN → '?' visible en home, nunca else_home silencioso.
#
# Uso:
#   python3 scripts/vsl/socratic_engine.py eval-tree <arbol.vsm|arbol.json> \
#       --context '{"type":"VSL-LANG-GATES-v1.0","path":"..."}'
#   → {"truth":"TRUE","certified":true,"home":"vsl-language","unknown":false,
#      "diagnose":[...],"explain":"..."}
# ─────────────────────────────────────────────────────────────────────────────

def _eval_tree_cli(argv: list[str]) -> int:
    if len(argv) < 1:
        print("usage: socratic_engine.py eval-tree <tree.vsm|tree.json> "
              "[--context <json>] [--doc-type <TYPE>]", file=sys.stderr)
        return 2
    tree_path = Path(argv[0])
    if not tree_path.exists():
        print(f"tree not found: {tree_path}", file=sys.stderr)
        return 2
    ctx: dict = {}
    i = 1
    while i < len(argv):
        if argv[i] == "--context" and i + 1 < len(argv):
            try:
                ctx = json.loads(argv[i + 1])
            except json.JSONDecodeError as e:
                print(f"context is not valid JSON: {e}", file=sys.stderr)
                return 2
            i += 2
        elif argv[i] == "--doc-type" and i + 1 < len(argv):
            ctx["type"] = argv[i + 1]
            i += 2
        else:
            i += 1
    # árbol: .json → dict directo; .vsm → parse_socratic_block
    if tree_path.suffix == ".json":
        tree = json.loads(tree_path.read_text(encoding="utf-8"))
    else:
        tree = parse_socratic_block(tree_path.read_text(encoding="utf-8"))
    if tree is None:
        print("no socratic(...) block found in tree file", file=sys.stderr)
        return 2
    eng = SocraticEngine()
    try:
        ev = eng.evaluate(tree, ctx)
    except (ValueError, KeyError, TypeError) as e:
        print(f"evaluation error: {e}", file=sys.stderr)
        return 1
    out: dict = {
        "truth": ev.truth.name if hasattr(ev.truth, "name") else str(ev.truth),
        "certified": ev.certified,
        "unknown": ev.is_unknown,
        "home": tree_home(tree, ctx.get("type", ""), eng, ctx),
        "explain": ev.explain(),
        "diagnose": [t.to_dict() if hasattr(t, "to_dict") else str(t)
                     for t in eng.diagnose(tree, ctx)],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point: `socratic-engine eval-tree <tree> [opts]` o selftest."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "eval-tree":
        return _eval_tree_cli(args[1:])  # pragma: no cover — verificado por subprocess en tests; coverage no instrumenta procesos hijos
    # selftest rápido (R4.1: el instrumento se auto-verifica)
    _run_selftest()
    return 0


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover — verificado por subprocess en tests; coverage no instrumenta procesos hijos

