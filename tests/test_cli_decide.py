"""Tests for the decide CLI command."""
import json
import subprocess
import sys
import pytest

# Import directly for unit tests
from socratic_engine.cli import _build_decide_tree, _decide_cli
from socratic_engine.engine import SocraticEngine


def run_decide(*args):
    """Run decide command and return parsed output."""
    result = subprocess.run(
        [sys.executable, "-m", "socratic_engine.cli", "decide", *args],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result


class TestDecideCLI:
    """Tests for socratic-engine decide command."""

    def test_simple_reversible_decision(self):
        """Simple reversible decision should pass."""
        result = run_decide("--decision", "Use JSONL", "--json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["truth"] == "TRUE"
        assert data["certified"] is True
        assert data["home"] == "pass"

    def test_decision_with_alternatives(self):
        """Decision with alternatives should pass."""
        result = run_decide(
            "--decision", "Restructure docs/",
            "--alternatives", "Keep,Reorganize",
            "--impact", "All references",
            "--json",
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["truth"] == "TRUE"
        assert data["context"]["has_alternatives"] is True
        assert data["context"]["has_impact"] is True

    def test_irreversible_without_approval(self):
        """Irreversible decision without approval should be UNKNOWN."""
        result = run_decide(
            "--decision", "Delete data",
            "--reversible", "false",
            "--json",
        )
        assert result.returncode == 1
        data = json.loads(result.stdout)
        assert data["truth"] == "UNKNOWN"
        assert data["certified"] is False

    def test_irreversible_with_approval(self):
        """Irreversible decision with approval should pass."""
        result = run_decide(
            "--decision", "Delete data",
            "--reversible", "false",
            "--approved",
            "--json",
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["truth"] == "TRUE"
        assert data["certified"] is True

    def test_human_readable_output(self):
        """Non-JSON output should be human readable."""
        result = run_decide("--decision", "Test decision")
        assert result.returncode == 0
        assert "DECISION CERTIFIED" in result.stdout

    def test_irreversible_human_readable(self):
        """Irreversible without approval should show rejected."""
        result = run_decide(
            "--decision", "Delete data",
            "--reversible", "false",
        )
        assert result.returncode == 1
        assert "DECISION UNCERTAIN" in result.stdout

    def test_missing_decision_fails(self):
        """Missing --decision should fail."""
        result = run_decide()
        assert result.returncode != 0

    def test_context_json(self):
        """Additional context should be merged into evaluation context."""
        result = run_decide(
            "--decision", "Test",
            "--context", '{"reversible": "false"}',
            "--json",
        )
        # Irreversible without approval returns exit code 1
        assert result.returncode == 1
        data = json.loads(result.stdout)
        # The context is merged into the evaluation, affecting the result
        assert data["truth"] == "UNKNOWN"  # irreversible without approval

    def test_prerequisites(self):
        """Prerequisites should be accepted without error."""
        result = run_decide(
            "--decision", "Test",
            "--prerequisites", "Prereq1,Prereq2",
            "--json",
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["truth"] == "TRUE"


class TestBuildDecideTree:
    """Unit tests for _build_decide_tree function."""

    def test_simple_decision_tree(self):
        """Simple decision should have ctx_has and ctx_equals."""
        ctx = {"decision": "test", "reversible": "true"}
        tree = _build_decide_tree(ctx)
        assert tree["op"] == "AND"
        assert len(tree["children"]) == 2  # ctx_has + ctx_equals

    def test_with_alternatives(self):
        """Decision with alternatives should add ctx_has for alternatives."""
        ctx = {"decision": "test", "reversible": "true", "alternatives": ["A", "B"]}
        tree = _build_decide_tree(ctx)
        assert len(tree["children"]) == 3  # ctx_has + ctx_has(alternatives) + ctx_equals

    def test_with_impact(self):
        """Decision with impact should add ctx_has for impact."""
        ctx = {"decision": "test", "reversible": "true", "impact": "big"}
        tree = _build_decide_tree(ctx)
        assert len(tree["children"]) == 3  # ctx_has + ctx_has(impact) + ctx_equals

    def test_irreversible_tree(self):
        """Irreversible decision should have AND subtree for approval."""
        ctx = {"decision": "test", "reversible": "false"}
        tree = _build_decide_tree(ctx)
        assert len(tree["children"]) == 2  # ctx_has + AND subtree
        and_subtree = tree["children"][1]
        assert and_subtree["op"] == "AND"
        assert len(and_subtree["children"]) == 2  # ctx_equals + ctx_has(approved)


class TestDecideCLIUnit:
    """Unit tests for _decide_cli function."""

    def test_help_exits(self):
        """Help should trigger SystemExit(0)."""
        with pytest.raises(SystemExit) as exc_info:
            _decide_cli(["--help"])
        assert exc_info.value.code == 0

    def test_missing_decision_exits(self):
        """Missing --decision should trigger SystemExit(2)."""
        with pytest.raises(SystemExit) as exc_info:
            _decide_cli([])
        assert exc_info.value.code == 2

    def test_invalid_context_json(self):
        """Invalid JSON context should return error."""
        result = _decide_cli(["--decision", "test", "--context", "not json"])
        assert result == 2
