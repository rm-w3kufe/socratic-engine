# socratic-engine

**Externalized epistemic scaffolding for AI agents. Recursive boolean certification trees.**

A model-agnostic engine that evaluates recursive boolean trees with **trivalent
logic** (TRUE / FALSE / UNKNOWN), **evidence certification** (`certified`:
structural evidence ≠ opinion) and a **full reasoning trace**
(`explain()` / `diagnose()`).

Born inside the Viable System Model (VSM) governance stack (`vsf`), extracted
as a standalone library. Every agent layer — write-time gates, commit hooks,
MCP servers, CI/CD — uses the *same* engine, the *same* contract.

---

## The Problem

LLMs can't maintain logical consistency across long reasoning chains.
They confuse claims with facts, forget premises, and self-contradict.
When an agent says "the deployment is safe", you need more than
confidence scores — you need structural evidence.

Existing frameworks (LangChain, AutoGen, CrewAI) lack a verification
layer that separates opinion from certification. This engine fills
that gap.

## Why

LLM agents produce *claims*, not facts. Before a claim can gate a build, a
commit, a document, or a decision, something must certify it with
**structural evidence** — deterministic checks, not confidence scores.

`socratic-engine` gives you the decision layer: a recursive evaluator over
declared trees, where:

- **TRUE/FALSE/UNKNOWN** — the trivalent core. *Without a subject there is no
  judgment*: an empty TYPE is **UNKNOWN**, not FALSE. No silent concessions.
- **certified** — a predicate carries `PredicateResult(certified=True)` only
  when backed by structural evidence (fnmatch / prefix / regex / context).
  An LLM judge may answer TRUE but it does **not** certify (R10: opinion ≠
  evidence).
- **explain() / diagnose()** — the full reasoning tree, plus inverse tracing:
  *which leaf actually failed certification?* Feedback to the agent, not a
  black box.

## Install

> **Note:** the package is not on PyPI yet. Install from source for now.

### From source (recommended for now)

```bash
git clone https://github.com/rm-w3kufe/socratic-engine.git
cd socratic-engine
python -m venv .venv
.venv/bin/pip install -e .
```

### From source with MCP extras

```bash
.venv/bin/pip install -e ".[mcp]"
```

## Quick start

```python
from socratic_engine import SocraticEngine, tree_home

eng = SocraticEngine()

tree = {
    "op": "OR",
    "children": [
        {"predicate": "type_prefix", "args": ["$type", "VSL-LANG-"], "home": "vsl-language"},
        {"predicate": "type_prefix", "args": ["$type", "THEORY-VC-"], "home": "s3-control"},
    ],
    "else_home": "system",
}

home = tree_home(tree, "THEORY-VC-01", eng)   # → "s3-control"
home = tree_home(tree, "", eng)               # → None (UNKNOWN → '?' visible, NOT else_home)
```

### CLI

```bash
socratic-engine eval-tree tree.json --doc-type THEORY-VC-01
# → {"truth":"TRUE","certified":true,"home":"s3-control","unknown":false,
#    "explain":"op:OR → true [✓]\n  ...", "diagnose":[]}
```

Trees can be JSON or declared in VSL (`socratic("NAME") = { ... }` blocks —
nested AND/OR/NOT, kwargs, homes).

### Built-in predicates (deterministic)

| predicate | question | returns UNKNOWN when |
|---|---|---|
| `type_glob` | TYPE matches fnmatch pattern | TYPE empty |
| `type_prefix` | TYPE starts with prefix | TYPE empty |
| `type_regex` | TYPE matches regex | TYPE empty |
| `type_has` | TYPE contains token | TYPE empty |
| `doc_has_status` | doc declares @status | — |
| `ctx_has` | context provides key | key missing/empty |

Register your own with `@engine.register("name")` — return `bool` or
`PredicateResult(truth=..., certified=..., evidence=...)`.

## MCP bridge

Optional: expose the engine over the [Model Context Protocol](https://modelcontextprotocol.io).

```bash
pip install socratic-engine[mcp]
python -m socratic_engine.mcp_server
```

Tools: `socratic_evaluate` (tree + context → decision), `socratic_diagnose`
(failure traces), `socratic_build` (validate a proposed tree).

## Design notes

- **Model-agnostic.** The engine contains no domain logic: only
  `op/children/predicate`. The atomic questioning lives in predicates; each
  level declares *its* tree (a VSM recursion: every S1 contains a full L).
- **R10 (LLM boundary).** The LLM may *propose* trees and *opine* on
  predicates; it never *certifies*. `certified=True` requires structural
  evidence.
- **R9 (no silent concession).** An undecidable branch returns the visible
  `'?'` (None), never a silent `else_home`.

## Philosophy

This engine implements **externalized epistemic scaffolding**: the
verification structure lives OUTSIDE the LLM's reasoning, not inside it.

The LLM generates trees (proposals). The engine evaluates them
(certification). The trace explains failures (diagnosis). Each component
does what it does best.

This is not about making LLMs smarter. It's about making their claims
verifiable, auditable, and diagnosable.

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

## License

Apache-2.0 — see [LICENSE](./LICENSE).
