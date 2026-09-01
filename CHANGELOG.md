# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- **Version**: 0.2.4 → 0.2.5

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
