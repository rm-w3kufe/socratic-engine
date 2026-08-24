# Roadmap — v0.1.0 → v0.2.x (completado) → v0.3.0

## ✅ Completado en v0.1.0
- [x] Motor trivaluado (TRUE/FALSE/UNKNOWN)
- [x] Separación truth/certified
- [x] Trace inverso (diagnóstico)
- [x] CLI eval-tree
- [x] MCP server básico
- [x] 14 tests unitarios
- [x] Predicados built-in (type_glob, type_prefix, etc.)

## 🎯 Objetivo v0.2.0: Maduración y Documentación

> Issue de seguimiento: https://github.com/rm-w3kufe/socratic-engine/issues/1

### Documentación
- [x] README con visión completa (The Problem + Philosophy)
- [x] docs/ONTOLOGY.md (ontología epistémica)
- [x] docs/ARCHITECTURE.md (cómo encaja con state-canon, VSM)
- [x] docs/EXAMPLES.md (casos de uso reales)

### Tests y Calidad
- [x] GitHub Actions CI (pytest en cada push, 3.10/3.11/3.12 + MCP job)
- [x] Coverage report (objetivo: >90%) — **100% real (189 tests)**, CI gate `--cov-fail-under=90` desde 1e1a893; cobertura verificada en cada push (4 jobs green)
- [x] Tests de integración con state-canon (tests/test_state_canon_integration.py: JsonStateProvider + DIALECTICAL_AND detecta drift declarado/observado)
- [x] Benchmarks de performance (benchmarks/benchmark.py: deep/wide trees,
      cache speedup ~43x en 1ms I/O, diagnose; stdlib only)

### Features
- [x] Operador dialéctico (DIALECTICAL_AND para contradicciones legítimas)
- [x] Predicados pragmáticos (feedback loops, tendencias temporales)
- [x] Cache TTL para predicados costosos
- [x] Rate limiting en MCP server

### Ecosistema
- [x] Publicar en PyPI (pip install socratic-engine) — **0.2.0 publicado** https://pypi.org/project/socratic-engine/0.2.0/ (verificado: instalación desde PyPI + dialéctico operativo)
- [x] Bridge oficial con state-canon-mcp (socratic_engine/bridge_statecanon.py: predicados canon_query/canon_matches/canon_field_equals/canon_drift — evidencia certificada desde el provider; MCP opt-in vía provider=; tests dedicados 100% cobertura)
- [x] Ejemplo end-to-end con Claude Code (examples/claude-code-end-to-end.md: .mcp.json + wrapper con bridge; **verificación en vivo PENDIENTE** — VERIFY-E2E-CLAUDE-CODE, requiere tokens Anthropic; contrato MCP verificado sin LLM en examples/mcp-contract-check.sh)
- [x] Ejemplo end-to-end con OpenCode (examples/opencode-end-to-end.md: config MCP + wrapper bridge + escenario declared/observed; contrato MCP verificado)
- [x] **Multi-bridge** (feat/multi-bridge): routing de predicados canon_* a múltiples providers por dominio
  - MultiBridge class: routing domain→provider, 6 predicados (4 existentes + canon_domains + canon_providers)
  - VsmDocProvider: parsea headers VSM del filesystem, expone como records consultables
  - SocraticMCP: acepta bridge_config o multi_bridge (backward compatible)
  - Config-driven: bridge_config.json con lazy loading de providers
  - 382 tests (46 nuevos), 0 regresiones

### Pendiente de estabilización (verificado 2026-08-19)
- [x] **Release 0.2.2 a PyPI** — el bridge + ejemplos (commits hasta 4b506db)
      NO estaban en PyPI 0.2.1 (publicado antes). Verificado: instalación limpia
      0.2.1 en venv /tmp no tenía `socratic_engine.bridge_statecanon`. 0.2.3
      sincronizado en 4 lugares: pyproject.toml + `__init__.py __version__` +
      `mcp_server.py` serverInfo + `tests/test_mcp_server.py` assert.
      **PUBLICADO 2026-08-19** https://pypi.org/project/socratic-engine/0.2.3/
      (0.2.2 corregido → 0.2.3: classifier MIT residual eliminado del metadata;
      verificado: License: Apache-2.0 + Classifier Apache Software License only)
- [ ] VERIFY-E2E-CLAUDE-CODE — verificación en vivo del ejemplo Claude Code (requiere tokens Anthropic)

## 🚀 Objetivo v0.3.0: Extensión Formal
- [ ] Lógica paraconsistente (contradicciones certificadas)
- [ ] Frame semantics (hermenéutica: significado contextual)
- [ ] Stakeholder participation graphs (ética discursiva)
- [ ] Integración formal con VSM (derivación VSM→SEF)
