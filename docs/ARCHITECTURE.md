# Architecture — socratic-engine

> How the engine actually fits together. Written against the code
> (engine.py, tree.py, cli.py, mcp_server.py), not against aspiration.

## Overview

`socratic-engine` is a small, model-agnostic reasoning substrate: a
recursive evaluator for **trivalent logical trees**. The entire core is
four modules:

| Module | Responsibility |
|---|---|
| `socratic_engine/engine.py` | The evaluator: `Truth`, `Evaluation`, `PredicateResult`, `SocraticEngine`, `FailureTrace`, `diagnose()` |
| `socratic_engine/tree.py` | Parsing + tree building: `SocraticTreeBuilder`, `parse_socratic_block()`, `tree_home()` |
| `socratic_engine/cli.py` | External contract: `socratic-engine eval-tree <tree> [--context JSON] [--doc-type T]` + `selftest` |
| `socratic_engine/mcp_server.py` | MCP bridge: `socratic_evaluate`, `socratic_diagnose`, `socratic_build` |

```
                ┌────────────────────────────────────────────┐
                │              socratic-engine                │
                │                                              │
  tree.vsm ───► │  parse_socratic_block / SocraticTreeBuilder │
                │              │                               │
                │              ▼                               │
                │      SocraticEngine.evaluate(node, ctx)      │
                │              │  ┌──► predicates (built-in    │
                │              │  │     or registered)         │
                │              ▼  │                            │
                │      Evaluation (rich, recursive)            │
                │      truth/certified/evidence/children       │
                │              │                               │
                │              ▼                               │
                │      diagnose() → FailureTrace[]             │
                │                                              │
                └──────────────┬───────────────────────────────┘
                               │
              ┌────────────────┼──────────────────┐
              ▼                ▼                  ▼
        CLI eval-tree    MCP server        (future: library API)
```

## Core data model

### `Truth` — trivalent logic

```python
class Truth(Enum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"
```

`UNKNOWN` is first-class, not an error. Absence of evidence is not
falsity — it is indetermination (see ONTOLOGY.md, R9: no silent
concession).

### `Evaluation` — the rich result

Every recursive evaluation produces an `Evaluation` that conserves:

- `truth` — the trivalent logical value
- `certified` — whether the truth is backed by sufficient structural
  evidence (the truth/certification split; an LLM opinion is
  `TRUE/uncertified`)
- `evidence` — raw data that supports the evaluation
- `source` — where it came from (predicate, operator, literal)
- `children` — recursive sub-evaluations (the reasoning tree)
- `context` — contextual state at evaluation time
- `metadata` — arbitrary extras

The `children` list is what makes the whole thing inspectable: the
result is not just a boolean, it is the full reasoning tree that
produced it.

### `PredicateResult` — predicate outcome

A predicate returns a `PredicateResult` carrying the same truth /
certified / evidence / source shape, which is then folded into the
parent `Evaluation`.

## Evaluation semantics

### Operators

`SocraticEngine.OPERATORS = {"AND", "OR", "NOT", "XOR", "IMPLIES"}`.

Certification propagates per-operator (the exact rules live in
ONTOLOGY.md):

- **AND** — all children certified
- **OR** — at least one TRUE child certified
- **NOT** — child certified
- **XOR** — both children certified
- **IMPLIES** — antecedent AND consequent certified

### Predicates

Built-in predicates (in `engine.py`):

| Predicate | Matches |
|---|---|
| `type_glob` | document type against a glob |
| `type_prefix` | document type against a prefix |
| `type_regex` | document type against a regex |
| `type_has` | document type contains a token |
| `doc_has_status` | document has a status field |
| `ctx_has` | context has a key (with optional value) |

New predicates are registered with `engine.register(name)` — the
mechanism used by the CLI to inject domain-specific ones.

### UNKNOWN semantics in `tree_home()`

Epistemological detail: when a child responds `UNKNOWN` (could not be
decided), the router does **not** silently fall to `else_home` — it
returns `None` (the `?` state). A router must not route a decision it
could not make. This is the R9 no-silent-concession rule made concrete
in the engine.

## The truth/certification split

The single most important design decision:

- **truth** — is the proposition true under the system's rules?
- **certified** — do we have structural evidence sufficient to assert it?

An LLM saying "the service is running" is `TRUE, certified=FALSE`.
`pgrep` verifying the process is `TRUE, certified=TRUE`. The engine can
consume both, but only certified results survive into a gate.

## Parsing (tree.py)

Two entry points:

1. **JSON trees** — `.json` files are loaded directly as dicts.
2. **VSL trees** — `.vsm` files are parsed by `parse_socratic_block()`,
   which extracts the `socratic("NAME") = { ... }` block (vsm-1.2
   format) and converts it to a dict. The block regex requires the `=`
   between the name and the body.

`SocraticTreeBuilder.build(tree_json)` normalizes a raw tree dict into
the evaluator's canonical shape.

## CLI (cli.py)

```
socratic-engine eval-tree <tree.vsm|tree.json> [--context <json>] [--doc-type <TYPE>]
socratic-engine selftest
```

Output is JSON with at minimum:

```json
{
  "truth": "TRUE|FALSE|UNKNOWN",
  "certified": true|false,
  "unknown": false,
  "home": null,
  "explain": "...",
  "diagnose": [...]
}
```

The CLI registers extra predicates (`maybe`, `llm_judge`, ...) via
`engine.register` — the extension mechanism.

## MCP server (mcp_server.py)

`SocraticMCP` exposes three operations:

- `socratic_evaluate(tree, context)` — evaluate and return the result dict
- `socratic_diagnose(tree, context)` — return the failure traces
- `socratic_build(tree)` — normalize a raw tree into canonical form

Runs as `socratic-engine-mcp`. The `mcp` extra (`mcp>=1.0`) is
optional — core engine has zero dependencies.

## Failure diagnosis

`evaluate()` is paired with `diagnose()`:

- `FailureTrace` — a leaf that failed certification, with path and reason
- `find_failure_traces(evaluation, path)` — walks the `Evaluation`
  tree and collects every failed leaf

This converts "it didn't pass" into "it failed here, for this reason,
with this evidence" — the trace-inverse principle of ONTOLOGY.md.

## Relationship to the host system (VSM / state-canon)

The engine is domain-agnostic; it does not import state-canon. In the
VSM context it is the epistemic substrate for S1 verification (S3
supervision): predicates verify claims against reality, state-canon
reconciles declared-vs-observed, and this engine provides the formal
certification tree that gates decisions. The bridge is the CLI/MCP
contract, not a code dependency.

## Boundaries — what this is NOT

- Not an agent framework (no agents, no loops, no memory)
- Not a vector DB / RAG
- Not a prompting system
- Not a judge of truth — it is the *structure* in which truth claims
  are proposed, evaluated, certified, and diagnosed
