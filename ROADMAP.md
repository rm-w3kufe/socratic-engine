# Roadmap to v0.2.0

## ✅ Completado en v0.1.0
- [x] Motor trivaluado (TRUE/FALSE/UNKNOWN)
- [x] Separación truth/certified
- [x] Trace inverso (diagnóstico)
- [x] CLI eval-tree
- [x] MCP server básico
- [x] 14 tests unitarios
- [x] Predicados built-in (type_glob, type_prefix, etc.)

## 🎯 Objetivo v0.2.0: Maduración y Documentación

### Documentación
- [x] README con visión completa (The Problem + Philosophy)
- [x] docs/ONTOLOGY.md (ontología epistémica)
- [x] docs/ARCHITECTURE.md (cómo encaja con state-canon, VSM)
- [x] docs/EXAMPLES.md (casos de uso reales)

### Tests y Calidad
- [x] GitHub Actions CI (pytest en cada push)
- [ ] Coverage report (objetivo: >90%) — CI reporta coverage, umbral actual 50% (gate del 90% cuando la suite cubra más)
- [ ] Tests de integración con state-canon
- [ ] Benchmarks de performance

### Features
- [ ] Operador dialéctico (DIALECTICAL_AND para contradicciones legítimas)
- [ ] Predicados pragmáticos (feedback loops, tendencias temporales)
- [ ] Cache TTL para predicados costosos
- [ ] Rate limiting en MCP server

### Ecosistema
- [ ] Publicar en PyPI (pip install socratic-engine) — pendiente: sin acceso al registry
- [ ] Bridge oficial con state-canon-mcp
- [ ] Ejemplo end-to-end con Claude Code
- [ ] Ejemplo end-to-end con OpenCode

## 🚀 Objetivo v0.3.0: Extensión Formal
- [ ] Lógica paraconsistente (contradicciones certificadas)
- [ ] Frame semantics (hermenéutica: significado contextual)
- [ ] Stakeholder participation graphs (ética discursiva)
- [ ] Integración formal con VSM (derivación VSM→SEF)
