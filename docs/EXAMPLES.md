# Examples — socratic-engine in practice

> Every example below is executable. Run them with the CLI
> (`python -m socratic_engine.cli`) or adapt them into tests.

---

## 1. Classification tree (the router use case)

The canonical use: a document type routes to a subsystem home based on
a classification tree.

**File `classify.vsm`:**

```
socratic("CLASS-TREE-CLASSIFY") = {
  op: AND,
  children: [
    { predicate: "ctx_has", args: ["$ctx", "type"], },
    { op: OR, children: [
      { predicate: "type_prefix", args: ["$type", "VSL-LANG-"], home: "vsl-language" },
      { predicate: "type_glob", args: ["$type", "SPEC-*"], home: "spec" },
    ], },
  ],
  else_home: "system",
}
```

**Run:**

```bash
python -m socratic_engine.cli eval-tree classify.vsm --context '{"type":"SPEC-42"}'
# → {"truth":"TRUE", "certified":true, "home":"spec", ...}
```

A `VSL-LANG-*` doc routes to `vsl-language`; a `SPEC-*` doc to `spec`;
anything else to `system` — or `home:null` if the decision is UNKNOWN.

---

## 2. Deploy gate (the CI/CD use case)

A gate that refuses to certify a deploy unless the process is running
AND the schema is valid.

**Python (library API):**

```python
from socratic_engine import SocraticEngine, PredicateResult, Truth

engine = SocraticEngine()

@engine.register("service_running")
def service_running(name, **kw):
    # In real life: pgrep/ps + systemctl is-active — deterministic evidence
    return PredicateResult(truth=Truth.TRUE, certified=True,
                           evidence={"check": "systemctl is-active", "name": name})

@engine.register("schema_valid")
def schema_valid(data, **kw):
    if not data or "id" not in data:
        return PredicateResult(truth=Truth.FALSE, certified=True)
    return PredicateResult(truth=Truth.TRUE, certified=True,
                           evidence={"fields_checked": ["id"]})

tree = {"op": "AND", "children": [
    {"predicate": "service_running", "args": ["cache"]},
    {"predicate": "schema_valid", "kwargs": {"data": {"id": 7}}},
]}

ev = engine.evaluate(tree)
print(ev.truth, ev.certified)      # Truth.TRUE True
print(ev.explain())                # full reasoning tree
```

**Semantics that matter here:**

- If `service_running` cannot verify (timeout), return
  `Truth.UNKNOWN` — the gate must NOT certify on absence of evidence.
- `certified=False` means "someone said TRUE but nobody proved it" —
  the gate rejects it.

---

## 3. Failure diagnosis (the incident-response use case)

`diagnose()` points at exactly which leaf prevented **certification** —
the case that matters is not a legitimately-certified FALSE (that is a
clean rejection), but a leaf that returned UNKNOWN (insufficient
evidence), because that is where the gate cannot decide.

```python
from socratic_engine import SocraticEngine, PredicateResult, Truth

engine = SocraticEngine()

@engine.register("disk_ok")
def disk_ok(threshold, **kw):
    usage = 0.93
    return PredicateResult(
        truth=Truth.TRUE if usage < threshold else Truth.FALSE,
        certified=True,
        evidence={"usage": usage, "threshold": threshold},
    )

@engine.register("backup_recent")
def backup_recent(age_hours, **kw):
    # no backup data available → UNKNOWN, NOT certified
    return PredicateResult(
        truth=Truth.UNKNOWN, certified=False,
        evidence={"age_hours": age_hours, "error": "backup status unavailable"},
    )

tree = {"op": "AND", "children": [
    {"predicate": "disk_ok", "args": [0.9]},
    {"predicate": "backup_recent", "args": [30]},
]}

ev = engine.evaluate(tree)
# ev.truth == FALSE, ev.certified == False
for t in engine.diagnose(tree):
    print(t)
```

Output (abridged):

```
[✗] op:AND → backup_recent | unknown | El predicado 'backup_recent' retornó UNKNOWN (evidencia insuficiente)
```

`disk_ok` is certified-FALSE (a clean rejection, not a problem); the
gate's inability to decide comes from `backup_recent`'s UNKNOWN — and
`diagnose()` says so. Note: a certified-FALSE AND returns no traces —
there was no certification failure, the answer is a legitimate "no".

---

## 4. LLM opinion — certified never

The R10 boundary in practice: an LLM may **propose** (generate trees,
voice an opinion via `llm_judge`) but never **certify**.

```python
from socratic_engine import PredicateResult, Truth

# An LLM's answer is evidence of opinion, not evidence of fact:
opinion = PredicateResult(
    truth=Truth.TRUE,          # "the service is running" (per the model)
    certified=False,           # ← NO structural evidence
    evidence={"source": "llm_judge", "confidence": 0.8},
)
# A gate that requires certified=True will reject this.
```

Combine: LLM proposes a tree, the tree is evaluated against
deterministic predicates (`systemctl is-active`), and only the
certified leaves carry the gate.

---

## 5. VSL trees with `parse_socratic_block`

Trees can be declared in VSL files (vsm-1.2) and parsed directly:

```python
from socratic_engine.tree import parse_socratic_block

text = '''
socratic("SMOKE") = {
  predicate: "ctx_has",
  args: ["$ctx", "type"],
  home: "ok",
}
'''
tree = parse_socratic_block(text)
assert tree is not None
assert tree["predicate"] == "ctx_has"
```

Note the `= ` between the name and `{` — the parser regex requires it.

---

## Quick reference

| Operation | CLI | Library |
|---|---|---|
| Evaluate a tree | `socratic-engine eval-tree tree.vsm --context '{"type":"X"}'` | `engine.evaluate(tree, ctx)` |
| Diagnose failures | `eval-tree` returns `diagnose[]` | `engine.diagnose(tree, ctx)` |
| Parse a VSL block | — | `parse_socratic_block(text)` |
| Register a predicate | (domain predicates via engine) | `@engine.register("name")` |
| MCP bridge | `socratic-engine-mcp` | `SocraticMCP.evaluate/diagnose/build` |
---

## 6. Dialectical AND — certified contradiction (v0.2.0)

A service says "up" (`systemd`), an external healthcheck says "down".
Both are certified structural evidence — rejecting one is taking a side.
`DIALECTICAL_AND` surfaces the tension instead:

```python
from socratic_engine import SocraticEngine, PredicateResult, Truth

engine = SocraticEngine()

@engine.register("systemd_says_up")
def systemd_says_up(name, **kw):
    # deterministic: systemctl is-active
    return PredicateResult(truth=Truth.TRUE, certified=True,
                           evidence={"check": "systemctl is-active", "name": name})

@engine.register("healthcheck_says_down")
def healthcheck_says_down(url, **kw):
    # deterministic: HTTP probe from outside the host
    return PredicateResult(truth=Truth.FALSE, certified=True,
                           evidence={"probe": url, "status": 503})

tree = {"op": "DIALECTICAL_AND", "children": [
    {"predicate": "systemd_says_up", "args": ["cache"]},
    {"predicate": "healthcheck_says_down", "args": ["http://cache:8080/health"]},
]}

ev = engine.evaluate(tree)
print(ev.truth, ev.certified)              # Truth.UNKNOWN True
print(ev.metadata["dialectical_conflict"]) # True
print(ev.metadata["thesis"])               # [{"source": "systemd_says_up", "evidence": {...}}]
print(ev.metadata["antithesis"])           # [{"source": "healthcheck_says_down", "evidence": {...}}]
print(engine.diagnose(tree))               # [] — no guilty child; the contradiction is the state
```

The upper level receives a **certified UNKNOWN** with the full tension:
"evidence in conflict", not "no evidence". It must synthesize (e.g.
escalate to a human, or probe a third source) — it cannot silently pick
a side.

---

## 7. Pragmatic predicates — trends and feedback loops (v0.2.0)

The engine now ships predicates that ask *behavioral* questions, not
just static document questions.

**Tendencia:** una serie que crece pero con una caída brusca es ruido, no tendencia.

```python
from socratic_engine import SocraticEngine

engine = SocraticEngine()

ev = engine.evaluate({"predicate": "trend_up", "args": [[1, 2, 3, 4]]})
print(ev.truth.name, ev.certified)          # TRUE True (sostenida)

ev = engine.evaluate({"predicate": "trend_up", "args": [[1, 2, 3, 4, 0]]})
print(ev.truth.name, ev.certified)          # FALSE True (caída > 1/3 del rango = ruido)

ev = engine.evaluate({"predicate": "trend_up", "args": [[1]]})
print(ev.truth.name, ev.certified)          # UNKNOWN False (serie insuficiente — R10)
```

**Feedback loop:** un ciclo en la topología (longitud >= 2) que incluye al nodo objetivo.

```python
ev = engine.evaluate({"predicate": "feedback_loop",
                      "args": [{"A": ["B"], "B": ["C"], "C": ["A"]}, "A"]})
print(ev.truth.name, ev.certified)          # TRUE True — A→B→C→A
ev = engine.evaluate({"predicate": "feedback_loop",
                      "args": [{"A": ["A"]}, "A"]})
print(ev.truth.name, ev.certified)          # FALSE True — self-loop no cuenta
```

Misma disciplina R10: sin serie/topología válida → UNKNOWN no certificado;
la evidencia incluye la serie/el ciclo completo (auditable).

---

## 8. Cache TTL for costly predicates (v0.2.0)

Wrap an expensive predicate (I/O, network, MCP) with `@cached`:

```python
from socratic_engine import SocraticEngine, PredicateResult, Truth, cached

engine = SocraticEngine()

@engine.register("expensive_probe")
@cached(ttl=2.0)          # 2s window; default is 5s
def expensive_probe(host, **kw):
    # e.g. HTTP probe, DNS lookup, MCP call — slow
    return PredicateResult(truth=Truth.TRUE, certified=True,
                           evidence={"host": host})

e1 = engine.evaluate({"predicate": "expensive_probe", "args": ["cache"]})
e2 = engine.evaluate({"predicate": "expensive_probe", "args": ["cache"]})
# e2.metadata["cached"] == True — historical evidence, marked, not fresh
```

Semantics:

- `UNKNOWN` results are **never cached** — retrying is cheap and may be
  the only path to a decision.
- Cache hits are marked `metadata.cached=True` so consumers know the
  evidence is historical, not a fresh measurement.
- `engine.cache.clear()` forces re-verification.

The cache is an optimization, never a substitute for verification:
certification is still decided by the original predicate.
