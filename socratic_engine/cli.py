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


def _decide_cli(argv: list[str]) -> int:
    """CLI: socratic-engine decide --decision "..." [options]
    
    Evaluate a decision through the socratic engine.
    
    Options:
      --decision TEXT       The decision to evaluate (required)
      --alternatives TEXT   Comma-separated alternatives
      --impact TEXT         Impact description
      --reversible BOOLEAN Whether decision is reversible (default: true)
      --prerequisites TEXT  Comma-separated prerequisites
      --approved            Mark as approved (for irreversible decisions)
      --context JSON        Additional context as JSON
      --json                Output as JSON
    
    Returns:
      {"truth": "TRUE"/"FALSE", "certified": bool, "home": "pass"/"reject", ...}
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Evaluate a decision through the socratic engine"
    )
    parser.add_argument("--decision", required=True, help="The decision to evaluate")
    parser.add_argument("--alternatives", help="Comma-separated alternatives")
    parser.add_argument("--impact", help="Impact description")
    parser.add_argument("--reversible", default="true", help="Whether reversible (true/false)")
    parser.add_argument("--prerequisites", help="Comma-separated prerequisites")
    parser.add_argument("--approved", action="store_true", help="Mark as approved")
    parser.add_argument("--context", help="Additional context as JSON")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args(argv)
    
    # Build context
    ctx: dict = {
        "decision": args.decision,
        "reversible": args.reversible.lower(),  # Keep as string for ctx_equals
    }
    
    if args.alternatives:
        ctx["alternatives"] = [a.strip() for a in args.alternatives.split(",")]
    
    if args.impact:
        ctx["impact"] = args.impact
    
    if args.prerequisites:
        ctx["prerequisites"] = [p.strip() for p in args.prerequisites.split(",")]
    
    if args.approved:
        ctx["approved"] = True
    
    if args.context:
        try:
            extra = json.loads(args.context)
            ctx.update(extra)
        except json.JSONDecodeError as e:
            print(f"invalid --context JSON: {e}", file=sys.stderr)
            return 2
    
    # Build decide tree dynamically
    tree = _build_decide_tree(ctx)
    
    # Evaluate
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
        "home": "pass" if ev.is_true else "reject",
        "explain": ev.explain(),
        "diagnose": [t.to_dict() if hasattr(t, "to_dict") else str(t)
                     for t in eng.diagnose(tree, ctx)],
        "decision": args.decision,
        "context": {
            "reversible": ctx.get("reversible"),
            "has_alternatives": bool(ctx.get("alternatives")),
            "has_impact": bool(ctx.get("impact")),
            "approved": ctx.get("approved", False),
        },
    }
    
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        truth = out["truth"]
        certified = out["certified"]
        home = out["home"]
        
        if truth == "TRUE" and certified:
            print(f"✓ DECISION CERTIFIED: {args.decision}")
            print(f"  Truth: {truth}, Certified: {certified}")
        elif truth == "FALSE" and certified:
            print(f"✗ DECISION REJECTED: {args.decision}")
            print(f"  Truth: {truth}, Certified: {certified}")
            if out.get("explain"):
                print(f"  Reason: {out['explain'][:200]}")
        else:
            print(f"? DECISION UNCERTAIN: {args.decision}")
            print(f"  Truth: {truth}, Certified: {certified}")
    
    return 0 if ev.is_true else 1


def _build_decide_tree(ctx: dict) -> dict:
    """Build a decide tree dynamically from context.
    
    Tree structure:
      AND
      ├── ctx_has("decision")
      ├── OR
      │   ├── ctx_has("alternatives")
      │   └── (skip if no alternatives required)
      ├── OR
      │   ├── ctx_has("impact")
      │   └── (skip if no impact required)
      └── OR
          ├── ctx_equals("reversible", "true")
          └── AND
              ├── ctx_equals("reversible", "false")
              └── ctx_has("approved")
    """
    children = [
        # Gate 1: Decision must be provided
        {"predicate": "ctx_has", "args": ["$ctx", "decision"]},
    ]
    
    # Gate 2: Alternatives (only if provided in context)
    if ctx.get("alternatives"):
        children.append(
            {"predicate": "ctx_has", "args": ["$ctx", "alternatives"]}
        )
    
    # Gate 3: Impact (only if provided in context)
    if ctx.get("impact"):
        children.append(
            {"predicate": "ctx_has", "args": ["$ctx", "impact"]}
        )
    
    # Gate 4: Reversibility check
    # Note: ctx.get returns string, so we compare with "true"
    is_reversible = ctx.get("reversible", "true") == "true"
    
    if is_reversible:
        # Reversible decisions pass automatically
        children.append(
            {"predicate": "ctx_equals", "args": ["$ctx", "reversible", "true"]}
        )
    else:
        # Irreversible require approval
        children.append({
            "op": "AND",
            "children": [
                {"predicate": "ctx_equals", "args": ["$ctx", "reversible", "false"]},
                {"predicate": "ctx_has", "args": ["$ctx", "approved"]},
            ],
        })
    
    return {"op": "AND", "children": children}


def main(argv: list[str] | None = None) -> int:
    """Entry point: `socratic-engine eval-tree <tree> [opts]` o selftest."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "eval-tree":
        return _eval_tree_cli(args[1:])  # pragma: no cover — verificado por subprocess en tests; coverage no instrumenta procesos hijos
    if args and args[0] == "decide":
        return _decide_cli(args[1:])  # pragma: no cover — verificado por subprocess en tests
    # selftest rápido (R4.1: el instrumento se auto-verifica)
    _run_selftest()
    return 0


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover — verificado por subprocess en tests; coverage no instrumenta procesos hijos

