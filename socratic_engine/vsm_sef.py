"""VSM → SEF derivation (roadmap v030 §3.4 — FASE 1-3).

Deriva árboles SEF canónicos desde bloques VSM y genera template files
auto-generables por sistema S1..S5. Determinístico (R10): mismos
inputs → mismos outputs, sin aleatoriedad.

FASE 1: mapping S1..S5 → kind + template evaluável por sistema
FASE 2: reglas de derivación (VSM block → SEF trees) + invariantes
FASE 3: generación de template files (.tree.vsm) parseables con
        tree.load_tree — s1_execution.tree.vsm, s2_routing.tree.vsm, ...

Mapping (roadmap §3.4):
    S1 Operations  → execution trees    (operable AND healthy)
    S2 Coordination→ routing trees      (primary OR fallback)
    S3 Control     → validation trees   (invariant AND NOT violation)
    S4 Intelligence→ hypothesis trees   (observed AND NOT refuted)
    S5 Policy      → covenant trees     (a0_hard_rules AND scope)

Slots son predicates `ctx_has` — el template es evaluável tal cual:
slots presentes → TRUE certificado; sin dato → UNKNOWN (R10).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .engine import SocraticEngine
from .tree import SocraticTreeBuilder, parse_socratic_block

#: FASE 1 — mapping sistema VSM → kind de árbol SEF.
SYSTEM_KIND: dict[str, str] = {
    "S1": "execution",
    "S2": "routing",
    "S3": "validation",
    "S4": "hypothesis",
    "S5": "covenant",
}

_SYSTEMS = tuple(SYSTEM_KIND)

#: Slots evaluables (predicate, key) por sistema. La rama negada usa
#: ctx_not_has (nunca ctx_has: sin dato ctx_has = UNKNOWN, no FALSE —
#: NOT(UNKNOWN) = UNKNOWN dejaría el template inevaluable a TRUE).
_TEMPLATE_SLOTS: dict[str, tuple[tuple[str, str], ...]] = {
    "S1": (("ctx_has", "operable"), ("ctx_has", "healthy")),
    "S2": (("ctx_has", "route_primary"), ("ctx_has", "route_fallback")),
    "S3": (("ctx_has", "invariant_holds"), ("ctx_not_has", "violation")),
    "S4": (("ctx_has", "observed"), ("ctx_not_has", "refuted")),
    "S5": (("ctx_has", "a0_hard_rules"), ("ctx_has", "scope_respected")),
}


def derive_kind(system: str) -> str:
    """FASE 1: sistema VSM → kind SEF. ValueError en sistema desconocido."""
    try:
        return SYSTEM_KIND[system]
    except KeyError:
        raise ValueError(
            f"sistema VSM desconocido: {system!r} (esperado uno de {list(SYSTEM_KIND)})"
        ) from None


def _leaf(predicate: str, key: str) -> dict[str, Any]:
    return {"predicate": predicate, "args": [key]}


def template_slot_keys(system: str) -> list[str]:
    """CLaves de contexto que alimentan los slots de un sistema."""
    derive_kind(system)  # valida sistema
    return [key for _, key in _TEMPLATE_SLOTS[system]]


def derive_tree(system: str) -> dict[str, Any]:
    """FASE 1: template SEF evaluável para un sistema (shape determinístico).

    `inject_context: True` en la raíz: el engine propaga el flag a los
    hijos (engine.py inject-context propagation) — cualquier engine
    default evalúa el template sin flags extra."""
    kind = derive_kind(system)
    (pa, ka), (pb, kb) = _TEMPLATE_SLOTS[system]
    if kind == "routing":  # S2: OR de rutas
        tree = {"op": "OR", "children": [_leaf(pa, ka), _leaf(pb, kb)]}
    elif kind == "hypothesis":  # S4: hipótesis soportada — AND, no IMPLIES:
        #   IMPLIES(UNKNOWN, TRUE)=TRUE certificaría TRUE con contexto
        #   vacío: vacuidad epistémica.
        tree = {"op": "AND", "children": [_leaf(pa, ka), _leaf(pb, kb)]}
    elif kind == "validation":  # S3: invariante Y NO violación (ctx_not_has)
        tree = {"op": "AND", "children": [_leaf(pa, ka), _leaf(pb, kb)]}
    else:  # S1 execution / S5 covenant: AND de dos slots
        tree = {"op": "AND", "children": [_leaf(pa, ka), _leaf(pb, kb)]}
    tree["inject_context"] = True
    return tree


def derive_from_vsm_block(block: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """FASE 2: VSM block (dict con claves S1..S5) → {system: {kind, tree}}.

    Claves que no son subsystemos (S3*_channel, metadatos, E:, ...) se
    ignoran: el canal S3* no es un sexto subsystemo (ratificado 2026-08-04)."""
    out: dict[str, dict[str, Any]] = {}
    for key in block:
        if key in SYSTEM_KIND:
            out[key] = {"kind": SYSTEM_KIND[key], "tree": derive_tree(key)}
    return out


def check_vsm_block_invariants(block: dict[str, Any]) -> list[str]:
    """FASE 2: invariantes del block VSM — los 5 subsystemos presentes."""
    return [
        f"missing-{s}: VSM block sin {s}"
        for s in _SYSTEMS
        if s not in block
    ]


def _count_leaves(node: dict[str, Any]) -> int:
    if "predicate" in node:
        return 1
    return sum(_count_leaves(c) for c in node.get("children", []))


def check_invariants(
    system: str,
    tree: dict[str, Any],
    engine: SocraticEngine | None = None,
) -> list[str]:
    """FASE 2: violaciones de preservación VSM→SEF (lista vacía = OK).

    Reglas: (1) sistema conocido; (2) tree == template derivado (los
    propiedades del sistema se preservan); (3) estructura válida
    (SocraticTreeBuilder: arity, no-vacío, predicados existentes);
    (4) al menos un slot evaluável."""
    try:
        derive_kind(system)
    except ValueError as e:
        return [str(e)]

    violations: list[str] = []
    if tree != derive_tree(system):
        violations.append(
            f"template-mismatch: tree de {system} no es el template SEF derivado"
        )
    eng = engine if engine is not None else SocraticEngine()
    try:
        SocraticTreeBuilder(eng).build(tree)
    except ValueError as e:
        violations.append(f"invalid-tree: {e}")
    if _count_leaves(tree) < 1:
        violations.append("empty-template: sin slots evaluables")
    return violations


# ── FASE 3 — template files ────────────────────────────────────────────────


def _vsl_scalar(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return json.dumps(str(v))


def _to_vsl(node: dict[str, Any], depth: int = 0) -> str:
    """Serializa un node SEF a notación VSL (parseable por parse_socratic_block).

    Formato espejo del docstring de parse_socratic_block: op + flag +
    children: [ un item compacto por línea ]."""
    ind = "    " * depth
    if "predicate" in node:
        parts = [f'predicate: {json.dumps(node["predicate"])}']
        if node.get("args"):
            args = ", ".join(_vsl_scalar(a) for a in node["args"])
            parts.append(f"args: [{args}]")
        if node.get("inject_context"):
            parts.append("inject_context: true")
        return "{ " + ", ".join(parts) + " }"
    flag = ", inject_context: true" if node.get("inject_context") else ""
    children = node.get("children", [])
    if not children:
        return f"{{ op: {node['op']}{flag}, children: [] }}"
    kids = ",\n".join(f"{ind}    " + _to_vsl(c, depth + 1) for c in children)
    return f"{{ op: {node['op']}{flag},\n{ind}    children: [\n{kids}\n{ind}    ]\n{ind}}}"


def template_stem(system: str) -> str:
    """s1_execution — nombre canónico (roadmap §3.4: s1_execution.tree.vsm)."""
    return f"{system.lower()}_{derive_kind(system)}"


def render_template_file(system: str) -> str:
    """FASE 3: contenido .vsm del template (header real, block socratic(...))."""
    stem = template_stem(system)
    tree = derive_tree(system)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    leaves = ", ".join(f"{p}({k})" for p, k in _TEMPLATE_SLOTS[system])
    return (
        f"⟦ {stem}_tree | TREE-TEMPLATE-v1 | vsm-1.2.1 | {now} ⟧\n"
        f"\n"
        f"@vsm 1.2.1\n"
        f"@status active\n"
        f"\n"
        f"// VSM->SEF template (roadmap v030 sec 3.4, FASE 3) — generado\n"
        f"// por socratic_engine.vsm_sef.render_template_file. NO editar a mano.\n"
        f"// system={system} kind={derive_kind(system)} slots: {leaves}\n"
        f"socratic(\"{stem}\") = {_to_vsl(tree)}\n"
        f"\n"
        f"⟦ /{stem}_tree ⟧\n"
    )


def generate_template_files(out_dir: str | Path) -> list[Path]:
    """FASE 3: escribe los 5 templates; valida invariantes antes de escribir.

    Falla ruidosamente (RuntimeError) si algún template no pasa
    check_invariants — sin teatro: no se publica un template roto."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for system in _SYSTEMS:
        violations = check_invariants(system, derive_tree(system))
        if violations:
            raise RuntimeError(
                f"{system}: invariantes violadas, no se escribe: {violations}"
            )
        path = out / f"{template_stem(system)}.tree.vsm"
        path.write_text(render_template_file(system), encoding="utf-8")
        # round-trip: lo escrito parsea de vuelta al mismo tree
        parsed = parse_socratic_block(path.read_text(encoding="utf-8"))
        if parsed != derive_tree(system):
            raise RuntimeError(f"{system}: round-trip falló en {path.name}")
        paths.append(path)
    return paths
