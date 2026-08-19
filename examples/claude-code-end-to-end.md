# Ejemplo end-to-end — Claude Code

Configuración del MCP server de socratic-engine en **Claude Code**
(`.mcp.json` en la raíz del proyecto). El MCP server del engine es
**transporte-agnóstico** (JSON-RPC 2.0 sobre stdio), así que el mismo
proceso sirve para Claude Code, OpenCode, o cualquier cliente MCP.

> **Estado de verificación**: este ejemplo está **documentado pero NO
> verificado en vivo** — requiere tokens de Anthropic (Claude Code), que
> no están disponibles en el entorno de desarrollo actual. La verificación
> queda como tarea pendiente (`VERIFY-E2E-CLAUDE-CODE`): ejecutar el flujo
> descrito con una sesión real de Claude Code y registrar la salida.
>
> Lo que SÍ está verificado: el contrato MCP (tools/list, tools/call,
> initialize, ping) contra el mismo server — ver `examples/mcp-contract-check.sh`.

## Requisitos

- `pip install socratic-engine` (o `pip install -e .[mcp]`)
- state-canon accesible (instalado o `~/state-canon-mcp`)
- `examples/state.json` (provider de ejemplo)

## Configuración

Crea `.mcp.json` en la raíz del proyecto:

```json
{
  "mcpServers": {
    "socratic-engine": {
      "command": "python3",
      "args": [
        "-m",
        "socratic_engine.mcp_server"
      ],
      "env": {
        "SOCRATIC_MCP_RATE_LIMIT": "100"
      }
    }
  }
}
```

## Bridge con state-canon en Claude Code

El MCP server acepta un provider opcional (R6: opt-in). En código, antes
de arrancar el server con bridge:

```python
# run_with_bridge.py
from socratic_engine.mcp_server import SocraticMCP
from state_canon.provider import JsonStateProvider

mcp = SocraticMCP(provider=JsonStateProvider("examples/state.json"))

import sys
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    import json
    try:
        req = json.loads(line)
    except json.JSONDecodeError:
        continue
    resp = mcp.handle(req)
    if resp is not None:
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()
```

y apunta `.mcp.json` a `run_with_bridge.py`:

```json
{
  "mcpServers": {
    "socratic-engine": {
      "command": "python3",
      "args": ["/path/to/run_with_bridge.py"]
    }
  }
}
```

## Prompt sugerido

> "Usa `socratic_evaluate` para certificar si el servicio `api` está
> operativo. Consulta el canon con `socratic_canon_query` y evalúa un árbol
> AND con `canon_field_equals` sobre declared_active y observed_active. Si
> hay drift, diagnostica con `socratic_diagnose` y explícame por qué no se
> puede certificar."

## Escenario esperado (con examples/state.json)

- `cache`: declared=observed=true → TRUE certificado
- `api`: declared=true, observed=false → DIALECTICAL_AND → UNKNOWN
  certificado (conflicto legítimo) — el agente NO debe inventar que "está
  caído" ni que "está operativo": la evidencia está en conflicto.