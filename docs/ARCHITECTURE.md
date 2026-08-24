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
| `socratic_engine/semantics.py` | Semantic simplification: NOT flattening, contradiction/tautology, dedup, absorption |
| `socratic_engine/cli.py` | External contract: `socratic-engine eval-tree <tree> [--context JSON] [--doc-type T]` + `selftest` |
| `socratic_engine/mcp_server.py` | MCP bridge: `socratic_evaluate`, `socratic_diagnose`, `socratic_build` + DoS limits + simplify |
| `socratic_engine/multi_bridge.py` | Multi-provider routing: `MultiBridge`, domain-based canon_* dispatch, provider health tracking |
| `socratic_engine/bridge_statecanon.py` | Official state-canon bridge (single provider, opt-in) |
| `socratic_engine/providers/vsm_doc.py` | VSM documentation filesystem provider |

```
                ┌──────────────────────────────────────────────────┐
                │                socratic-engine                  │
                │                                                │
  tree.vsm ───► │  parse_socratic_block / SocraticTreeBuilder     │
                │              │                                   │
                │              ▼                                   │
                │  _validate_tree_limits(depth≤100, nodes≤10K)    │
                │              │                                   │
                │              ▼                                   │
                │  simplify() → semantic patterns                 │
                │  (NOT flatten, contradiction, dedup, absorption)│
                │              │                                   │
                │              ▼                                   │
                │      SocraticEngine.evaluate(node, ctx)          │
                │      + _evaluate_short_circuit(AND/OR)          │
                │              │  ┌──► predicates (built-in       │
                │              │  │     or registered)            │
                │              ▼  │                               │
                │      Evaluation (rich, recursive)               │
                │      truth/certified/evidence/children          │
                │              │                                   │
                │              ▼                                   │
                │      diagnose() → FailureTrace[]                │
                │                                                │
                └──────────────┬─────────────────────────────────┘
                               │
              ┌────────────────┼──────────────────┐
              ▼                ▼                  ▼
        CLI eval-tree    MCP server        (future: library API)
                     ┌─────────────┐
                     │ MultiBridge  │
                     │  routing     │
                     │  health      │
                     │  observability│
                     └──────┬──────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
         provider A    provider B    provider C
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

`SocraticEngine.OPERATORS = {"AND", "OR", "NOT", "XOR", "IMPLIES", "DIALECTICAL_AND"}`.

Certification propagates per-operator (the exact rules live in
ONTOLOGY.md):

- **AND** — all children certified
- **OR** — at least one TRUE child certified
- **NOT** — child certified
- **XOR** — both children certified
- **IMPLIES** — antecedent AND consequent certified
- **DIALECTICAL_AND** — in conflict: all children certified (the
  contradiction itself is a certified fact); without conflict: all
  children certified

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
| `trend_up` | time series is growing sustainably (min_delta, noise guard) |
| `trend_down` | time series is falling sustainably (min_delta, noise guard) |
| `feedback_loop` | topology has a closed cycle (length >= 2) through target |

New predicates are registered with `engine.register(name)` — the
mechanism used by the CLI to inject domain-specific ones.

### UNKNOWN semantics in `tree_home()`

Epistemological detail: when a child responds `UNKNOWN` (could not be
decided), the router does **not** silently fall to `else_home` — it
returns `None` (the `?` state). A router must not route a decision it
could not make. This is the R9 no-silent-concession rule made concrete
in the engine.

### DIALECTICAL_AND — certified contradiction

A plain AND short-circuits to FALSE on any FALSE child — contradiction
is rejection. But a *legitimate* contradiction (opposite claims, BOTH
certified with structural evidence) is not rejection and not approval:
deciding would take a side. `DIALECTICAL_AND` yields `UNKNOWN`
**certified** with the full tension in metadata
(`dialectical_conflict`, `thesis[]`, `antithesis[]`) so the upper level
can synthesize. A certified `UNKNOWN` is "evidence in conflict", not
"no evidence". `diagnose()` reports no guilty children for a certified
conflict — blaming a child would be taking a side. See ONTOLOGY.md.

## Semantic simplification (semantics.py)

Before evaluation, `simplify()` runs as a pre-processor on the tree.
It detects and resolves pathological patterns that would otherwise waste
evaluation cycles or produce misleading results.

**Pipeline** (called from `socratic_evaluate` after `_validate_tree_limits`):

1. **NOT chain flattening** — `NOT(NOT(NOT(P)))` → `NOT(P)` (odd) or
   `P` (even). O(depth) → O(1).

2. **Contradiction / tautology** — `AND(A, NOT(A))` → `_resolved: FALSE`.
   `OR(A, NOT(A))` → `_resolved: TRUE`. Pairwise structural equality
   check, O(n²) where n = children count.

3. **Child deduplication** — `AND(P, P, P)` → `AND(P)` → `P`. Uses
   `structural_equal()` for recursive dict comparison.

4. **Absorption** — `AND(A, OR(A, B))` → `A`. `OR(A, AND(A, B))` → `A`.
   Detects when a sibling appears inside a nested OR/AND.

5. **Deep contradiction** — `AND(P∧Q, NOT(P∧Q))` detected via recursive
   `structural_equal()` (not just shallow key comparison).

**Resolution markers**: simplify returns either a simplified tree dict
or `{"_resolved": true, "truth": bool}`. The MCP server unwraps
markers before calling `engine.evaluate()`.

## Tree DoS prevention

`_validate_tree_limits()` runs before simplification and evaluation.
Two hard limits:

- **MAX_TREE_DEPTH = 100** — prevents left-deep recursion chains
- **MAX_TREE_NODES = 10,000** — prevents exponential branching

Depth is tracked per-path (increment going down, max across siblings).
A balanced binary tree with 5K leaves (depth=14, 9999 nodes) passes;
a left-deep chain of 101 nodes (depth=101) is rejected.

## Short-circuit evaluation (engine.py)

`_evaluate_short_circuit()` wraps child evaluation for AND and OR:

- **AND**: stops at first certified FALSE → returns immediately
- **OR**: stops at first certified TRUE (not just TRUE — must be
  certified) → returns immediately

 uncertified TRUE does NOT trigger OR short-circuit: a predicate
returning `TRUE, certified=FALSE` (e.g., LLM opinion) is not sufficient
evidence to satisfy an OR gate.

## Multi-bridge (multi_bridge.py)

Routes `canon_*` predicates to providers by domain. Architecture:

```
canon_query(domain, filter)
       │
       ▼
  MultiBridge._records(domain, filter)
       │
       ├─► provider.agent-state.query("tasks", filter)  → records
       ├─► provider.infra-state.query("services", filter) → records
       └─► provider.vsm-docs.query("docs", filter)      → records
       │
       ▼
  (records, routing_info)
```

### Provider health tracking

Each `ProviderEntry` tracks:
- `_healthy` (bool, default True)
- `_consecutive_failures` (int)
- `_last_error` (str | None)
- `_last_check` (float | None)

**Threshold**: 3 consecutive failures → `_healthy = False`.
`canon_providers` returns `UNKNOWN` if any registered provider is
unhealthy. Failed queries return `UNKNOWN` (not FALSE) — a provider
crash is indetermination, not falsity.

### Routing observability

`_records()` returns `(records, routing_info)` where routing contains:
- `provider` — which provider answered
- `domain` — queried domain
- `latency_ms` — query time
- `record_count` — records returned

All `canon_*` predicates include routing in their evidence dict.
This makes provider selection inspectable in the evaluation tree.

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

## Cache TTL (v0.2.0)

`@cached(ttl=...)` wraps an expensive predicate. Key = (name,
serializable args, serializable kwargs). Semantics:

- **UNKNOWN is never cached** — re-trying is cheap and may be the only
  path to a decision.
- **Cache hits are marked** `metadata.cached=True` — the result is
  historical evidence, not a fresh measurement; the consumer can tell.
- Default TTL 5s (live systems change fast); per-registration TTL
  overrides it.
- `engine.cache.clear()` forces re-verification.

The cache is an optimization for costly predicates (I/O, network, MCP),
never a substitute for verification — certification is decided by the
original predicate.

## MCP server (mcp_server.py)

`SocraticMCP` exposes 9 operations:

**Core:**
- `socratic_evaluate(tree, context)` — simplify → evaluate → return result dict
- `socratic_diagnose(tree, context)` — return the failure traces
- `socratic_build(tree)` — normalize a raw tree into canonical form

**Multi-bridge (canon_*):**
- `socratic_canon_query(domain, filter)` — query records from a provider
- `socratic_canon_matches(domain, filter, expected)` — check if records match
- `socratic_canon_field_equals(domain, filter, field, expected)` — field equality
- `socratic_canon_drift(domain, filter, declared, observed)` — declared vs observed
- `socratic_canon_domains` — list all available domains
- `socratic_canon_providers` — list providers with health status

Runs as `socratic-engine-mcp`. The `mcp` extra (`mcp>=1.0`) is
optional — core engine has zero dependencies.

**Request flow:**

```
JSON-RPC request
  → _resolve_tree()        (parse JSON string if needed)
  → _validate_tree_limits() (depth ≤ 100, nodes ≤ 10K)
  → simplify()              (semantic patterns)
  → engine.evaluate()       (recursive, with short-circuit)
  → result dict
```

### Rate limiting (v0.2.0)

Sliding-window limiter per tool, configurable via env (no deps):

- `SOCRATIC_MCP_RATE_LIMIT` — max calls per window (default 100)
- `SOCRATIC_MCP_RATE_WINDOW` — window seconds (default 60)

A rate-limited call returns error `-32029` with
`data.retry_after_s` — a transient signal, not a rejection: the client
should back off and retry. `RateLimiter` is also usable standalone.

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
