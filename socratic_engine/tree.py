"""
socratic_engine.tree — constructor seguro de árboles + parser VSL + tree_home.

- SocraticTreeBuilder: valida estructura + verifica que los predicados
  existan en el engine; fallo rápido con mensajes contextuales.
- parse_socratic_block: mini-parser VSL recursivo (árboles anidados
  AND/OR/NOT, kwargs, homes) sobre bloques socratic(...) declarados.
- tree_home: evalúa un árbol contra el TYPE de un doc y retorna el home
  del primer hijo TRUE, o else_home, o None.

SEMÁNTICA EPISTEMOLÓGICA: si un hijo responde UNKNOWN (no se pudo decidir),
NO se enruta al else_home silencioso — se retorna None ('?' visible, R9:
no conceder silenciosamente). Sin sujeto no hay juicio.
"""

import re
from typing import Any, Dict, Optional

from .engine import SocraticEngine

class SocraticTreeBuilder:
    """
    Constructor seguro de árboles socráticos (rmw3, 2026-08-17).
    Valida estructura + verifica que los predicados existan en el engine.
    Fallo rápido con mensajes contextuales — la puerta de entrada para que
    un LLM (o cualquier fuente externa) proponga árboles sin alucinar
    (R10.1: el LLM propone, el motor certifica; el builder valida)."""

    def __init__(self, engine: SocraticEngine):
        self.engine = engine

    def build(self, tree_json) -> Dict[str, Any]:
        """Parsea y valida un árbol desde JSON string o dict.
        Retorna el árbol listo para engine.evaluate().
        Lanza excepciones descriptivas si algo está mal."""
        import json
        if isinstance(tree_json, str):
            try:
                tree = json.loads(tree_json)
            except json.JSONDecodeError as e:
                raise ValueError(f"JSON inválido: {e}")
        else:
            tree = tree_json
        self._validate_node(tree)
        return tree

    def _validate_node(self, node: Any, path: str = "root") -> None:
        """Validación recursiva con mensajes de error contextuales."""
        # Literales: bool (caso base lógico) y escalares (args/kwargs values)
        if isinstance(node, (bool, str, int, float)) or node is None:
            return

        if not isinstance(node, dict):
            raise ValueError(f"{path}: esperado bool, escalar o dict, recibido {type(node).__name__}")

        # Predicate
        if "predicate" in node:
            name = node["predicate"]
            if name not in self.engine.predicates:
                available = ", ".join(sorted(self.engine.predicates.keys()))
                raise ValueError(
                    f"{path}: predicado '{name}' no registrado. Disponibles: [{available}]"
                )
            for i, arg in enumerate(node.get("args", [])):
                self._validate_node(arg, f"{path}.args[{i}]")
            for k, v in node.get("kwargs", {}).items():
                self._validate_node(v, f"{path}.kwargs.{k}")
            return

        # Operator
        if "op" in node:
            op = node["op"].upper()
            if op not in SocraticEngine.OPERATORS:
                raise ValueError(f"{path}: operador '{op}' desconocido. Válidos: {SocraticEngine.OPERATORS}")

            children = node.get("children", [])
            if not children:
                raise ValueError(f"{path}: operador '{op}' requiere al menos un hijo")

            if op == "NOT" and len(children) != 1:
                raise ValueError(f"{path}: NOT requiere exactamente 1 hijo, recibió {len(children)}")
            if op == "IMPLIES" and len(children) != 2:
                raise ValueError(f"{path}: IMPLIES requiere exactamente 2 hijos, recibió {len(children)}")

            for i, child in enumerate(children):
                self._validate_node(child, f"{path}.children[{i}]")
            return

        raise ValueError(f"{path}: nodo debe tener 'predicate', 'op' o ser bool")


# ── interfaz con classification.local.vsm (árbol declarado en VSL) ──────────
def _parse_vsl_value(s: str, i: int) -> tuple[Any, int]:
    """Mini-parser VSL de valores: { } [ ] "string" word — recursivo.
    Retorna (valor, índice_tras_el_valor). Soporta árboles anidados."""
    while i < len(s) and s[i] in " \t\n\r,":
        i += 1
    if i >= len(s):
        return None, i
    c = s[i]
    if c == "{":
        i += 1
        obj: dict = {}
        key: str | None = None
        while i < len(s):
            while i < len(s) and s[i] in " \t\n\r,":
                i += 1
            if i >= len(s):
                break
            if s[i] == "}":
                i += 1
                break
            if s[i] == '"':
                # string key
                j = i + 1
                while j < len(s) and s[j] != '"':
                    j += 1
                key = s[i + 1:j]
                i = j + 1
            else:
                # word key
                j = i
                while j < len(s) and s[j] not in ": \t\n\r,}":
                    j += 1
                key = s[i:j]
                i = j
            while i < len(s) and s[i] in " \t\n\r":
                i += 1
            if i < len(s) and s[i] == ":":
                i += 1
            val, i = _parse_vsl_value(s, i)
            if key is not None:
                obj[key] = val
        return obj, i
    if c == "[":
        i += 1
        arr: list = []
        while i < len(s):
            while i < len(s) and s[i] in " \t\n\r,":
                i += 1
            if i >= len(s):
                break
            if s[i] == "]":
                i += 1
                break
            val, i = _parse_vsl_value(s, i)
            arr.append(val)
        return arr, i
    if c == '"':
        j = i + 1
        while j < len(s) and s[j] != '"':
            j += 1
        return s[i + 1:j], j + 1
    # bare word / number
    j = i
    while j < len(s) and s[j] not in " \t\n\r,}]":
        j += 1
    word = s[i:j].strip()
    if word in ("true", "True"):
        return True, j
    if word in ("false", "False"):
        return False, j
    try:
        return int(word), j
    except ValueError:
        return word, j


def parse_socratic_block(text: str) -> Optional[dict]:
    """Extrae el bloque socratic(...) de un classification.local.vsm y lo
    convierte a dict Python. Formato VSL (vsm-1.2):
      socratic("NAME") = {
        op: AND,
        children: [
          { predicate: "ctx_has", args: ["$ctx", "type"] },
          { op: OR, children: [ { predicate: "type_prefix", args: ["$type", "VSL-LANG-"], home: "vsl-language" } ] },
        ],
        else_home: "sandbox",
      }
    Soporta anidamiento arbitrario (AND/OR/NOT, kwargs, homes). Retorna
    None si no hay bloque socratic."""
    if "socratic(" not in text:
        return None
    m = re.search(r'socratic\("[^"]*"\)\s*=\s*\{', text)
    if not m:
        return None
    body = text[m.end() - 1:]  # desde el { del bloque
    obj, _ = _parse_vsl_value(body, 0)
    if not isinstance(obj, dict):
        return None
    return obj


def tree_home(tree: Optional[dict], doc_type: str, engine: SocraticEngine,
              context: Optional[dict] = None) -> Optional[str]:
    """Evalúa el árbol socrático de un nivel contra el TYPE de un doc.
    Retorna el home del primer hijo que responda TRUE, o else_home, o None.
    SEMÁNTICA EPISTEMOLÓGICA: si un hijo responde UNKNOWN (no se pudo
    decidir), NO se enruta al else_home silencioso — se retorna None ('?'
    visible, R9: no conceder silenciosamente).
    Árboles anidados: cuando un child TRUE no lleva home (es un sub-árbol
    op), se desciende recursivamente a buscar el home de su primer hijo
    TRUE. context: dict completo (adicional a {"type": doc_type})."""
    if tree is None:
        return None
    ctx = {"type": doc_type}
    if context:
        ctx.update(context)

    def _resolve(node: Any) -> Optional[str]:
        if not isinstance(node, dict):
            return None
        # hoja con home propio: evalúa y devuelve su home si TRUE
        if "predicate" in node or "op" in node:
            try:
                ev = engine.evaluate(node, ctx)
            except (ValueError, KeyError):
                return None
            if ev.is_true and node.get("home"):
                return node["home"]
            if ev.is_true and "op" in node:
                # sub-árbol TRUE sin home → descender
                for child in node.get("children", []):
                    h = _resolve(child)
                    if h is not None:
                        return h
            return None
        return None

    saw_unknown = False
    for child in tree.get("children", []):
        try:
            ev = engine.evaluate(child, ctx)
            if ev.is_true:
                h = _resolve(child)
                if h is not None:
                    return h
                continue
            if ev.is_unknown:
                saw_unknown = True
        except (ValueError, KeyError):
            continue
    if saw_unknown:
        return None  # '?' visible — no inventar, no conceder silenciosamente
    return tree.get("else_home")

