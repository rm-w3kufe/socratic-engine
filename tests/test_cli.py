"""Tests del CLI (contrato externo): eval-tree + selftest + errores."""

import json

import pytest

from socratic_engine.cli import _eval_tree_cli, _run_selftest, main

# ── helpers ──

def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content)
    return str(p)


VSL_TREE = '''socratic("TEST") = {
  op: AND,
  children: [
    { predicate: "ctx_has", args: ["$ctx", "type"], },
    { op: OR, children: [
      { predicate: "type_prefix", args: ["$type", "VSL-"], home: "vsl-language" },
      { predicate: "type_glob", args: ["$type", "SPEC-*"], home: "spec" },
    ], },
  ],
  else_home: "system",
}
'''

JSON_TREE = json.dumps({
    "op": "AND",
    "children": [
        {"predicate": "ctx_has", "args": ["$ctx", "type"]},
        {"predicate": "type_prefix", "args": ["$type", "VSL-"]},
    ],
})


# ── main / selftest ──

def test_main_no_args_runs_selftest(monkeypatch):
    monkeypatch.setattr("socratic_engine.cli.sys.argv", ["socratic-engine"])
    assert main() == 0


def test_run_selftest_ok(capsys):
    _run_selftest()
    out = capsys.readouterr().out
    assert "selftest OK" in out


# ── eval-tree: éxito ──

def test_eval_tree_vsl_success(tmp_path, capsys):
    path = _write(tmp_path, "t.vsm", VSL_TREE)
    rc = _eval_tree_cli([path, "--context", '{"type":"VSL-LANG-01"}'])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["truth"] == "TRUE"
    assert out["certified"] is True
    assert out["unknown"] is False
    assert out["home"] == "vsl-language"


def test_eval_tree_json_success(tmp_path, capsys):
    path = _write(tmp_path, "t.json", JSON_TREE)
    rc = _eval_tree_cli([path, "--doc-type", "VSL-LANG-01"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["truth"] == "TRUE"
    assert "explain" in out
    assert isinstance(out["diagnose"], list)


def test_eval_tree_doc_type_injects_type(tmp_path, capsys):
    path = _write(tmp_path, "t.vsm", VSL_TREE)
    rc = _eval_tree_cli([path, "--doc-type", "OTHER-TYPE"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["truth"] == "FALSE"  # type_prefix no matchea → decidible FALSE


# ── eval-tree: errores ──

def test_eval_tree_missing_arg(tmp_path, capsys):
    rc = _eval_tree_cli([])
    err = capsys.readouterr().err
    assert rc == 2
    assert "usage" in err


def test_eval_tree_not_found(tmp_path, capsys):
    rc = _eval_tree_cli([str(tmp_path / "nope.vsm")])
    err = capsys.readouterr().err
    assert rc == 2
    assert "not found" in err


def test_eval_tree_bad_context_json(tmp_path, capsys):
    path = _write(tmp_path, "t.vsm", VSL_TREE)
    rc = _eval_tree_cli([path, "--context", "{invalid json"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "not valid JSON" in err


def test_eval_tree_no_socratic_block(tmp_path, capsys):
    path = _write(tmp_path, "t.vsm", "no socratic here")
    rc = _eval_tree_cli([path])
    err = capsys.readouterr().err
    assert rc == 2
    assert "no socratic" in err


def test_eval_tree_unknown_predicate_fails(tmp_path, capsys):
    path = _write(tmp_path, "t.vsm", '''socratic("T") = {
  predicate: "does_not_exist",
  args: ["x"],
}
''')
    rc = _eval_tree_cli([path])
    err = capsys.readouterr().err
    assert rc == 1
    assert "evaluation error" in err


def test_eval_tree_unknown_flag_ignored(tmp_path, capsys):
    path = _write(tmp_path, "t.vsm", VSL_TREE)
    rc = _eval_tree_cli([path, "--unknown-flag"])
    assert rc == 0  # flags desconocidos se ignoran (no rompen el contrato)


def test_cli_main_block_entry():
    # L181: sys.exit(main()) en __main__ — selftest sin args
    import subprocess, sys
    r = subprocess.run(
        [sys.executable, "-m", "socratic_engine.cli"],
        capture_output=True, text=True, timeout=30)
    assert r.returncode == 0


def test_cli_eval_tree_dispatch(tmp_path):
    # L174: return _eval_tree_cli(args[1:]) — dispatch de "eval-tree"
    import subprocess, sys, json
    tree_file = tmp_path / "tree.json"
    tree_file.write_text(json.dumps(
        {"predicate": "type_prefix", "args": ["SPEC-1", "SPEC-"]}))
    r = subprocess.run(
        [sys.executable, "-m", "socratic_engine.cli", "eval-tree",
         str(tree_file), "--doc-type", "SPEC-1"],
        capture_output=True, text=True, timeout=30)
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["truth"] == "TRUE" and out["certified"] is True
