# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **VSM→SEF derivation (A3, roadmap v030 §3.4 FASE 1-3)**: new `socratic_engine/vsm_sef.py` — `SYSTEM_KIND` mapping (S1→execution, S2→routing, S3→validation, S4→hypothesis, S5→covenant), deterministic per-system templates (`derive_tree`) evaluated with `ctx_has`/`ctx_not_has` slots and root `inject_context: true`, derivation rules `derive_from_vsm_block` (S3* channel excluded) + `check_vsm_block_invariants` (5 subsystems required), preservation invariants `check_invariants` (template-match, `SocraticTreeBuilder`, ≥1 slot), and FASE-3 auto-generation of the five `s{1..5}_*.tree.vsm` template files (`render_template_file`/`generate_template_files`, round-trip via `parse_socratic_block`). S4 uses AND (not IMPLIES): `IMPLIES(UNKNOWN, TRUE)` would certify TRUE from an empty context (epistemic vacuity). Negative branches use `ctx_not_has` so absence is provable (`NOT(ctx_has)` can never reach TRUE: missing data is UNKNOWN).

### Changed
- **TASK-5/C — certified-UNKNOWN for completed-empty canon queries (GAP-10, decision S5 2026-10-01)**: a `canon_*` query that *completes* against the right provider and returns 0 records now returns `UNKNOWN, certified=True` carrying `evidence.indeterminacy = {kind: exhaustive-empty, proof: {query_completed: true, routing}}`. Previously merged failure/empty branches are now split: `unknown_domain` and `query_failed` keep `UNKNOWN, certified=False` (no completed search to show), and the R10-corolario gate (`_valid_indeterminacy`) still degrades any certified-UNKNOWN without a valid proof block. Applies to `canon_query` (`no_records`) and to `canon_matches`/`canon_field_equals`/`canon_drift` (previously fused `records is None or not records` under `no_evidence` — now split into uncertified failure vs certified empty).

### Tests
- **627 passed** (was 591): 36 new `tests/test_vsm_sef.py` (FASE 1 mapping/shapes, FASE 2 derivation+invariants, FASE 3 template files/round-trip/evaluation). Coverage `socratic_engine/*` = **92%** (gate 90; `vsm_sef.py` 93%).
- **591 tests at TASK-5/C**: 9 new `TestTask5ExhaustiveEmpty` tests 9 new `TestTask5ExhaustiveEmpty` tests (certified empty with proof per predicate, failed/unknown-domain stay uncertified, engine gate preserves proven-UNKNOWN and degrades bare UNKNOWN+certified).

## [0.2.12] - 2026-09-22

### Added
- **Certified-UNKNOWN doctrine (R10-corolario, S5)**: `certified=True` admits `truth=UNKNOWN` only with an `indeterminacy` evidence block. New `INDETERMINACY_KINDS` vocabulary (`undecidable-reduction`, `quantum-superposition`, `jury-hung`, `exhaustive-empty`, `vague-boundary`, `symmetric-tie`) + validator. A gate in `_evaluate_predicate` degrades bare UNKNOWN+certified to uncertified with a warning (truth preserved, caller object unmutated). Precedent: `DIALECTICAL_AND` already certified UNKNOWN on proven contradiction.
- **`JURY` operator**: verdict by supermajority (default ⅔, configurable `supermajority` in (0.5, 1.0], `quorum` default = all children). Supermajority wins; hung + quorum → `UNKNOWN` certified with `indeterminacy: jury-hung` in metadata (tally travels in `metadata["jury"]`); no quorum → `UNKNOWN` uncertified. `UNKNOWN` votes are abstentions. Certification = all votes certified (the verdict certifies the *procedure*).
- **Computation nodes**: `{"computation": {features, tree}}` evaluated natively — chained derived features (`d0 → d1 → d2` over 15 ops) then genome-style decision tree. Zero-loss target for RSI genome evaluation.
- **`match-procedure` CLI command**: match context against `learning_records/procedures/` (instrument/hook/success/recency scoring) → `reuse`/`adapt`/`skip` with confidence.
- **Duplicate-domain priority (GAP-9)**: `add_provider(..., priority=N)` + `priority` config field (higher wins, tie keeps first registered); exposed in `canon_providers` evidence.
- **Inline VSL notation (GAP-8)**: `parse_socratic_block` accepts `socratic(predicate, arg, ...)` shorthand → `{predicate, args}` (quote-aware paren matching, reuses `_parse_vsl_value`).

### Fixed
- **Observer-effect heal (H4)**: `canon_providers`/`canon_domains` introspection called the health-tracking `list_domains()` wrapper, clearing consecutive query failures — observing health healed the patient. `query`/`list_domains` accept `track=False`, used by introspection paths.
- **`from_config` robustness**: falls back to `sys.modules` (full path, then final component) when importlib can't resolve — fixes `test_loads_config` under pytest rootdir import mode.

### Tests
- **546 passed** (was 519): 14 jury/gate tests, 10 composite multi-bridge tests (OR/NOT/nested/empty-children), inline-parser tests, observer-effect regressions. 2 tests updated to new contracts (inline fallback, falsification UNKNOWN).

## [0.2.11] - 2026-09-07

### Added
- **`decide` CLI command** — Evaluate decisions through the socratic engine before execution. Enables RSI (Recursive Self-Improvement) by logging decision outcomes for learning.
  - `--decision` — The decision to evaluate (required)
  - `--alternatives` — Comma-separated alternatives considered
  - `--impact` — Impact description
  - `--reversible` — Whether reversible (true/false, default: true)
  - `--prerequisites` — Comma-separated prerequisites
  - `--approved` — Mark as approved (required for irreversible decisions)
  - `--context` — Additional context as JSON
  - `--json` — Output as JSON (default: human-readable)

### Decision Evaluation Logic
- Reversible decisions pass automatically if decision is provided
- Irreversible decisions require `--approved` flag to pass
- Without approval, irreversible decisions return `UNKNOWN` (uncertified)
- Context merges into evaluation, affecting tree evaluation

### Tests
- 16 new tests in `tests/test_cli_decide.py`:
  - 9 integration tests (subprocess)
  - 4 unit tests for `_build_decide_tree`
  - 3 unit tests for `_decide_cli`

## [0.2.10] - 2026-09-05

### Added
- **ctx_equals(key, expected)** — Context predicate: checks if `ctx[key] == expected`. Supports 2-arg API (key, expected) and 3-arg legacy API ($ctx, key, expected). Returns TRUE/FALSE/UNKNOWN.
- **ctx_contains(key, substring)** — Context predicate: checks if `ctx[key]` contains `substring` (for strings) or `element` (for lists). Supports substring matching and list membership.
- **ctx_not_has(key)** — Context predicate: inverse of ctx_has. Returns TRUE if key is missing or empty.

### Context Predicates (complete set)
The engine now ships with 4 context predicates for tree-based evaluation:
- `ctx_has` — key exists and is non-empty (v0.2.5)
- `ctx_equals` — key equals expected value (NEW)
- `ctx_contains` — value contains substring/element (NEW)
- `ctx_not_has` — key is missing or empty (NEW)

## [0.2.9] - 2026-09-01

### Security (addressing independent audit findings)

#### 🔴 Critical Fixes
- **enforce_limits default changed to True** — Tree depth/node limits are now enabled by default. Callers that need to evaluate deep trees must explicitly pass `enforce_limits=False`. This prevents `RecursionError` crashes from pathological trees.
- **Cycle detection added** — Tracks visited nodes via `id()` to detect circular references. Uses `_visited` set that copies per-branch to allow shared subtrees while still catching real cycles.
- **Predicate error wrapping** — Exceptions from user predicates are now wrapped in `RuntimeError` with context (predicate name, args, kwargs) for better debugging. System errors (`RecursionError`, `MemoryError`, `KeyboardInterrupt`, `SystemExit`) propagate unwrapped.

#### 🟡 Robustness Improvements
- **XOR arity validation** — XOR now requires exactly 2 children (consistent with NOT and IMPLIES). Previously accepted n-ary XOR without validation.
- **Empty AND/OR warning** — Emits `UserWarning` when AND/OR have 0 children. Mathematically valid (identity elements) but likely indicates a bug.
- **Predicate overwrite warning** — Emits `UserWarning` when registering a predicate with a name that already exists. Prevents silent overwrites.

### Changed
- **Default behavior**: `enforce_limits=True` (was `False`)
- **Error handling**: Predicate exceptions wrapped in `RuntimeError`
- **Validation**: XOR, NOT, IMPLIES all validate arity

### Migration Guide
- If your code relies on `enforce_limits=False` being the default, you must now explicitly pass it:
  ```python
  # Before (implicit False)
  engine.evaluate(tree)
  
  # After (explicit False if needed)
  engine.evaluate(tree, enforce_limits=False)
  ```

### Test Updates
- Updated `test_falsification.py` deep recursion tests to use `enforce_limits=False`
- Updated `test_engine.py` XOR tests to use 2 children
- All 479 socratic-engine tests pass
- All 843 vsf-rsi tests pass (verified compatibility)

## [0.2.8] - 2026-09-01

### Added
- **engine_contract.py** — `SocraticEngineProtocol` and `EvaluationProtocol` define explicit public API between socratic-engine and vsf-rsi
- **check_engine_compatibility()** — validates engine meets contract requirements
- 18 protocol tests in `tests/test_engine_contract.py`

## [0.2.7] - 2026-09-01

### Fixed
- **_TreeLimitCounter bypass fix** — replaced `_node_count: int` with mutable counter shared by reference. Fixes two bypass bugs:
  - Bug 1: `_evaluate_predicate._maybe_eval` didn't forward limits to nested args
  - Bug 2: `_node_count` passed by value across siblings, not accumulated
- 11 regression tests in `tests/test_enforce_limits.py`
- Engine coverage: 94% → 96%

## [0.2.6] - 2026-08-31

### Fixed
- **ctx_has predicate**: Now supports both old API (`ctx_has(ctx, key)`) and new API (`ctx_has(key)`). Context is auto-injected via `_context` kwarg.
- **doc_has_status predicate**: Same backward-compatible fix as ctx_has. Supports both old API (`doc_has_status(doc, status)`) and new API (`doc_has_status(status)`).
- **Context injection**: Engine now has `inject_context_always` option to auto-inject context dict as `_context` kwarg to all predicates.

### Added
- **TreeExecutor class**: Wrapper for executing trees with context injection, validation, and diagnosis.
  - `execute(tree, context)` — Execute tree with validation
  - `execute_with_diagnosis(tree, context)` — Execute with full diagnosis output
- **load_tree function**: Load trees from .vsm (VSL format) or .json files.
- **register_module method**: Register all predicates from an external module.
- **register_predicates_dict method**: Register a dictionary of predicates at runtime.

### Changed
- **Backward compatible**: Old API for ctx_has and doc_has_status still works. New API is preferred.

### Technical Details
- ctx_has signature: `(ctx, key)` → `(*args, **kw)` with auto-detection
- doc_has_status signature: `(doc, status)` → `(*args, **kw)` with auto-detection
- Both predicates now accept `_context` kwarg for context injection
- Engine constructor now accepts `inject_context_always=True` parameter

## [0.2.4] - 2026-08-18

### Added
- DIALECTICAL_AND operator for thesis-antithesis synthesis
- PredicateCache with TTL for expensive predicates
- @cached decorator for predicate caching
- FailureTrace for inverse diagnosis
- find_failure_traces for certification failure analysis

### Changed
- Engine now supports `inject_context` flag per node for context injection

## [0.2.3] - 2026-08-15

### Added
- tree_home for routing documents to homes based on TYPE
- SocraticTreeBuilder for safe tree construction
- parse_socratic_block for VSL tree parsing

### Changed
- Engine now supports `$ctx` token for full context access

## [0.2.2] - 2026-08-10

### Added
- IMPLIES operator
- XOR operator
- trend_up, trend_down predicates
- feedback_loop predicate

## [0.2.1] - 2026-08-05

### Added
- type_glob, type_prefix, type_regex, type_has predicates
- ctx_has predicate
- doc_has_status predicate

## [0.2.0] - 2026-08-01

### Added
- Initial release with AND, OR, NOT operators
- Trivalent logic: TRUE, FALSE, UNKNOWN
- Certified evidence support
- explain() method for reasoning trace
