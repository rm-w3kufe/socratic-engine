"""Tests for match-procedure CLI + decide/eval-tree error paths (in-process).

Covers socratic_engine/cli.py branches that subprocess-based tests
cannot reach for coverage (child processes aren't instrumented).
All fixtures hermetic (tmp dirs).
"""
from __future__ import annotations

import json

import pytest

from socratic_engine.cli import (
    _decide_cli,
    _eval_tree_cli,
    _match_procedure_cli,
)


def _proc(repo, pid, instrument="x", hook="session.idle", success=True,
          ts="2026-09-22T10:00:00Z"):
    return {
        "id": pid, "type": "procedure", "version": "1.0",
        "source": {"instrument": instrument, "hook": hook},
        "action": "do", "decision": {"result": "pending"},
        "outcome": {"success": success},
        "metadata": {"timestamp": ts, "pid": 1},
    }


def _repo_with(repo, procs):
    d = repo / "docs" / "spec_revision" / "learning_records" / "procedures"
    d.mkdir(parents=True)
    for p in procs:
        (d / f"{p['id']}.json").write_text(json.dumps(p))
    return repo


def _inp(repo, **kw):
    base = {"instrument": "x", "hook": "session.idle",
            "context": {}, "repoRoot": str(repo)}
    base.update(kw)
    return ["--input", json.dumps(base)]


def test_match_no_procedures_dir(tmp_path, capsys):
    rc = _match_procedure_cli(_inp(tmp_path))
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["action"] == "skip" and out["matches_count"] == 0


def test_match_reuse_high_confidence(tmp_path, capsys):
    _repo_with(tmp_path, [_proc(tmp_path, "p1")])
    rc = _match_procedure_cli(_inp(tmp_path))
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["action"] == "reuse" and out["confidence"] >= 0.8


def test_match_skip_no_instrument(tmp_path, capsys):
    _repo_with(tmp_path, [_proc(tmp_path, "p1", instrument="other")])
    rc = _match_procedure_cli(_inp(tmp_path))
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["action"] == "skip"


def test_match_adapt_medium_confidence(tmp_path, capsys):
    # instrument(0.4) + hook(0.3) + failure(0) + stale(0) = 0.7 -> adapt
    _repo_with(tmp_path, [_proc(tmp_path, "p1", success=False,
                                ts="2026-01-01T00:00:00Z")])
    rc = _match_procedure_cli(_inp(tmp_path))
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["action"] == "adapt"


def test_match_invalid_input(capsys):
    rc = _match_procedure_cli(["--input", "{not json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["action"] == "skip" and "invalid input" in out["detail"]


def test_match_missing_input_arg():
    with pytest.raises(SystemExit) as e:
        _match_procedure_cli([])
    assert e.value.code == 2


def test_match_malformed_procedure_file(tmp_path, capsys):
    d = (tmp_path / "docs" / "spec_revision" / "learning_records"
         / "procedures")
    d.mkdir(parents=True)
    (d / "broken.json").write_text("{oops")
    (d / "wrong-type.json").write_text(json.dumps({"type": "nope"}))
    rc = _match_procedure_cli(_inp(tmp_path))
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["action"] == "skip"


def test_decide_reversible_passes(capsys):
    rc = _decide_cli(["--decision", "use json", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["home"] == "pass"


def test_decide_irreversible_needs_approval(capsys):
    rc = _decide_cli(["--decision", "drop db", "--reversible", "false",
                      "--json"])
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["home"] == "reject"


def test_decide_irreversible_approved(capsys):
    rc = _decide_cli(["--decision", "drop db", "--reversible", "false",
                      "--approved", "--json"])
    assert rc == 0


def test_decide_full_context(capsys):
    rc = _decide_cli(["--decision", "ship it",
                      "--alternatives", "wait,rollback",
                      "--impact", "users", "--prerequisites", "tests",
                      "--context", '{"team": "core"}', "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["context"]["has_alternatives"] is True
    assert out["context"]["has_impact"] is True


def test_decide_bad_context_json(capsys):
    rc = _decide_cli(["--decision", "x", "--context", "{bad"])
    assert rc == 2


def test_decide_missing_required():
    with pytest.raises(SystemExit) as e:
        _decide_cli([])
    assert e.value.code == 2


def test_eval_tree_missing_file(capsys):
    rc = _eval_tree_cli(["/nonexistent/tree.vsm"])
    assert rc == 2


def test_eval_tree_no_args(capsys):
    rc = _eval_tree_cli([])
    assert rc == 2


def test_eval_tree_bad_context(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"predicate": "ctx_has",
                             "args": ["$ctx", "a"]}))
    rc = _eval_tree_cli([str(p), "--context", "{bad"])
    assert rc == 2


def test_eval_tree_no_block(tmp_path):
    p = tmp_path / "t.vsm"
    p.write_text("no socratic block here\n")
    rc = _eval_tree_cli([str(p)])
    assert rc == 2


def test_eval_tree_json_ok(tmp_path, capsys):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"predicate": "ctx_has",
                             "args": ["$ctx", "a"]}))
    rc = _eval_tree_cli([str(p), "--context", '{"a": 1}'])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["truth"] == "TRUE"


def test_eval_tree_vsm_ok(tmp_path, capsys):
    p = tmp_path / "t.vsm"
    p.write_text('socratic("T") = {\n  predicate: "ctx_has",\n'
                 '  args: ["$ctx", "a"],\n}\n')
    rc = _eval_tree_cli([str(p), "--context", '{"a": 1}'])
    assert rc == 0


def test_eval_tree_doc_type_flag(tmp_path, capsys):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"predicate": "type_prefix",
                             "args": ["$type", "VSL-"]}))
    rc = _eval_tree_cli([str(p), "--doc-type", "VSL-X"])
    assert rc == 0


def test_eval_tree_eval_error(tmp_path, capsys):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"predicate": "no_such_predicate_xyz",
                             "args": []}))
    rc = _eval_tree_cli([str(p)])
    assert rc == 1
