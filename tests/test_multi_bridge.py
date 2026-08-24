"""Tests for MultiBridge — routing, providers, predicates."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from socratic_engine.engine import SocraticEngine, Truth
from socratic_engine.multi_bridge import MultiBridge, ProviderEntry, _normalize_filter


# ── helpers ──────────────────────────────────────────────────────────────


class FakeProvider:
    """Minimal provider for testing."""

    def __init__(self, domains: dict[str, list[dict]] | None = None):
        self._domains = domains or {}

    def query(self, domain: str, filter_dict: dict | None = None) -> list[dict]:
        records = self._domains.get(domain, [])
        if filter_dict:
            records = [
                r for r in records
                if all(r.get(k) == v for k, v in filter_dict.items())
            ]
        return records

    def list_domains(self) -> list[str]:
        return list(self._domains.keys())


# ── normalize_filter ─────────────────────────────────────────────────────


class TestNormalizeFilter:
    def test_none_returns_empty_dict(self):
        assert _normalize_filter(None) == {}

    def test_dict_passthrough(self):
        assert _normalize_filter({"a": 1}) == {"a": 1}

    def test_json_string(self):
        assert _normalize_filter('{"a": 1}') == {"a": 1}

    def test_invalid_json_returns_none(self):
        assert _normalize_filter("not json") is None

    def test_non_dict_json_returns_none(self):
        assert _normalize_filter("[1, 2]") is None


# ── ProviderEntry ────────────────────────────────────────────────────────


class TestProviderEntry:
    def test_query_success(self):
        provider = FakeProvider({"svc": [{"name": "a"}]})
        entry = ProviderEntry("test", provider, ["svc"])
        assert entry.query("svc", {}) == [{"name": "a"}]

    def test_query_exception_returns_empty(self):
        provider = MagicMock()
        provider.query.side_effect = RuntimeError("boom")
        entry = ProviderEntry("test", provider, ["svc"])
        with pytest.raises(RuntimeError):
            entry.query("svc", {})

    def test_list_domains_success(self):
        provider = FakeProvider({"a": [], "b": []})
        entry = ProviderEntry("test", provider, ["a", "b"])
        assert entry.list_domains() == ["a", "b"]

    def test_list_domains_exception(self):
        provider = MagicMock()
        provider.list_domains.side_effect = RuntimeError("boom")
        entry = ProviderEntry("test", provider, ["a"])
        assert entry.list_domains() == []


# ── MultiBridge core ─────────────────────────────────────────────────────


class TestMultiBridge:
    def _make_bridge(
        self, providers: dict[str, dict[str, list[dict]]] | None = None
    ) -> MultiBridge:
        bridge = MultiBridge()
        if providers:
            for name, domains in providers.items():
                bridge.add_provider(name, FakeProvider(domains), list(domains.keys()))
        return bridge

    def test_add_provider(self):
        bridge = self._make_bridge({"p1": {"svc": [{"n": 1}]}})
        assert "svc" in bridge._domain_map
        assert bridge._domain_map["svc"] == "p1"

    def test_domain_override(self):
        bridge = MultiBridge()
        bridge.add_provider("p1", FakeProvider({"svc": [{"n": 1}]}), ["svc"])
        bridge.add_provider("p2", FakeProvider({"svc": [{"n": 2}]}), ["svc"])
        # p2 wins
        assert bridge._domain_map["svc"] == "p2"

    def test_remove_provider(self):
        bridge = self._make_bridge({"p1": {"svc": []}})
        bridge.remove_provider("p1")
        assert "p1" not in bridge._providers
        assert "svc" not in bridge._domain_map

    def test_remove_nonexistent(self):
        bridge = MultiBridge()
        bridge.remove_provider("nope")  # no error

    def test_register_predicates(self):
        bridge = self._make_bridge({"p1": {"svc": []}})
        eng = SocraticEngine()
        bridge.register(eng)
        # All 6 predicates should be registered
        for name in [
            "canon_query", "canon_matches", "canon_field_equals",
            "canon_drift", "canon_domains", "canon_providers",
        ]:
            assert name in eng.predicates


# ── canon_query ──────────────────────────────────────────────────────────


class TestCanonQuery:
    def test_existing_records(self):
        bridge = MultiBridge()
        bridge.add_provider(
            "p1", FakeProvider({"svc": [{"name": "a"}, {"name": "b"}]}), ["svc"]
        )
        eng = SocraticEngine()
        bridge.register(eng)

        result = eng.predicates["canon_query"]("svc")
        assert result.truth == Truth.TRUE
        assert result.certified is True
        assert result.evidence["count"] == 2

    def test_no_records(self):
        bridge = MultiBridge()
        bridge.add_provider("p1", FakeProvider({"svc": []}), ["svc"])
        eng = SocraticEngine()
        bridge.register(eng)

        result = eng.predicates["canon_query"]("svc")
        assert result.truth == Truth.UNKNOWN
        assert result.evidence["reason"] == "no_records"

    def test_unknown_domain(self):
        bridge = MultiBridge()
        bridge.add_provider("p1", FakeProvider({"svc": []}), ["svc"])
        eng = SocraticEngine()
        bridge.register(eng)

        result = eng.predicates["canon_query"]("nonexistent")
        assert result.truth == Truth.UNKNOWN
        assert result.evidence["reason"] == "unknown_domain"

    def test_with_filter(self):
        bridge = MultiBridge()
        bridge.add_provider(
            "p1",
            FakeProvider({"svc": [{"name": "a", "active": True}, {"name": "b", "active": False}]}),
            ["svc"],
        )
        eng = SocraticEngine()
        bridge.register(eng)

        result = eng.predicates["canon_query"]("svc", '{"active": true}')
        assert result.truth == Truth.TRUE
        assert result.evidence["count"] == 1


# ── canon_matches ────────────────────────────────────────────────────────


class TestCanonMatches:
    def test_all_match(self):
        bridge = MultiBridge()
        bridge.add_provider(
            "p1", FakeProvider({"svc": [{"name": "a", "status": "ok"}]}), ["svc"]
        )
        eng = SocraticEngine()
        bridge.register(eng)

        result = eng.predicates["canon_matches"]("svc", "{}", '{"status": "ok"}')
        assert result.truth == Truth.TRUE
        assert result.certified is True

    def test_mismatch(self):
        bridge = MultiBridge()
        bridge.add_provider(
            "p1", FakeProvider({"svc": [{"name": "a", "status": "ok"}]}), ["svc"]
        )
        eng = SocraticEngine()
        bridge.register(eng)

        result = eng.predicates["canon_matches"]("svc", "{}", '{"status": "down"}')
        assert result.truth == Truth.FALSE

    def test_no_records(self):
        bridge = MultiBridge()
        bridge.add_provider("p1", FakeProvider({"svc": []}), ["svc"])
        eng = SocraticEngine()
        bridge.register(eng)

        result = eng.predicates["canon_matches"]("svc", "{}", '{"x": 1}')
        assert result.truth == Truth.UNKNOWN


# ── canon_field_equals ───────────────────────────────────────────────────


class TestCanonFieldEquals:
    def test_field_matches(self):
        bridge = MultiBridge()
        bridge.add_provider(
            "p1", FakeProvider({"svc": [{"name": "a", "version": "2.0"}]}), ["svc"]
        )
        eng = SocraticEngine()
        bridge.register(eng)

        result = eng.predicates["canon_field_equals"]("svc", "{}", "version", "2.0")
        assert result.truth == Truth.TRUE

    def test_field_missing(self):
        bridge = MultiBridge()
        bridge.add_provider(
            "p1", FakeProvider({"svc": [{"name": "a"}]}), ["svc"]
        )
        eng = SocraticEngine()
        bridge.register(eng)

        result = eng.predicates["canon_field_equals"]("svc", "{}", "nope", "x")
        assert result.truth == Truth.UNKNOWN
        assert result.evidence["reason"] == "field_missing"


# ── canon_drift ──────────────────────────────────────────────────────────


class TestCanonDrift:
    def test_no_drift(self):
        bridge = MultiBridge()
        bridge.add_provider(
            "p1",
            FakeProvider({"svc": [{"name": "a", "declared": "1.0", "observed": "1.0"}]}),
            ["svc"],
        )
        eng = SocraticEngine()
        bridge.register(eng)

        result = eng.predicates["canon_drift"]("svc", "{}", "declared", "observed")
        assert result.truth == Truth.TRUE
        assert result.evidence["drift"] == []

    def test_drift_detected(self):
        bridge = MultiBridge()
        bridge.add_provider(
            "p1",
            FakeProvider({"svc": [{"name": "a", "declared": "1.0", "observed": "2.0"}]}),
            ["svc"],
        )
        eng = SocraticEngine()
        bridge.register(eng)

        result = eng.predicates["canon_drift"]("svc", "{}", "declared", "observed")
        assert result.truth == Truth.FALSE
        assert len(result.evidence["drift"]) == 1


# ── canon_domains + canon_providers ──────────────────────────────────────


class TestCanonIntrospection:
    def test_canon_domains(self):
        bridge = MultiBridge()
        bridge.add_provider("p1", FakeProvider({"a": [], "b": []}), ["a", "b"])
        bridge.add_provider("p2", FakeProvider({"c": []}), ["c"])
        eng = SocraticEngine()
        bridge.register(eng)

        result = eng.predicates["canon_domains"]()
        assert result.truth == Truth.TRUE
        assert sorted(result.evidence["domains"]) == ["a", "b", "c"]
        assert result.evidence["total_providers"] == 2

    def test_canon_providers(self):
        bridge = MultiBridge()
        bridge.add_provider("p1", FakeProvider({"a": []}), ["a"])
        eng = SocraticEngine()
        bridge.register(eng)

        result = eng.predicates["canon_providers"]()
        assert result.truth == Truth.TRUE
        assert len(result.evidence["providers"]) == 1
        assert result.evidence["providers"][0]["name"] == "p1"


# ── from_config ──────────────────────────────────────────────────────────


class TestFromConfig:
    def test_loads_config(self, tmp_path):
        config = {
            "version": 1,
            "bridges": [
                {
                    "name": "test",
                    "provider_class": "FakeProvider",
                    "module": "tests.test_multi_bridge",
                    "init_args": {"domains": {"svc": [{"name": "a"}]}},
                    "domains": ["svc"],
                }
            ],
        }
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config))

        bridge = MultiBridge.from_config(config_path)
        assert "svc" in bridge._domain_map

    def test_missing_config(self):
        with pytest.raises(FileNotFoundError):
            MultiBridge.from_config("/nonexistent/config.json")

    def test_bad_version(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"version": 2, "bridges": []}))
        with pytest.raises(ValueError, match="Unsupported"):
            MultiBridge.from_config(config_path)


# ── cross-domain AND ────────────────────────────────────────────────────


class TestCrossDomain:
    def test_and_across_providers(self):
        """AND with records from different providers works."""
        bridge = MultiBridge()
        bridge.add_provider(
            "p1", FakeProvider({"svc": [{"name": "a"}]}), ["svc"]
        )
        bridge.add_provider(
            "p2", FakeProvider({"tasks": [{"id": 1}]}), ["tasks"]
        )
        eng = SocraticEngine()
        bridge.register(eng)

        tree = {
            "op": "AND",
            "children": [
                {"predicate": "canon_query", "args": ["svc"]},
                {"predicate": "canon_query", "args": ["tasks"]},
            ],
        }
        ev = eng.evaluate(tree)
        assert ev.truth == Truth.TRUE
        assert ev.certified is True

    def test_and_one_domain_missing(self):
        """AND fails when one domain has no records."""
        bridge = MultiBridge()
        bridge.add_provider(
            "p1", FakeProvider({"svc": [{"name": "a"}]}), ["svc"]
        )
        bridge.add_provider("p2", FakeProvider({"tasks": []}), ["tasks"])
        eng = SocraticEngine()
        bridge.register(eng)

        tree = {
            "op": "AND",
            "children": [
                {"predicate": "canon_query", "args": ["svc"]},
                {"predicate": "canon_query", "args": ["tasks"]},
            ],
        }
        ev = eng.evaluate(tree)
        assert ev.truth == Truth.UNKNOWN  # AND with UNKNOWN child
