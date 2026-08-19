"""
socratic_engine.engine — motor socrático recursivo con semántica epistemológica.

Lógica TRIVALUADA (TRUE/FALSE/UNKNOWN), certificación de evidencia
(certified: evidencia estructural ≠ opinión) y rastro completo de
razonamiento (Evaluation.explain()).

El motor NO contiene lógica de dominio: solo evalúa op/children/predicate.
El cuestionamiento atómico vive en predicates; cada nivel declara SU árbol
(el motor recursa con el mismo contrato sin saber la profundidad).

R10 (LLM boundary): un predicate puede retornar PredicateResult(certified=False)
— el LLM opina, no certifica. Solo la evidencia estructural certifica.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
import fnmatch
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union


# ============================================================
# EPISTEMIC TYPES
# ============================================================

class Truth(Enum):
    """Lógica trivaluada: el UNKNOWN es tan importante como TRUE/FALSE."""
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


@dataclass
class Evaluation:
    """
    Resultado rico de una evaluación recursiva.

    Conserva:
      - truth:       valor lógico trivaluado
      - certified:   si la verdad está respaldada por evidencia suficiente
      - evidence:    dato crudo que sustenta la evaluación
      - source:      origen de la evaluación (predicado, operador, literal)
      - children:    sub-evaluaciones recursivas (árbol de razonamiento)
      - context:     estado contextual al momento de evaluar
      - metadata:    datos arbitrarios adicionales
    """
    truth: Truth
    certified: bool = False
    evidence: Any = None
    source: Optional[str] = None
    children: List["Evaluation"] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_true(self) -> bool:
        return self.truth == Truth.TRUE

    @property
    def is_false(self) -> bool:
        return self.truth == Truth.FALSE

    @property
    def is_unknown(self) -> bool:
        return self.truth == Truth.UNKNOWN

    def explain(self, indent: int = 0) -> str:
        """Genera una representación textual del árbol de razonamiento."""
        prefix = "  " * indent
        cert_mark = "✓" if self.certified else "✗"
        lines = [f"{prefix}{self.source or 'node'} → {self.truth.value} [{cert_mark}]"]
        if self.evidence is not None:
            lines.append(f"{prefix}  evidence: {self.evidence}")
        for child in self.children:
            lines.append(child.explain(indent + 1))
        return "\n".join(lines)


@dataclass
class PredicateResult:
    """
    Retorno enriquecido para predicados que quieren aportar evidencia.
    Los predicados también pueden retornar bool simple (compatibilidad).
    """
    truth: Truth
    certified: bool = False
    evidence: Any = None
    source: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# Tipo flexible: un predicado puede retornar bool o PredicateResult
Predicate = Callable[..., Union[bool, PredicateResult]]


class PredicateCache:
    """Cache con TTL para predicados costosos (v0.2.0).

    Semántica: la certificación exige evidencia FRESCA — un resultado
    cacheado es evidencia histórica, no presente. Por eso el cache nunca
    devuelve certified=True como si fuera recién medido; el predicado
    original es quien decide la certificación. Este cache es un
    optimizador para predicados caros (I/O, red, MCP), no un sustituto de
    la verificación.

    TTL por defecto: 5s (los sistemas vivos cambian rápido). Clave =
    (nombre, args serializables). No cachea resultados UNKNOWN: el
    UNKNOWN es "no se pudo decidir ahora" — reintentar es barato y puede
    ser la única vía a una decisión.
    """

    def __init__(self, default_ttl: float = 5.0):
        self.default_ttl = default_ttl
        self._entries: Dict[tuple, tuple] = {}  # key → (expires_at, result)

    def get(self, key: tuple) -> Any:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, result = entry
        if time.monotonic() > expires_at:
            del self._entries[key]
            return None
        return result

    def set(self, key: tuple, result: Any, ttl: Optional[float] = None):
        self._entries[key] = (
            time.monotonic() + (ttl if ttl is not None else self.default_ttl),
            result,
        )

    def clear(self):
        self._entries.clear()


def cached(ttl: Optional[float] = None, cache: Optional[PredicateCache] = None):
    """Decorador: cachea un predicado por (args, kwargs serializables).

    Uso:
        @engine.register("expensive_check")
        @cached(ttl=2.0)
        def expensive_check(name, **kw):
            ...

    El cache se adjunta al engine (engine.cache) si no se pasa uno
    explícito, y se resuelve en el momento del registro — por eso el
    decorador debe usarse DEBAJO de @engine.register y captura `cache`
    desde el engine en el registro.
    """
    def decorator(func: Predicate) -> Predicate:
        func.__socratic_cached__ = True
        func.__socratic_ttl__ = ttl
        func.__socratic_cache_ref__ = cache
        return func
    return decorator


# ============================================================
# SOCRATIC ENGINE (Fusionado)
# ============================================================

class SocraticEngine:
    """
    Motor recursivo agnóstico con semántica epistemológica.

    No contiene lógica de dominio. Solo evalúa árboles de verdad/falsedad
    y conserva el rastro completo del razonamiento.
    """

    OPERATORS = {"AND", "OR", "NOT", "XOR", "IMPLIES", "DIALECTICAL_AND"}

    def __init__(self):
        self.predicates: Dict[str, Predicate] = {}
        self.cache: PredicateCache = PredicateCache()
        self._register_builtins()

    # --------------------------------------------------------
    # Registro de predicados
    # --------------------------------------------------------

    def register(self, name: str):
        """Registra una función externa. Puede retornar bool o PredicateResult.
        Si la función está decorada con @cached, se envuelve con el cache
        del engine (TTL resuelto en el registro)."""
        def decorator(func: Predicate):
            if getattr(func, "__socratic_cached__", False):
                cache_ref = func.__socratic_cache_ref__ or self.cache
                ttl = func.__socratic_ttl__
                original = func

                def wrapped(*args, **kwargs):
                    try:
                        key = (name, json.dumps(args, default=str),
                               json.dumps(kwargs, default=str, sort_keys=True))
                    except (TypeError, ValueError):
                        # args no serializables → no cachear, llamar directo
                        return original(*args, **kwargs)
                    hit = cache_ref.get(key)
                    if hit is not None:
                        # Evidencia de cache = evidencia histórica: marcar
                        # para que el resultado no mienta sobre su frescura.
                        if isinstance(hit, PredicateResult):
                            hit = PredicateResult(
                                truth=hit.truth, certified=hit.certified,
                                evidence=hit.evidence, source=hit.source,
                                metadata=dict(hit.metadata or {}, cached=True),
                            )
                        return hit
                    result = original(*args, **kwargs)
                    # NO cachear UNKNOWN: reintentar es barato y puede ser
                    # la única vía a una decisión.
                    if isinstance(result, PredicateResult) and result.truth == Truth.UNKNOWN:
                        return result
                    cache_ref.set(key, result, ttl)
                    return result
                wrapped.__name__ = func.__name__
                wrapped.__doc__ = func.__doc__
                wrapped.__socratic_cache_wrapper__ = True
                self.predicates[name] = wrapped
            else:
                self.predicates[name] = func
            return func
        return decorator

    # Alias de compatibilidad (API previa)
    register_predicate = register

    def _register_builtins(self):
        """Predicados de dominio DETERMINISTAS: preguntas que un nivel puede
        hacer sobre un documento. Registrados aquí = instrumento compartido
        (classify.py y el daemon write-time usan el MISMO registro — R16, sin
        drift). Retornan PredicateResult(certified=True): son evidencia
        estructural verificable (fnmatch/startswith/regex), NO opinión."""

        @self.register("type_glob")
        def type_glob(type_: str, pattern: str, **kw) -> PredicateResult:
            """¿El TYPE coincide (fnmatch)? — la primitiva clásica.
            SIN SUJETO NO HAY JUICIO (R10): type_ vacío/ausente → UNKNOWN
            (no se pudo decidir), NO FALSE — un doc sin TYPE no "no coincide",
            no se sabe. La frontera entre decidible e indecidible."""
            if not type_:
                return PredicateResult(
                    truth=Truth.UNKNOWN, certified=False,
                    evidence={"missing": "type_", "pattern": pattern},
                    source="type_glob",
                )
            matched = any(p.strip() and fnmatch.fnmatch(type_, p.strip())
                          for p in pattern.split("|"))
            return PredicateResult(
                truth=Truth.TRUE if matched else Truth.FALSE,
                certified=True,
                evidence={"type": type_, "pattern": pattern},
                source="type_glob",
            )

        @self.register("type_prefix")
        def type_prefix(type_: str, prefix: str, **kw) -> PredicateResult:
            """¿El TYPE empieza por prefix? — EL patrón común (vsl-lang-*).
            SIN SUJETO NO HAY JUICIO: type_ vacío → UNKNOWN, no FALSE."""
            if not type_:
                return PredicateResult(
                    truth=Truth.UNKNOWN, certified=False,
                    evidence={"missing": "type_", "prefix": prefix},
                    source="type_prefix",
                )
            ok = type_.startswith(prefix)
            return PredicateResult(
                truth=Truth.TRUE if ok else Truth.FALSE,
                certified=True,
                evidence={"type": type_, "prefix": prefix},
                source="type_prefix",
            )

        @self.register("type_regex")
        def type_regex(type_: str, pattern: str, **kw) -> PredicateResult:
            """¿El TYPE matchea un regex estructural (S1-([A-Z]+)-CONTRACT)?
            SIN SUJETO NO HAY JUICIO: type_ vacío → UNKNOWN."""
            if not type_:
                return PredicateResult(
                    truth=Truth.UNKNOWN, certified=False,
                    evidence={"missing": "type_", "pattern": pattern},
                    source="type_regex",
                )
            try:
                ok = re.search(pattern, type_) is not None
            except re.error:
                return PredicateResult(truth=Truth.FALSE, certified=False,
                                       evidence={"regex_error": pattern},
                                       source="type_regex")
            return PredicateResult(
                truth=Truth.TRUE if ok else Truth.FALSE,
                certified=True,
                evidence={"type": type_, "pattern": pattern},
                source="type_regex",
            )

        @self.register("type_has")
        def type_has(type_: str, token: str, **kw) -> PredicateResult:
            """¿El TYPE contiene el token en cualquier posición?
            SIN SUJETO NO HAY JUICIO: type_ vacío → UNKNOWN."""
            if not type_:
                return PredicateResult(
                    truth=Truth.UNKNOWN, certified=False,
                    evidence={"missing": "type_", "token": token},
                    source="type_has",
                )
            ok = token in type_
            return PredicateResult(
                truth=Truth.TRUE if ok else Truth.FALSE,
                certified=True,
                evidence={"type": type_, "token": token},
                source="type_has",
            )

        @self.register("doc_has_status")
        def doc_has_status(doc, status: str, **kw) -> PredicateResult:
            """¿El doc declara @status == status? (doc = path)"""
            ok = status in doc.get("statuses", [])
            return PredicateResult(
                truth=Truth.TRUE if ok else Truth.FALSE,
                certified=True,
                evidence={"doc": doc, "status": status},
                source="doc_has_status",
            )

        @self.register("ctx_has")
        def ctx_has(ctx, key: str, **kw) -> PredicateResult:
            """¿El contexto provee la clave? — el GUARDIÁN del trivaluado para
            shells. Si el contexto carece de la clave (p.ej. un doc sin TYPE
            leíble), la respuesta es UNKNOWN (no se pudo decidir), NO FALSE:
            el shell debe enrutar a '?' visible (R9), no al else_home
            silencioso. Esta es la frontera R10: sin dato no hay evidencia."""
            if not isinstance(ctx, dict) or key not in ctx or ctx[key] in (None, ""):
                return PredicateResult(
                    truth=Truth.UNKNOWN, certified=False,
                    evidence={"missing_key": key}, source="ctx_has",
                )
            return PredicateResult(
                truth=Truth.TRUE, certified=True,
                evidence={"ctx": ctx, "key": key}, source="ctx_has",
            )

        # ── PREDICADOS PRAGMÁTICOS (v0.2.0): preguntas sobre comportamiento
        # temporal y estructural, NO sobre el contenido estático del doc.
        # Siguen la misma disciplina R10: sin serie/topología no hay juicio
        # (UNKNOWN), y la evidencia es la serie completa (auditable).

        @self.register("trend_up")
        def trend_up(series, min_delta: float = 0.0, **kw) -> PredicateResult:
            """¿La serie temporal está creciendo de forma sostenida? — la
            primitiva de tendencia. Retorna TRUE si el último punto supera
            el primero por min_delta y la serie no tiene caídas > 1/3 del
            rango (tendencia, no ruido). UNKNOWN si la serie es demasiado
            corta (< 2 puntos) o no numérica — sin datos no hay tendencia."""
            if not isinstance(series, (list, tuple)) or len(series) < 2:
                return PredicateResult(
                    truth=Truth.UNKNOWN, certified=False,
                    evidence={"series": series, "reason": "insufficient"},
                    source="trend_up",
                )
            try:
                vals = [float(v) for v in series]
            except (TypeError, ValueError):
                return PredicateResult(
                    truth=Truth.UNKNOWN, certified=False,
                    evidence={"series": series, "reason": "non_numeric"},
                    source="trend_up",
                )
            first, last = vals[0], vals[-1]
            if last - first < min_delta:
                return PredicateResult(
                    truth=Truth.FALSE, certified=True,
                    evidence={"series": vals, "first": first, "last": last},
                    source="trend_up",
                )
            rng = max(vals) - min(vals)
            # caída > 1/3 del rango entre puntos consecutivos = ruido, no tendencia
            for a, b in zip(vals, vals[1:]):
                if b < a - (rng / 3 if rng > 0 else abs(a)):
                    return PredicateResult(
                        truth=Truth.FALSE, certified=True,
                        evidence={"series": vals, "first": first, "last": last,
                                  "drop": (a, b)},
                        source="trend_up",
                    )
            return PredicateResult(
                truth=Truth.TRUE, certified=True,
                evidence={"series": vals, "first": first, "last": last},
                source="trend_up",
            )

        @self.register("trend_down")
        def trend_down(series, min_delta: float = 0.0, **kw) -> PredicateResult:
            """¿La serie temporal está cayendo de forma sostenida? — la
            primitiva de decremento (espejo de trend_up, con los mismos
            criterios de ruido)."""
            if not isinstance(series, (list, tuple)) or len(series) < 2:
                return PredicateResult(
                    truth=Truth.UNKNOWN, certified=False,
                    evidence={"series": series, "reason": "insufficient"},
                    source="trend_down",
                )
            try:
                vals = [float(v) for v in series]
            except (TypeError, ValueError):
                return PredicateResult(
                    truth=Truth.UNKNOWN, certified=False,
                    evidence={"series": series, "reason": "non_numeric"},
                    source="trend_down",
                )
            first, last = vals[0], vals[-1]
            if first - last < min_delta:
                return PredicateResult(
                    truth=Truth.FALSE, certified=True,
                    evidence={"series": vals, "first": first, "last": last},
                    source="trend_down",
                )
            rng = max(vals) - min(vals)
            for a, b in zip(vals, vals[1:]):
                if b > a + (rng / 3 if rng > 0 else abs(a)):
                    return PredicateResult(
                        truth=Truth.FALSE, certified=True,
                        evidence={"series": vals, "first": first, "last": last,
                                  "rise": (a, b)},
                        source="trend_down",
                    )
            return PredicateResult(
                truth=Truth.TRUE, certified=True,
                evidence={"series": vals, "first": first, "last": last},
                source="trend_down",
            )

        @self.register("feedback_loop")
        def feedback_loop(topology, target: str, **kw) -> PredicateResult:
            """¿Hay un ciclo de retroalimentación en la topología que incluye
            al nodo objetivo? — la primitiva estructural de loops. La
            topología es un dict {nodo: [vecinos]}; retorna TRUE si existe un
            camino cerrado (de target a target) de longitud >= 2. UNKNOWN si
            la topología es inválida o el target no está presente."""
            if not isinstance(topology, dict) or not isinstance(target, str) or target not in topology:
                return PredicateResult(
                    truth=Truth.UNKNOWN, certified=False,
                    evidence={"topology": topology, "target": target,
                              "reason": "invalid_or_absent"},
                    source="feedback_loop",
                )
            adj = {k: (list(v) if isinstance(v, (list, tuple, set)) else [])
                   for k, v in topology.items()}
            # BFS desde target buscando volver a target (longitud >= 2)
            from collections import deque
            seen_paths = set()
            dq = deque()
            for nxt in adj.get(target, []):
                if nxt == target:
                    continue  # self-loop de longitud 1 no cuenta
                dq.append((nxt, (target, nxt)))
            while dq:
                node, path = dq.popleft()
                if node == target:
                    return PredicateResult(
                        truth=Truth.TRUE, certified=True,
                        evidence={"cycle": list(path), "target": target},
                        source="feedback_loop",
                    )
                for nxt in adj.get(node, []):
                    if (node, nxt) in seen_paths:
                        continue
                    seen_paths.add((node, nxt))
                    dq.append((nxt, path + (nxt,)))
            return PredicateResult(
                truth=Truth.FALSE, certified=True,
                evidence={"target": target, "no_cycle": True},
                source="feedback_loop",
            )

    # --------------------------------------------------------
    # Evaluación recursiva principal
    # --------------------------------------------------------

    def evaluate(
        self,
        node: Any,
        context: Optional[Dict[str, Any]] = None,
    ) -> Evaluation:
        ctx = context or {}

        # --- CASO BASE: booleano literal ---
        if isinstance(node, bool):
            return Evaluation(
                truth=Truth.TRUE if node else Truth.FALSE,
                certified=False,  # Literal sin evidencia = no certificado
                source="literal",
                context=ctx.copy(),
            )

        # --- PREDICADO: cuestionamiento atómico ---
        if isinstance(node, dict) and "predicate" in node:
            return self._evaluate_predicate(node, ctx)

        # --- OPERADOR: composición lógica recursiva ---
        if isinstance(node, dict) and "op" in node:
            return self._evaluate_operator(node, ctx)

        raise ValueError(
            f"Nodo inválido: debe ser bool, o dict con 'predicate'/'op'. Recibido: {node}"
        )

    # --------------------------------------------------------
    # Evaluación de predicados
    # --------------------------------------------------------

    def _evaluate_predicate(
        self,
        node: Dict[str, Any],
        ctx: Dict[str, Any],
    ) -> Evaluation:
        name = node["predicate"]
        if name not in self.predicates:
            raise ValueError(f"Predicado no registrado: {name}")

        # Resolver argumentos recursivamente
        # Resolver argumentos recursivamente — SOLO si el dict es un NODO
        # (tiene 'predicate'/'op'). Un dict de DATOS (p.ej. {"id": 123}
        # pasado a un predicado como kwargs) NO es un nodo lógico: se pasa
        # tal cual, no se evalúa. Antes cualquier dict se evaluaba como
        # nodo → ValueError en predicados con datos estructurados
        # (quickstart demo case 1, 2026-08-18).
        def _maybe_eval(v: Any) -> Any:
            if isinstance(v, dict) and ("predicate" in v or "op" in v):
                return self.evaluate(v, ctx).is_true
            return v

        resolved_args = [_maybe_eval(arg) for arg in node.get("args", [])]
        resolved_kwargs = {
            k: _maybe_eval(v) for k, v in node.get("kwargs", {}).items()
        }

        # Resolución de tokens: "$type" → TYPE del doc (sujeto del
        # cuestionamiento, inyectado por tree_home). "$ctx" → contexto
        # completo. Agnóstico: es un simple lookup, el motor no sabe qué
        # es un TYPE.
        def _resolve(a: Any) -> Any:
            if isinstance(a, str) and a.startswith("$"):
                if a == "$ctx":
                    return ctx
                return ctx.get(a[1:], a)
            return a

        resolved_args = [_resolve(a) for a in resolved_args]
        resolved_kwargs = {k: _resolve(v) for k, v in resolved_kwargs.items()}

        # Inyectar contexto si se solicita explícitamente
        if node.get("inject_context", False):
            resolved_kwargs["_context"] = ctx

        # Ejecutar predicado
        raw_result = self.predicates[name](*resolved_args, **resolved_kwargs)

        # Normalizar: bool → PredicateResult automático
        if isinstance(raw_result, bool):
            result = PredicateResult(
                truth=Truth.TRUE if raw_result else Truth.FALSE,
                certified=False,
                source=name,
            )
        elif isinstance(raw_result, PredicateResult):
            result = raw_result
            if result.source is None:
                result.source = name
        else:
            raise TypeError(
                f"Predicado '{name}' debe retornar bool o PredicateResult, "
                f"no {type(raw_result).__name__}"
            )

        return Evaluation(
            truth=result.truth,
            certified=result.certified,
            evidence=result.evidence,
            source=result.source,
            context=ctx.copy(),
            metadata=result.metadata,
        )

    # --------------------------------------------------------
    # Evaluación de operadores lógicos
    # --------------------------------------------------------

    def _evaluate_operator(
        self,
        node: Dict[str, Any],
        ctx: Dict[str, Any],
    ) -> Evaluation:
        op = node["op"].upper()
        if op not in self.OPERATORS:
            raise ValueError(f"Operador desconocido: {op}")

        children_nodes = node.get("children", [])
        children = [self.evaluate(child, ctx) for child in children_nodes]

        truth = self._apply_operator(op, children)

        # Certificación del operador: solo si TODOS los hijos relevantes están certificados
        certified = self._compute_operator_certification(op, children)

        # Metadata dialéctica: cuando hay conflicto certificado, documentar
        # exactamente la tensión (qué hijos afirman, cuáles niegan, con qué
        # evidencia) para que el nivel superior pueda sintetizar.
        metadata: Dict[str, Any] = {}
        if op == "DIALECTICAL_AND":
            affirm = [c for c in children if c.is_true]
            deny = [c for c in children if c.is_false]
            if affirm and deny:
                metadata["dialectical_conflict"] = True
                metadata["thesis"] = [
                    {"source": c.source, "evidence": c.evidence} for c in affirm
                ]
                metadata["antithesis"] = [
                    {"source": c.source, "evidence": c.evidence} for c in deny
                ]

        return Evaluation(
            truth=truth,
            certified=certified,
            source=f"op:{op}",
            children=children,
            context=ctx.copy(),
            metadata=metadata,
        )

    @staticmethod
    def _apply_operator(op: str, children: List[Evaluation]) -> Truth:
        truths = [c.truth for c in children]

        if op == "AND":
            if any(t == Truth.FALSE for t in truths):
                return Truth.FALSE
            if any(t == Truth.UNKNOWN for t in truths):
                return Truth.UNKNOWN
            return Truth.TRUE

        if op == "DIALECTICAL_AND":
            # Dialéctico: la contradicción certificada (tesis TRUE + antítesis
            # FALSE, ambas con evidencia) NO es rechazo ni aprobación — es
            # indeterminación productiva. El truth se decide aquí; la metadata
            # del conflicto la inyecta _evaluate_operator.
            if any(t == Truth.UNKNOWN for t in truths):
                return Truth.UNKNOWN
            if all(t == Truth.TRUE for t in truths):
                return Truth.TRUE
            if all(t == Truth.FALSE for t in truths):
                return Truth.FALSE
            # Mezcla TRUE+FALSE (todos decididos): conflicto → no se decide
            # en este nivel; la síntesis es del nivel superior.
            return Truth.UNKNOWN

        if op == "OR":
            if any(t == Truth.TRUE for t in truths):
                return Truth.TRUE
            if any(t == Truth.UNKNOWN for t in truths):
                return Truth.UNKNOWN
            return Truth.FALSE

        if op == "NOT":
            if len(children) != 1:
                raise ValueError("NOT requiere exactamente un hijo")
            mapping = {Truth.TRUE: Truth.FALSE, Truth.FALSE: Truth.TRUE, Truth.UNKNOWN: Truth.UNKNOWN}
            return mapping[children[0].truth]

        if op == "XOR":
            if any(t == Truth.UNKNOWN for t in truths):
                return Truth.UNKNOWN
            return Truth.TRUE if sum(t == Truth.TRUE for t in truths) == 1 else Truth.FALSE

        if op == "IMPLIES":
            if len(children) != 2:
                raise ValueError("IMPLIES requiere exactamente dos hijos")
            ante, cons = children
            if ante.truth == Truth.FALSE:
                return Truth.TRUE
            if ante.truth == Truth.UNKNOWN:
                return Truth.TRUE if cons.truth == Truth.TRUE else Truth.UNKNOWN
            return cons.truth

        raise ValueError(f"Operador no implementado: {op}")

    @staticmethod
    def _compute_operator_certification(op: str, children: List[Evaluation]) -> bool:
        """
        Regla de certificación por operador:
          AND  → todos los hijos deben estar certificados
          OR   → al menos un hijo TRUE debe estar certificado
          NOT  → el hijo debe estar certificado
          XOR  → ambos hijos deben estar certificados
          IMPLIES → antecedente y consecuente deben estar certificados
        """
        if not children:
            return False

        if op == "AND":
            return all(c.certified for c in children)

        if op == "DIALECTICAL_AND":
            # Si hay conflicto decidido (mezcla TRUE+FALSE) y TODOS los hijos
            # están certificados, la contradicción misma es un hecho
            # certificado: certified=True con truth=UNKNOWN (evidencia en
            # conflicto ≠ falta de evidencia). Si falta certificación, se
            # aplica la regla AND.
            has_conflict = (
                any(c.is_true for c in children)
                and any(c.is_false for c in children)
            )
            if has_conflict:
                return all(c.certified for c in children)
            return all(c.certified for c in children)

        if op == "OR":
            true_children = [c for c in children if c.is_true]
            return any(c.certified for c in true_children) if true_children else False

        if op in ("NOT", "XOR", "IMPLIES"):
            return all(c.certified for c in children)

        return False

    # --------------------------------------------------------
    # Diagnóstico inverso (trace de fallos de certificación)
    # --------------------------------------------------------

    def diagnose(self, node: Any, context: Optional[Dict[str, Any]] = None) -> List[FailureTrace]:
        """
        Evalúa el árbol y retorna SOLO los nodos que causaron el fallo de certificación.

        Uso típico en un hook de agente:
            result = engine.evaluate(tree, ctx)
            if not result.certified:
                failures = engine.diagnose(tree, ctx)
                feedback = "\n".join(str(f) for f in failures)
                # Enviar feedback al agente para que refine su intención
        """
        evaluation = self.evaluate(node, context)
        if evaluation.certified:
            return []
        return find_failure_traces(evaluation)


# ── TRACE INVERSO: Diagnóstico de Fallos de Certificación (rmw3, 2026-08-17) ─
# La observabilidad S5: cuando un gate no certifica, extraer SOLO los nodos
# que causaron el fallo, respetando la semántica del operador (no todos los
# hijos no-certificados son culpables).

@dataclass
class FailureTrace:
    """
    Representa un nodo específico que contribuyó al fallo de certificación.
    """
    path: List[str]           # Ruta desde la raíz: ["op:AND", "predicate:has_tests"]
    source: str               # Nombre del predicado u operador
    truth: Truth              # Valor lógico del nodo
    certified: bool           # Estado de certificación
    evidence: Any             # Evidencia disponible (si hay)
    reason: str               # Explicación humana de por qué este nodo es parte del problema
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        path_str = " → ".join(self.path)
        cert = "✓" if self.certified else "✗"
        return f"[{cert}] {path_str} | {self.truth.value} | {self.reason}"


def find_failure_traces(evaluation: Evaluation, path: Optional[List[str]] = None) -> List[FailureTrace]:
    """
    Recorre el árbol de Evaluation y extrae SOLO los nodos que causaron
    que la certificación fallara, respetando la semántica de cada operador.

    Esto es el "trace inverso": de la conclusión fallida hacia las causas raíz.
    """
    if path is None:
        path = []

    current_path = path + [evaluation.source or "root"]
    traces: List[FailureTrace] = []

    # Si este nodo está certificado, no es parte del problema
    if evaluation.certified:
        return traces

    # --- NODO HOJA (predicado o literal): es la causa raíz ---
    if not evaluation.children:
        reason = _leaf_failure_reason(evaluation)
        traces.append(FailureTrace(
            path=current_path,
            source=evaluation.source or "unknown",
            truth=evaluation.truth,
            certified=evaluation.certified,
            evidence=evaluation.evidence,
            reason=reason,
            metadata=evaluation.metadata,
        ))
        return traces

    # --- NODO OPERADOR: determinar cuáles hijos son culpables ---
    op = evaluation.source.replace("op:", "") if evaluation.source and evaluation.source.startswith("op:") else None

    if op:
        guilty_children = _identify_guilty_children(op, evaluation.children)
    else:
        # Fallback: si no reconocemos el operador, todos los hijos no-certificados son sospechosos
        guilty_children = [c for c in evaluation.children if not c.certified]

    # Recursión hacia los hijos culpables
    for child in guilty_children:
        traces.extend(find_failure_traces(child, current_path))

    # Si ningún hijo produjo traces pero el operador mismo no está certificado,
    # el problema es la composición lógica misma
    if not traces:
        traces.append(FailureTrace(
            path=current_path,
            source=evaluation.source or "unknown",
            truth=evaluation.truth,
            certified=False,
            evidence=None,
            reason=f"Operador {op} no certificado aunque sus hijos individuales podrían estarlo",
        ))

    return traces


def _leaf_failure_reason(evaluation: Evaluation) -> str:
    """Genera una explicación legible para un nodo hoja que falló."""
    if evaluation.truth == Truth.FALSE:
        return f"El predicado '{evaluation.source}' retornó FALSE"
    if evaluation.truth == Truth.UNKNOWN:
        return f"El predicado '{evaluation.source}' retornó UNKNOWN (evidencia insuficiente)"
    if evaluation.truth == Truth.TRUE and not evaluation.certified:
        src = evaluation.source or "unknown"
        return f"'{src}' dice TRUE pero NO está certificado (falta evidencia estructural)"
    return f"Estado inesperado: {evaluation.truth.value}, certified={evaluation.certified}"


def _identify_guilty_children(op: str, children: List[Evaluation]) -> List[Evaluation]:
    """
    Determina cuáles hijos son RESPONSABLES del fallo según la semántica del operador.
    No todos los hijos no-certificados son culpables.
    """
    if op == "AND":
        # En AND, CUALQUIER hijo no-certificado o FALSE/UNKNOWN es culpable
        return [c for c in children if not c.certified]

    if op == "DIALECTICAL_AND":
        # Un conflicto dialéctico certificado NO tiene hijos "culpables"
        # individuales: la contradicción misma es el estado a resolver en el
        # nivel superior (la síntesis). Apuntar a un hijo sería tomar partido
        # por la tesis o la antítesis sin evidencia de resolución.
        has_conflict = any(c.is_true for c in children) and any(c.is_false for c in children)
        if has_conflict and all(c.certified for c in children):
            return []
        return [c for c in children if not c.certified]

    if op == "OR":
        # En OR, solo son culpables si NINGÚN hijo TRUE está certificado
        true_certified = [c for c in children if c.is_true and c.certified]
        if true_certified:
            return []  # Hay al menos uno válido, el OR debería estar certificado
        # Si no hay ninguno, los TRUE no-certificados son los más relevantes
        true_uncertified = [c for c in children if c.is_true and not c.certified]
        if true_uncertified:
            return true_uncertified
        # Si todos son FALSE/UNKNOWN, todos son culpables
        return [c for c in children if not c.certified]

    if op == "NOT":
        # NOT depende exclusivamente de su único hijo
        return [c for c in children if not c.certified]

    if op == "IMPLIES":
        if len(children) != 2:
            return [c for c in children if not c.certified]
        ante, cons = children
        # Si antecedente es FALSE, IMPLIES es TRUE automáticamente → no hay culpa
        if ante.is_false:
            return []
        # Si antecedente es TRUE/UNKNOWN, el consecuente debe estar certificado
        if not cons.certified:
            return [cons]
        if not ante.certified:
            return [ante]
        return []

    if op == "XOR":
        # XOR requiere ambos certificados
        return [c for c in children if not c.certified]

    # Fallback
    return [c for c in children if not c.certified]

