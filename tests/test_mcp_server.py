"""Tests del MCP server: rate limiting (v0.2.0)."""

import json

from socratic_engine.mcp_server import (
    RATE_LIMIT_ERROR_CODE,
    RateLimiter,
    SocraticMCP,
)


def _call(server: SocraticMCP, method: str, params: dict) -> dict:
    req = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    return server.handle(req)


def test_rate_limiter_allows_within_limit():
    rl = RateLimiter(limit=3, window=60)
    for _ in range(3):
        ok, _ = rl.allow("tool")
        assert ok
    ok, retry = rl.allow("tool")
    assert not ok
    assert retry is not None and retry > 0


def test_rate_limiter_per_method_independent():
    rl = RateLimiter(limit=1, window=60)
    ok, _ = rl.allow("a")
    assert ok
    ok, _ = rl.allow("b")  # método distinto → permitido
    assert ok
    ok, _ = rl.allow("a")  # a agotado
    assert not ok


def test_rate_limiter_window_expires():
    rl = RateLimiter(limit=1, window=0.05)
    ok, _ = rl.allow("tool")
    assert ok
    import time
    time.sleep(0.06)
    ok, _ = rl.allow("tool")  # ventana expirada → permitido de nuevo
    assert ok


def test_mcp_rate_limit_exceeded_returns_error():
    server = SocraticMCP()
    server.rate_limiter = RateLimiter(limit=1, window=60)
    tree = {"op": "AND", "children": [{"predicate": "ctx_has",
                                       "args": ["$ctx", "type"]}]}
    _call(server, "tools/call",
          {"name": "socratic_evaluate",
           "arguments": {"tree": tree, "context": {"type": "T"}}})
    resp = _call(server, "tools/call",
                 {"name": "socratic_evaluate",
                  "arguments": {"tree": tree, "context": {"type": "T"}}})
    assert "error" in resp
    assert resp["error"]["code"] == RATE_LIMIT_ERROR_CODE
    assert resp["error"]["data"]["retry_after_s"] >= 0


def test_mcp_rate_limit_per_tool():
    server = SocraticMCP()
    server.rate_limiter = RateLimiter(limit=1, window=60)
    tree = {"op": "AND", "children": [{"predicate": "ctx_has",
                                       "args": ["$ctx", "type"]}]}
    _call(server, "tools/call",
          {"name": "socratic_evaluate",
           "arguments": {"tree": tree, "context": {"type": "T"}}})
    # socratic_diagnose es herramienta distinta → permitida
    resp = _call(server, "tools/call",
                 {"name": "socratic_diagnose",
                  "arguments": {"tree": tree, "context": {"type": "T"}}})
    assert "result" in resp


def test_mcp_normal_call_still_works():
    server = SocraticMCP()
    server.rate_limiter = RateLimiter(limit=10, window=60)
    tree = {"op": "AND", "children": [{"predicate": "ctx_has",
                                       "args": ["$ctx", "type"]}]}
    resp = _call(server, "tools/call",
                 {"name": "socratic_evaluate",
                  "arguments": {"tree": tree, "context": {"type": "T"}}})
    assert "result" in resp
    text = resp["result"]["content"][0]["text"]
    d = json.loads(text)
    assert d["truth"] == "TRUE"
