"""Minimal MCP server (stdio, JSON-RPC 2.0, newline-delimited). Stdlib only.

Exposes the socratic-engine surface over the Model Context Protocol:

  tools:
    socratic_evaluate — tree (JSON or VSL text) + context → decision
                        {truth, certified, home, unknown, explain, diagnose}
    socratic_diagnose — tree + context → failure traces only (inverse trace)
    socratic_build    — validate a proposed tree against the engine's
                        registered predicates → ok/errors (R10.1: the LLM
                        proposes, the engine validates, never certifies)

Run:
  python3 -m socratic_engine.mcp_server
  # or with the optional extra installed:
  socratic-engine-mcp
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from .engine import SocraticEngine, Truth
from .tree import SocraticTreeBuilder, parse_socratic_block

PROTOCOL_VERSION = "2024-11-05"

RATE_LIMIT_ERROR_CODE = -32029  # server error: rate limit exceeded


class RateLimiter:
    """Rate limiter por método (sliding window) para el MCP server (v0.2.0).

    Configurable por entorno (sin deps):
      SOCRATIC_MCP_RATE_LIMIT   → máx. llamadas por ventana (default 100)
      SOCRATIC_MCP_RATE_WINDOW  → ventana en segundos (default 60)

    Epistemología: un rate limit no es un rechazo al cliente — es una
    señal de que el canal está saturado; el cliente debe volver a
    intentar (backoff), no abandonar.
    """

    def __init__(self, limit: Optional[int] = None, window: float = 60.0):
        try:
            self.limit = int(limit if limit is not None
                             else os.environ.get("SOCRATIC_MCP_RATE_LIMIT", "100"))
        except ValueError:
            self.limit = 100
        try:
            self.window = float(window if window != 60.0
                                else os.environ.get("SOCRATIC_MCP_RATE_WINDOW", "60"))
        except ValueError:
            self.window = 60.0
        self._timestamps: Dict[str, List[float]] = {}  # method → recent call times

    def allow(self, method: str) -> Tuple[bool, Optional[float]]:
        """¿Permitir la llamada? Retorna (True, None) o (False, retry_after_s)."""
        now = time.monotonic()
        times = [t for t in self._timestamps.get(method, [])
                 if now - t < self.window]
        if len(times) >= self.limit:
            oldest = times[0] if times else now
            retry_after = max(0.0, oldest + self.window - now)
            self._timestamps[method] = times
            return False, retry_after
        times.append(now)
        self._timestamps[method] = times
        return True, None

    def reset(self, method: Optional[str] = None):
        if method:
            self._timestamps.pop(method, None)
        else:
            self._timestamps.clear()


class SocraticMCP:
    """JSON-RPC 2.0 server (stdio, newline-delimited) for the engine.

    Supports two bridge modes (opt-in — R6: the MCP core does not depend
    on state-canon):

    1. **Single provider** (legacy): pass ``provider=`` — registers
       ``StateCanonBridge`` with the 4 canon_* predicates.

    2. **Multi-bridge**: pass ``bridge_config=`` (path to a JSON config)
       or ``multi_bridge=`` (an already-created ``MultiBridge``) —
       registers all providers and exposes canon_* + canon_domains +
       canon_providers.
    """

    def __init__(
        self,
        provider: Any = None,
        bridge_config: str | None = None,
        multi_bridge: Any = None,
    ) -> None:
        self.engine = SocraticEngine()
        self.builder = SocraticTreeBuilder(self.engine)
        self.rate_limiter = RateLimiter()
        self.provider = provider
        self.bridge = None
        self._multi_bridge = None

        # --- bridge setup ---
        if multi_bridge is not None:
            # Multi-bridge provided directly
            self._multi_bridge = multi_bridge
            multi_bridge.register(self.engine)
        elif bridge_config is not None:
            # Load multi-bridge from config file
            from .multi_bridge import MultiBridge
            self._multi_bridge = MultiBridge.from_config(bridge_config)
            self._multi_bridge.register(self.engine)
        elif self.provider is not None:
            # Legacy single-provider bridge
            from .bridge_statecanon import StateCanonBridge
            self.bridge = StateCanonBridge(self.engine, self.provider)

        # --- tools (all require inputSchema per MCP spec) ---
        self._tools = [
            {"name": "socratic_evaluate", "description":
             "Evaluate a socratic tree (JSON or VSL) against a context; "
             "returns truth/certified/home/explain/diagnose.",
             "inputSchema": {"type": "object", "properties": {
                 "tree": {"description": "Socratic tree (JSON dict or VSL string)"},
                 "context": {"type": "object", "description":
                             "Evaluation context (optional)"},
             }, "required": ["tree"]}},
            {"name": "socratic_diagnose", "description":
             "Inverse trace: which nodes failed certification.",
             "inputSchema": {"type": "object", "properties": {
                 "tree": {"description": "Socratic tree (JSON dict or VSL string)"},
                 "context": {"type": "object", "description":
                             "Evaluation context (optional)"},
             }, "required": ["tree"]}},
            {"name": "socratic_build", "description":
             "Validate a proposed tree structure against registered "
             "predicates (R10.1: proposal validation, not certification).",
             "inputSchema": {"type": "object", "properties": {
                 "tree": {"description": "Proposed tree (JSON dict or VSL string)"},
             }, "required": ["tree"]}},
        ]

        if self._multi_bridge is not None:
            # Multi-bridge: expose all canon_* tools
            self._tools.extend([
                {"name": "socratic_canon_query", "description":
                 "Query a data source through the multi-bridge: "
                 "canon_query(domain, filter) → TRUE/UNKNOWN certified "
                 "by evidence.",
                 "inputSchema": {"type": "object", "properties": {
                     "domain": {"type": "string", "description":
                                "Data domain to query (e.g. 'services', 'tasks')"},
                     "filter": {"type": "object", "description":
                                "Filter criteria (key-value pairs)"},
                 }, "required": ["domain", "filter"]}},
                {"name": "socratic_canon_matches", "description":
                 "Check if records match expected values: "
                 "canon_matches(domain, filter, expected).",
                 "inputSchema": {"type": "object", "properties": {
                     "domain": {"type": "string"},
                     "filter": {"type": "object"},
                     "expected": {"description": "Expected values to match"},
                 }, "required": ["domain", "filter", "expected"]}},
                {"name": "socratic_canon_field_equals", "description":
                 "Check if a field equals expected value: "
                 "canon_field_equals(domain, filter, field, expected).",
                 "inputSchema": {"type": "object", "properties": {
                     "domain": {"type": "string"},
                     "filter": {"type": "object"},
                     "field": {"type": "string", "description":
                               "Field name to check"},
                     "expected": {"description": "Expected value"},
                 }, "required": ["domain", "filter", "field", "expected"]}},
                {"name": "socratic_canon_drift", "description":
                 "Detect declared vs observed drift: "
                 "canon_drift(domain, filter, declared, observed).",
                 "inputSchema": {"type": "object", "properties": {
                     "domain": {"type": "string"},
                     "filter": {"type": "object"},
                     "declared_field": {"type": "string", "description":
                                        "Field name in declared state"},
                     "observed_field": {"type": "string", "description":
                                        "Field name in observed state"},
                 }, "required": ["domain", "filter",
                                 "declared_field", "observed_field"]}},
                {"name": "socratic_canon_domains", "description":
                 "List all available domains across all providers.",
                 "inputSchema": {"type": "object", "properties": {}}},
                {"name": "socratic_canon_providers", "description":
                 "List all registered providers with their status.",
                 "inputSchema": {"type": "object", "properties": {}}},
            ])
        elif self.bridge is not None:
            # Legacy single bridge: only canon_query
            self._tools.append(
                {"name": "socratic_canon_query", "description":
                 "Query state-canon through the registered "
                 "bridge: canon_query(domain, filter) → "
                 "TRUE/UNKNOWN certified by evidence.",
                 "inputSchema": {"type": "object", "properties": {
                     "domain": {"type": "string"},
                     "filter": {"type": "object"},
                 }, "required": ["domain", "filter"]}}
            )

    # ── tools ──

    def socratic_evaluate(self, tree: Any, context: Any = None) -> dict:
        """Evaluate a socratic tree against a context. tree: dict (JSON) or
        str (VSL socratic(...) block or JSON text). Returns the decision."""
        parsed = self._resolve_tree(tree)
        self._validate_tree_limits(parsed)
        ctx = self._resolve_context(context)
        ev = self.engine.evaluate(parsed, ctx)
        return {
            "truth": ev.truth.name,
            "certified": ev.certified,
            "unknown": ev.is_unknown,
            "home": self._tree_home(parsed, ctx),
            "explain": ev.explain(),
            "diagnose": [str(t) for t in self.engine.diagnose(parsed, ctx)],
        }

    def socratic_diagnose(self, tree: Any, context: Any = None) -> list:
        """Inverse trace: only the nodes that caused certification failure."""
        parsed = self._resolve_tree(tree)
        self._validate_tree_limits(parsed)
        return [str(t) for t in self.engine.diagnose(parsed, self._resolve_context(context))]

    def socratic_build(self, tree: Any) -> dict:
        """Validate a proposed tree (LLM proposal). R10.1: the engine
        validates structure + predicate existence; it never certifies."""
        try:
            parsed = self._resolve_tree(tree)
            self._validate_tree_limits(parsed)
            self.builder.build(parsed)
            return {"ok": True, "errors": []}
        except (ValueError, TypeError) as e:
            return {"ok": False, "errors": [str(e)]}

    # ── helpers ──

    MAX_TREE_DEPTH = 100
    MAX_TREE_NODES = 10000

    def _validate_tree_limits(self, node: Any, depth: int = 0,
                              count: int = 0) -> tuple[int, int]:
        """Check tree depth and node count. Returns (depth, count).
        Raises ValueError if limits exceeded."""
        count += 1
        if count > self.MAX_TREE_NODES:
            raise ValueError(
                f"Tree has >{self.MAX_TREE_NODES} nodes "
                f"(DoS vector: exponential branching)"
            )
        if isinstance(node, dict) and "op" in node:
            depth += 1
            if depth > self.MAX_TREE_DEPTH:
                raise ValueError(
                    f"Tree depth >{self.MAX_TREE_DEPTH} "
                    f"(DoS vector: deep recursion chain)"
                )
            for child in node.get("children", []):
                depth, count = self._validate_tree_limits(child, depth, count)
        elif isinstance(node, dict) and "children" in node:
            for child in node.get("children", []):
                depth, count = self._validate_tree_limits(child, depth, count)
        return depth, count

    def _resolve_tree(self, tree: Any) -> dict:
        if isinstance(tree, str):
            try:
                return json.loads(tree)
            except json.JSONDecodeError:
                parsed = parse_socratic_block(tree)
                if parsed is None:
                    raise ValueError("tree is neither valid JSON nor a "
                                     "socratic(...) VSL block")
                return parsed
        if isinstance(tree, dict):
            return tree
        raise TypeError(f"tree must be dict or str, got {type(tree).__name__}")

    def _resolve_context(self, context: Any) -> dict:
        """Parse context from JSON string or pass through dict."""
        if context is None:
            return {}
        if isinstance(context, str):
            try:
                return json.loads(context)
            except json.JSONDecodeError:
                return {}
        if isinstance(context, dict):
            return context
        return {}

    def _tree_home(self, tree: dict, ctx: dict) -> str | None:
        from .tree import tree_home
        return tree_home(tree, ctx.get("type", ""), self.engine, ctx)

    # ── JSON-RPC dispatch ──

    def handle(self, req: dict) -> dict:
        req_id = req.get("id")
        method = req.get("method", "")
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": req_id, "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "socratic-engine", "version": "0.2.3"},
            }}
        if method == "notifications/initialized":
            return None  # no response to notifications
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": self._tools}}
        if method == "tools/call":
            params = req.get("params", {})
            name = params.get("name", "")
            args = params.get("arguments") or {}
            if not isinstance(args, dict):
                args = {}
            # Rate limit por herramienta (sliding window). El error es un
            # estado transitorio: retry_after indica al cliente cuándo
            # reintentar (backoff), no es un rechazo definitivo.
            allowed, retry_after = self.rate_limiter.allow(name)
            if not allowed:
                return {"jsonrpc": "2.0", "id": req_id,
                        "error": {"code": RATE_LIMIT_ERROR_CODE,
                                  "message": f"Rate limit exceeded for tool "
                                             f"'{name}'",
                                  "data": {"retry_after_s": round(retry_after, 3)}}}
            try:
                if name == "socratic_evaluate":
                    result = self.socratic_evaluate(args.get("tree"), args.get("context"))
                elif name == "socratic_diagnose":
                    result = self.socratic_diagnose(args.get("tree"), args.get("context"))
                elif name == "socratic_build":
                    result = self.socratic_build(args.get("tree"))
                elif name.startswith("socratic_canon_"):
                    # No bridge registered → tool not available
                    if self.bridge is None and self._multi_bridge is None:
                        return self._error(req_id, -32601,
                                           "No state-canon bridge registered")
                    # Route all canon_* tools through the engine
                    predicate = name.replace("socratic_canon_", "canon_")
                    # Map tool args to predicate args
                    if predicate == "canon_query":
                        pargs = [args.get("domain"), args.get("filter")]
                    elif predicate == "canon_matches":
                        pargs = [args.get("domain"), args.get("filter"),
                                 args.get("expected")]
                    elif predicate == "canon_field_equals":
                        pargs = [args.get("domain"), args.get("filter"),
                                 args.get("field"), args.get("expected")]
                    elif predicate == "canon_drift":
                        pargs = [args.get("domain"), args.get("filter"),
                                 args.get("declared_field"),
                                 args.get("observed_field")]
                    elif predicate in ("canon_domains", "canon_providers"):
                        pargs = []
                    else:
                        return self._error(req_id, -32601,
                                           f"Unknown canon predicate: {predicate}")
                    ev = self.engine.evaluate(
                        {"predicate": predicate, "args": pargs})
                    result = {"truth": ev.truth.name,
                              "certified": ev.certified,
                              "evidence": ev.evidence,
                              "explain": ev.explain()}
                else:
                    return self._error(req_id, -32601, f"Unknown tool: {name}")
                return {"jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text",
                                                "text": json.dumps(result)}]}}
            except (ValueError, TypeError, KeyError) as e:
                return self._error(req_id, -32602, f"Invalid params: {e}")
        if method in ("ping",):
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}
        return self._error(req_id, -32601, f"Method not found: {method}")

    @staticmethod
    def _error(req_id, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": req_id,
                "error": {"code": code, "message": message}}


def main() -> int:
    server = SocraticMCP()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = server.handle(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover — entry point __main__, cubierto por subprocess test; coverage no instrumenta procesos hijos
