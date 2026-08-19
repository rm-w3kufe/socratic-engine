#!/usr/bin/env bash
# Verifica el contrato MCP del socratic-engine server SIN cliente LLM
# (JSON-RPC 2.0 sobre stdio). Esto cubre la parte verificable del ejemplo
# end-to-end: el server habla el protocolo correcto; lo único que requiere
# tokens es la sesión LLM real (Claude Code / OpenCode).
#
# Uso: bash examples/mcp-contract-check.sh
set -euo pipefail

PYTHON=${PYTHON:-python3}
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== 1. initialize ==="
echo '{"jsonrpc":"2.0","id":1,"method":"initialize"}' | \
  "$PYTHON" -m socratic_engine.mcp_server 2>/dev/null | \
  "$PYTHON" -c "
import sys, json
r = json.load(sys.stdin)
assert r['result']['protocolVersion'] == '2024-11-05', r
assert r['result']['serverInfo']['name'] == 'socratic-engine', r
print('  OK:', r['result']['serverInfo'])
"

echo "=== 2. tools/list ==="
echo '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | \
  "$PYTHON" -m socratic_engine.mcp_server 2>/dev/null | \
  "$PYTHON" -c "
import sys, json
r = json.load(sys.stdin)
names = [t['name'] for t in r['result']['tools']]
assert 'socratic_evaluate' in names and 'socratic_build' in names, names
print('  OK tools:', names)
"

echo "=== 3. tools/call socratic_evaluate (JSON tree) ==="
printf '%s\n' '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"socratic_evaluate","arguments":{"tree":{"predicate":"type_prefix","args":["SPEC-1","SPEC-"]}}}}' | \
  "$PYTHON" -m socratic_engine.mcp_server 2>/dev/null | \
  "$PYTHON" -c "
import sys, json
r = json.load(sys.stdin)
text = r['result']['content'][0]['text']
d = json.loads(text)
assert d['truth'] == 'TRUE' and d['certified'] is True, d
print('  OK: truth=', d['truth'], 'certified=', d['certified'])
"

echo "=== 4. tools/call socratic_evaluate (VSL tree with routing) ==="
TREE_VSL='socratic("X") = { op: "OR", children: [ { predicate: "ctx_has", args: ["$ctx", "type"], home: "ok" } ] }'
printf '%s\n' "{\"jsonrpc\":\"2.0\",\"id\":4,\"method\":\"tools/call\",\"params\":{\"name\":\"socratic_evaluate\",\"arguments\":{\"tree\":$(python3 -c "import json,sys; print(json.dumps(sys.argv[1]))" "$TREE_VSL"),\"context\":{\"type\":\"test\"}}}}" | \
  "$PYTHON" -m socratic_engine.mcp_server 2>/dev/null | \
  "$PYTHON" -c "
import sys, json
r = json.load(sys.stdin)
text = r['result']['content'][0]['text']
d = json.loads(text)
assert d['truth'] == 'TRUE', d
assert d['home'] == 'ok', d
print('  OK: VSL tree ->', d['truth'], 'home=', d['home'])
"

echo "=== 5. ping ==="
echo '{"jsonrpc":"2.0","id":5,"method":"ping"}' | \
  "$PYTHON" -m socratic_engine.mcp_server 2>/dev/null | \
  "$PYTHON" -c "
import sys, json
r = json.load(sys.stdin)
assert r['result'] == {}, r
print('  OK: pong')
"

echo ""
echo "✓ Contrato MCP verificado (initialize / tools/list / evaluate JSON+VSL / ping)"
echo "  Pendiente (requiere tokens): sesión LLM real — VERIFY-E2E-CLAUDE-CODE"