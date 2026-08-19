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
    """JSON-RPC 2.0 server (stdio, newline-delimited) for the engine."""

    def __init__(self) -> None:
        self.engine = SocraticEngine()
        self.builder = SocraticTreeBuilder(self.engine)
        self.rate_limiter = RateLimiter()

    # ── tools ──

    def socratic_evaluate(self, tree: Any, context: dict | None = None) -> dict:
        """Evaluate a socratic tree against a context. tree: dict (JSON) or
        str (VSL socratic(...) block or JSON text). Returns the decision."""
        parsed = self._resolve_tree(tree)
        ctx = context or {}
        ev = self.engine.evaluate(parsed, ctx)
        return {
            "truth": ev.truth.name,
            "certified": ev.certified,
            "unknown": ev.is_unknown,
            "home": self._tree_home(parsed, ctx),
            "explain": ev.explain(),
            "diagnose": [str(t) for t in self.engine.diagnose(parsed, ctx)],
        }

    def socratic_diagnose(self, tree: Any, context: dict | None = None) -> list:
        """Inverse trace: only the nodes that caused certification failure."""
        parsed = self._resolve_tree(tree)
        return [str(t) for t in self.engine.diagnose(parsed, context or {})]

    def socratic_build(self, tree: Any) -> dict:
        """Validate a proposed tree (LLM proposal). R10.1: the engine
        validates structure + predicate existence; it never certifies."""
        try:
            self.builder.build(self._resolve_tree(tree))
            return {"ok": True, "errors": []}
        except (ValueError, TypeError) as e:
            return {"ok": False, "errors": [str(e)]}

    # ── helpers ──

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
                "serverInfo": {"name": "socratic-engine", "version": "0.2.0"},
            }}
        if method == "notifications/initialized":
            return None  # no response to notifications
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": [
                {"name": "socratic_evaluate", "description":
                 "Evaluate a socratic tree (JSON or VSL) against a context; "
                 "returns truth/certified/home/explain/diagnose."},
                {"name": "socratic_diagnose", "description":
                 "Inverse trace: which nodes failed certification."},
                {"name": "socratic_build", "description":
                 "Validate a proposed tree structure against registered "
                 "predicates (R10.1: proposal validation, not certification)."},
            ]}}
        if method == "tools/call":
            params = req.get("params", {})
            name = params.get("name", "")
            args = params.get("arguments", {})
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
    sys.exit(main())