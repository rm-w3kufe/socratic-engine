#!/usr/bin/env python3
"""
Quickstart demo: 3 casos que muestran el valor del motor socrático.

Ejecutar: python examples/quickstart.py
"""
from socratic_engine import SocraticEngine, Truth, PredicateResult

engine = SocraticEngine()

# ── Predicado 1: Certificado con evidencia estructural ──────────────
@engine.register("service_running")
def service_running(name: str, **kwargs) -> PredicateResult:
    """Verifica si un servicio está corriendo (ejemplo: check de /proc)."""
    # En producción: subprocess.run(["pgrep", name])
    # Aquí simulamos:
    if name == "cache":
        return PredicateResult(
            truth=Truth.TRUE,
            certified=True,  # ← Evidencia estructural
            evidence={"pid": 1234, "uptime": "2h 15m"},
            source="pgrep",
        )
    return PredicateResult(truth=Truth.FALSE, certified=True, evidence={})

# ── Predicado 2: Opinión del LLM (NO certificado) ──────────────────
@engine.register("llm_judge")
def llm_judge(question: str, evidence: str, **kwargs) -> PredicateResult:
    """El LLM opina, pero NO certifica (R10: opinion ≠ evidence)."""
    # En producción: llamada real al LLM
    return PredicateResult(
        truth=Truth.TRUE,
        certified=False,  # ← Nunca certificado, aunque diga TRUE
        evidence=evidence,
        source="llm:gpt-4",
        metadata={"question": question},
    )

# ── Predicado 3: UNKNOWN (sin evidencia) ───────────────────────────
@engine.register("schema_valid")
def schema_valid(data: dict, **kwargs) -> PredicateResult:
    """Valida schema. Si falta información → UNKNOWN."""
    if not data:
        return PredicateResult(
            truth=Truth.UNKNOWN,
            certified=False,
            evidence="No data provided",
        )
    valid = isinstance(data, dict) and "id" in data
    return PredicateResult(
        truth=Truth.TRUE if valid else Truth.FALSE,
        certified=True,
        evidence={"fields_checked": ["id"]},
    )


def demo_case_1():
    """Caso 1: Todo certificado → APPROVED."""
    print("\n" + "="*70)
    print("CASO 1: Todo verificado → APPROVED")
    print("="*70)

    tree = {
        "op": "AND",
        "children": [
            {"predicate": "service_running", "args": ["cache"]},
            {"predicate": "schema_valid", "kwargs": {"data": {"id": 123}}},
        ]
    }

    result = engine.evaluate(tree)
    print(result.explain())
    print(f"\n→ Truth: {result.truth.value}, Certified: {result.certified}")
    print(f"→ Decisión: {'APPROVED' if result.certified else 'BLOCKED'}")


def demo_case_2():
    """Caso 2: LLM dice TRUE pero no certifica → UNKNOWN."""
    print("\n" + "="*70)
    print("CASO 2: LLM opina pero no certifica → UNKNOWN")
    print("="*70)

    tree = {
        "op": "AND",
        "children": [
            {"predicate": "service_running", "args": ["cache"]},
            {"predicate": "llm_judge", "kwargs": {
                "question": "¿Es seguro desplegar?",
                "evidence": "Tráfico al 45%"
            }},
        ]
    }

    result = engine.evaluate(tree)
    print(result.explain())
    print(f"\n→ Truth: {result.truth.value}, Certified: {result.certified}")
    print(f"→ Decisión: {'APPROVED' if result.certified else 'BLOCKED'}")
    print(f"→ Razón: Todo verificado, pero falta certificación humana")


def demo_case_3():
    """Caso 3: Fallo con trace inverso (diagnóstico)."""
    print("\n" + "="*70)
    print("CASO 3: Fallo con diagnóstico → BLOCKED + TRACE")
    print("="*70)

    tree = {
        "op": "AND",
        "children": [
            {"predicate": "service_running", "args": ["database"]},  # ← FALSE
            {"predicate": "schema_valid", "kwargs": {"data": {"id": 456}}},
            {"predicate": "llm_judge", "kwargs": {
                "question": "¿Hay riesgos de seguridad?",
                "evidence": "Ninguno detectado"
            }},
        ]
    }

    result = engine.evaluate(tree)
    print(result.explain())

    # Trace inverso: qué falló exactamente
    from socratic_engine.engine import find_failure_traces
    failures = find_failure_traces(result)

    print(f"\n→ Truth: {result.truth.value}, Certified: {result.certified}")
    print(f"→ Diagnóstico ({len(failures)} fallos):")
    for f in failures:
        print(f"   • {f}")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("SOCRATIC ENGINE — Quickstart Demo")
    print("Externalized epistemic scaffolding for AI agents")
    print("="*70)

    demo_case_1()
    demo_case_2()
    demo_case_3()

    print("\n" + "="*70)
    print("Para más ejemplos, ver tests/ y docs/ONTOLOGY.md")
    print("="*70 + "\n")
