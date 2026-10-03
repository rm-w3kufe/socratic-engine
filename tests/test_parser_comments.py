"""Tests del parser VSL: comentarios `//` inline (fix 2026-10-03).

Bug: `_parse_vsl_value` no strippeaba comments — dentro de
`children: [ ... ]` un comentario se parseaba como nodos string sueltos
("//" + fragmentos) y `engine.evaluate` lanzaba
`ValueError: Nodo inválido ... Recibido: //` la primera vez que una rama
sin short-circuit los alcanzaba (observado con classify.tree.vsm de
vOSlab: doc-types REGISTRY/PLAN/vacío crasheaban, PLAN-REGISTRY no).
"""
import pytest

from socratic_engine import SocraticEngine, Truth
from socratic_engine.tree import parse_socratic_block


RAW = """
socratic("T") = {
  op: AND,
  children: [
    { predicate: "ctx_has", args: ["$ctx", "type"] },
    // commentario interno (2026-10-03): debe ignorarse completo
    // segunda linea de comentario
    {
      op: OR,
      children: [
        { predicate: "type_prefix", args: ["$type", "FOO-"], home: "a" },
        // comment ANTES de la hoja final
        { predicate: "type_prefix", args: ["$type", "BAR-"], home: "b" },
      ],
    },
  ],
  else_home: "system",
}
"""


def test_comment_nodes_not_parsed():
    tree = parse_socratic_block(RAW)
    assert tree is not None
    or_node = tree["children"][1]
    assert or_node["op"] == "OR"
    # exactamente 2 hojas — los comments NO generaron nodos
    assert len(or_node["children"]) == 2
    for child in or_node["children"]:
        assert isinstance(child, dict)
        assert child.get("predicate") == "type_prefix"


def test_matches_comment_free_equivalent():
    comment_free = RAW.replace(
        "    // commentario interno (2026-10-03): debe ignorarse completo\n"
        "    // segunda linea de comentario\n", ""
    ).replace("        // comment ANTES de la hoja final\n", "")
    assert parse_socratic_block(RAW) == parse_socratic_block(comment_free)


def test_comment_preserved_inside_string():
    text = 'socratic("T") = { op: NOT, children: [ { predicate: "p", '
    text += 'args: ["http://x//y"] } ], else_home: "s" }'
    tree = parse_socratic_block(text)
    assert tree["children"][0]["args"] == ["http://x//y"]


def test_evaluate_tree_with_comments():
    # ctx_has / type_prefix son builtins del engine (rutas del classify)
    eng = SocraticEngine()
    tree = parse_socratic_block(RAW)

    ev = eng.evaluate(tree, {"type": "FOO-1"})
    assert ev.truth is Truth.TRUE
    ev = eng.evaluate(tree, {"type": "BAZ"})
    assert ev.truth is Truth.FALSE  # no match → else_home no cambia truth


def test_comment_to_eof():
    tree = parse_socratic_block(
        'socratic("T") = { op: NOT, children: [ true ], else_home: "s" }\n// fin')
    assert tree is not None
    assert tree["else_home"] == "s"
