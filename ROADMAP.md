# Roadmap — socratic-engine

## ✅ v0.1.0 — Core
- [x] Motor trivaluado (TRUE/FALSE/UNKNOWN)
- [x] Separación truth/certified
- [x] Trace inverso (diagnóstico)
- [x] CLI eval-tree
- [x] MCP server básico
- [x] 14 tests unitarios
- [x] Predicados built-in (type_glob, type_prefix, etc.)

## ✅ v0.2.0 — Maduración
- [x] README con visión completa (The Problem + Philosophy)
- [x] docs/ONTOLOGY.md, docs/ARCHITECTURE.md, docs/EXAMPLES.md
- [x] GitHub Actions CI (pytest 3.10/3.11/3.12 + MCP job)
- [x] Coverage > 90% (CI gate `--cov-fail-under=90`)
- [x] Tests de integración con state-canon
- [x] Benchmarks de performance
- [x] Operador dialéctico (DIALECTICAL_AND)
- [x] Predicados pragmáticos (feedback loops, tendencias temporales)
- [x] Cache TTL para predicados costosos
- [x] Rate limiting en MCP server
- [x] Publicado en PyPI: https://pypi.org/project/socratic-engine/0.2.0/

## ✅ v0.2.3 — Bridge + Ejemplos
- [x] Bridge oficial con state-canon-mcp (canon_query/canon_matches/canon_field_equals/canon_drift)
- [x] VsmDocProvider: VSM documentation como records consultables
- [x] Ejemplo end-to-end con Claude Code (examples/claude-code-end-to-end.md)
- [x] Ejemplo end-to-end con OpenCode (examples/opencode-end-to-end.md)
- [x] Publicado: https://pypi.org/project/socratic-engine/0.2.3/
- [ ] VERIFY-E2E-CLAUDE-CODE — verificación en vivo (requiere tokens Anthropic)

## ✅ v0.2.4 — Multi-bridge + Semantic Simplification
- [x] Multi-bridge: routing de predicados canon_* a múltiples providers por dominio
  - MultiBridge class: routing domain→provider, 6 predicados
  - Config-driven: bridge_config.json con lazy loading
  - Provider health tracking (3-failure threshold → UNKNOWN)
  - Routing observability (provider, domain, latency_ms, record_count in evidence)
- [x] Semantic simplification (semantics.py)
  - NOT chain flattening: O(depth) → O(1)
  - Contradiction/tautology: AND(A, NOT(A)) → FALSE, OR(A, NOT(A)) → TRUE
  - Child deduplication: AND(P, P) → AND(P)
  - Absorption: AND(A, OR(A, B)) → A
  - Deep structural equality for nested contradiction detection
- [x] Short-circuit evaluation (AND stops at first FALSE, OR at first certified TRUE)
- [x] Tree DoS prevention (depth ≤ 100, nodes ≤ 10,000)
- [x] 450 tests + 46 adversarial tests (6 categorías)
- [x] Publicado: https://pypi.org/project/socratic-engine/0.2.4/

## ✅ v0.2.6 — Integration Fixes
- [x] simplify() returns bool/node instead of _resolved dict (gap fix)
- [x] detect_contradiction() returns bool
- [x] detect_absorption() returns child node + propagates inject_context
- [x] engine._evaluate_operator propagates inject_context to children
- [x] Dynamic predicate registration via @engine.register() decorator

## ✅ v0.2.7 — enforce_limits bypass fixes
- [x] _TreeLimitCounter: mutable counter shared by reference (replaces _node_count: int)
- [x] Bug 1 fix: _evaluate_predicate._maybe_eval forwards enforce_limits to nested args
- [x] Bug 2 fix: node count accumulates across siblings (not restart per child)
- [x] 11 regression tests in tests/test_enforce_limits.py
- [x] engine.py coverage: 94% → 96%

## ✅ v0.2.8 — Engine Contract (Protocol)
- [x] SocraticEngineProtocol: explicit public API for cross-package consumers
- [x] EvaluationProtocol: what vsf-rsi reads from results
- [x] check_engine_compatibility(): runtime feature detection + warnings
- [x] 18 tests in tests/test_engine_contract.py
- [x] Backward-compatible: **kwargs in Protocol, old engines still work

## 🚀 v0.3.0 — Extensión Formal
- [x] DIALECTICAL_AND — contradicción certificada (desde v0.1)
- [ ] Lógica paraconsistente (más allá de contradicción por pares)
- [ ] Frame semantics (hermenéutica: significado contextual)
- [ ] Stakeholder participation graphs (ética discursiva)
- [ ] Integración formal con VSM (derivación VSM→SEF)
