# Ejemplo end-to-end — OpenCode

Configuración del MCP server de socratic-engine en **OpenCode**
(`opencode.json`). Este ejemplo registra el MCP del engine **con el bridge
de state-canon** (opt-in): el agente puede evaluar árboles socráticos
(`socratic_evaluate`) Y consultar el canon como evidencia certificada
(`socratic_canon_query`).

## Requisitos

- `pip install socratic-engine` (o `pip install -e .[mcp]` desde el repo)
- state-canon accesible (instalado, o el repo vecino `~/state-canon-mcp`)
- Un provider JSON de ejemplo — ver `examples/state.json`

## Configuración

Añade al `opencode.json` de tu proyecto (o al de usuario):

```json
{
  "mcp": {
    "socratic-engine": {
      "type": "local",
      "enabled": true,
      "command": [
        "python3",
        "-m",
        "socratic_engine.mcp_server"
      ]
    }
  }
}
```

Para el bridge con state-canon (opt-in), arranca el server con un pequeño
wrapper que pase el provider — el MCP server expone `SocraticMCP(provider=...)`
pero aún no tiene flag CLI dedicado:

```python
# run_with_bridge.py
import sys, json
from socratic_engine.mcp_server import SocraticMCP
from state_canon.provider import JsonStateProvider

mcp = SocraticMCP(provider=JsonStateProvider("/path/to/state.json"))
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
    except json.JSONDecodeError:
        continue
    resp = mcp.handle(req)
    if resp is not None:
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()
```

y apunta `opencode.json` a `run_with_bridge.py`.

## Uso

Tools disponibles (con provider registrado):

| Tool | Ejemplo |
|---|---|
| `socratic_evaluate` | evaluar un árbol de certificación contra un contexto |
| `socratic_diagnose` | traza inversa: qué nodos rompieron la certificación |
| `socratic_build` | validar un árbol propuesto (R10.1) |
| `socratic_canon_query` | consultar el canon: `{"domain": "services", "filter": "{\"name\": \"cache\"}"}` |

## Escenario end-to-end (declared vs observed)

Con `examples/state.json` (el fixture del bridge):

```text
services:
  cache: declared_active=true, observed_active=true   → consistente
  api:   declared_active=true, observed_active=false  → DRIFT
```

Un agente que pregunta "¿puedo certificar que el servicio api está
operativo?":

1. `socratic_evaluate` con un AND (árbol de routing con `home`):
   `{"op": "AND", "children": [{"predicate": "canon_field_equals", "args": ["services", "{\"name\": \"api\"}", "declared_active", true], "home": "declared-ok"}, {"predicate": "canon_field_equals", "args": ["services", "{\"name\": \"api\"}", "observed_active", true], "home": "observed-ok"}]}`
   → `FALSE` certificado (la observación no coincide); `home` apunta al
   primer hijo TRUE (si alguno) o queda sin ruta si el árbol completo falla.

2. `socratic_diagnose` sobre el mismo árbol → identifica el nodo culpable
   (`canon_field_equals` observado).

3. Alternativa dialéctica: DIALECTICAL_AND sobre ambos → `UNKNOWN`
   certificado con `metadata.dialectical_conflict=true` — el drift se
   vuelve indeterminación productiva, no un falso binario.