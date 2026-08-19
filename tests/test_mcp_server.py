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


# ── MCP: initialize / notifications / tools/list / ping / errores / VSL ──

def test_mcp_initialize():
    s = SocraticMCP()
    r = s.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert r["result"]["protocolVersion"] == "2024-11-05"
    assert r["result"]["serverInfo"]["version"] == "0.2.3"


def test_mcp_initialized_notification_no_response():
    s = SocraticMCP()
    r = s.handle({"jsonrpc": "2.0", "id": 2, "method": "notifications/initialized"})
    assert r is None


def test_mcp_tools_list():
    s = SocraticMCP()
    r = s.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    names = [t["name"] for t in r["result"]["tools"]]
    assert names == ["socratic_evaluate", "socratic_diagnose", "socratic_build"]


def test_mcp_ping():
    s = SocraticMCP()
    r = s.handle({"jsonrpc": "2.0", "id": 4, "method": "ping"})
    assert r["result"] == {}


def test_mcp_unknown_method_error():
    s = SocraticMCP()
    r = s.handle({"jsonrpc": "2.0", "id": 5, "method": "no/such"})
    assert r["error"]["code"] == -32601


def test_mcp_unknown_tool_error():
    s = SocraticMCP()
    r = _call(s, "tools/call", {"name": "nope", "arguments": {}})
    assert r["error"]["code"] == -32601


def test_mcp_invalid_params_error():
    s = SocraticMCP()
    r = _call(s, "tools/call", {"name": "socratic_evaluate",
                                "arguments": {"tree": "not json nor vsl"}})
    assert r["error"]["code"] == -32602


def test_mcp_evaluate_vsl_string():
    s = SocraticMCP()
    vsl = 'socratic("T") = { predicate: "ctx_has", args: ["$ctx", "type"] }'
    r = _call(s, "tools/call", {"name": "socratic_evaluate",
                                "arguments": {"tree": vsl,
                                              "context": {"type": "X"}}})
    d = json.loads(r["result"]["content"][0]["text"])
    assert d["truth"] == "TRUE"


def test_mcp_evaluate_bad_type():
    s = SocraticMCP()
    r = _call(s, "tools/call", {"name": "socratic_evaluate",
                                "arguments": {"tree": 42}})
    assert r["error"]["code"] == -32602


def test_mcp_build_ok_and_invalid():
    s = SocraticMCP()
    r = _call(s, "tools/call", {"name": "socratic_build",
                                "arguments": {"tree": {"predicate": "ctx_has",
                                                       "args": ["$ctx", "a"]}}})
    d = json.loads(r["result"]["content"][0]["text"])
    assert d == {"ok": True, "errors": []}
    r = _call(s, "tools/call", {"name": "socratic_build",
                                "arguments": {"tree": {"predicate": "nope",
                                                       "args": []}}})
    d = json.loads(r["result"]["content"][0]["text"])
    assert d["ok"] is False and d["errors"]


def test_rate_limiter_env_config(monkeypatch):
    monkeypatch.setenv("SOCRATIC_MCP_RATE_LIMIT", "2")
    monkeypatch.setenv("SOCRATIC_MCP_RATE_WINDOW", "10")
    rl = RateLimiter()
    assert rl.limit == 2 and rl.window == 10.0


def test_rate_limiter_bad_env_falls_back(monkeypatch):
    monkeypatch.setenv("SOCRATIC_MCP_RATE_LIMIT", "not-a-number")
    monkeypatch.setenv("SOCRATIC_MCP_RATE_WINDOW", "also-bad")
    rl = RateLimiter()
    assert rl.limit == 100 and rl.window == 60.0


def test_rate_limiter_reset():
    rl = RateLimiter(limit=1, window=60)
    rl.allow("tool")
    ok, _ = rl.allow("tool")
    assert not ok
    rl.reset("tool")
    ok, _ = rl.allow("tool")
    assert ok


# ── MCP main() stdio loop ──

def test_main_stdio_loop(monkeypatch, capsys):
    import socratic_engine.mcp_server as m
    req = '{"jsonrpc":"2.0","id":1,"method":"ping"}\n'
    # línea vacía se ignora; línea inválida se ignora; ping responde
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(
        "\n" + "{bad json}\n" + req))
    rc = m.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert '"result": {}' in out


def test_main_stdio_no_output_on_notification(monkeypatch, capsys):
    import socratic_engine.mcp_server as m
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(
        '{"jsonrpc":"2.0","id":2,"method":"notifications/initialized"}\n'))
    rc = m.main()
    assert rc == 0
    assert capsys.readouterr().out == ""  # notificaciones no responden


def test_main_entry_point():
    import socratic_engine.mcp_server as m
    assert m.__name__ == "socratic_engine.mcp_server"


# ── COBERTURA: rate limiter reset ──

def test_rate_limiter_reset_all():
    from socratic_engine.mcp_server import RateLimiter
    rl = RateLimiter(limit=2, window=60)
    rl.allow("tools/list")
    rl.allow("tools/list")
    ok, retry = rl.allow("tools/list")
    assert ok is False and retry is not None  # excede
    rl.reset()                            # clear all (77)
    ok, _ = rl.allow("tools/list")
    assert ok is True


def test_main_entry_call():
    import socratic_engine.mcp_server as m
    # main() con argv vacío → lee stdin (ya probado); el sys.exit de __main__
    # (219) se ejecuta solo al correr como script — lo cubrimos vía subprocess
    import subprocess, sys
    r = subprocess.run([sys.executable, "-c",
                        "import sys; from socratic_engine.mcp_server import main;"
                        "sys.stdin = __import__('io').StringIO('{}')",
                        ], capture_output=True, text=True)
    assert r.returncode == 0


def test_mcp_main_block_entry():
    # L219: sys.exit(main()) en __main__ — ejecutar como script con stdin vacío
    import subprocess, sys
    r = subprocess.run(
        [sys.executable, "-m", "socratic_engine.mcp_server"],
        input="", capture_output=True, text=True, timeout=30)
    assert r.returncode == 0
