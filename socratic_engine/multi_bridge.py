"""Multi-Bridge for socratic-engine — routes canon_* predicates to providers.

Routes queries to the correct provider based on domain. Supports
multiple providers with lazy loading and error isolation.

Usage:
    from socratic_engine.multi_bridge import MultiBridge

    bridge = MultiBridge()
    bridge.add_provider('agent-state', tasks_provider, ['tasks', 'sessions'])
    bridge.add_provider('infra-state', ssh_provider, ['services', 'lxcs'])
    bridge.register(engine)  # registers canon_* predicates on the engine

Config-driven:
    bridge = MultiBridge.from_config('/path/to/bridge_config.json')
    bridge.register(engine)
"""
from __future__ import annotations

import json
import importlib
import logging
import time
from pathlib import Path
from typing import Any, Optional

from .engine import PredicateResult, SocraticEngine, Truth

logger = logging.getLogger(__name__)


def _normalize_filter(filter_arg: Any) -> Optional[dict]:
    """Acepta dict o JSON-string; None si no es parseable."""
    if filter_arg is None:
        return {}
    if isinstance(filter_arg, dict):
        return filter_arg
    if isinstance(filter_arg, str):
        try:
            parsed = json.loads(filter_arg)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
    return None


class ProviderEntry:
    """Wrapper for a registered provider with metadata and health tracking."""

    def __init__(self, name: str, provider: Any, domains: list[str]):
        self.name = name
        self.provider = provider
        self.domains = domains
        self.status = 'active'
        # Health tracking (GAP-6)
        self._healthy = True
        self._last_error: Optional[str] = None
        self._last_check: Optional[float] = None  # monotonic timestamp
        self._consecutive_failures = 0

    def query(self, domain: str, filter_dict: dict) -> list[dict]:
        try:
            result = self.provider.query(domain, filter_dict)
            self._record_success()
            return result
        except Exception as e:
            self._record_failure(str(e))
            logger.warning(
                f"Provider '{self.name}' query failed for domain "
                f"'{domain}': {e}"
            )
            raise

    def list_domains(self) -> list[str]:
        try:
            domains = self.provider.list_domains()
            self._record_success()
            return domains
        except Exception as e:
            self._record_failure(str(e))
            logger.warning(
                f"Provider '{self.name}' list_domains failed: {e}"
            )
            return []

    def _record_success(self) -> None:
        """Record a successful interaction."""
        self._healthy = True
        self._last_error = None
        self._last_check = time.monotonic()
        self._consecutive_failures = 0

    def _record_failure(self, error: str) -> None:
        """Record a failed interaction."""
        self._consecutive_failures += 1
        self._last_error = error
        self._last_check = time.monotonic()
        # Mark unhealthy after 3 consecutive failures
        if self._consecutive_failures >= 3:
            self._healthy = False

    @property
    def health(self) -> dict:
        """Return health metadata for this provider."""
        return {
            "healthy": self._healthy,
            "last_error": self._last_error,
            "last_check": self._last_check,
            "consecutive_failures": self._consecutive_failures,
        }


class MultiBridge:
    """Routes canon_* predicates to multiple providers by domain.

    Maintains a domain -> provider mapping.  When a canon_* predicate is
    called, it looks up the correct provider and delegates the query.

    Backward compatible: same predicate names as StateCanonBridge.
    """

    PREFIX = "canon_"

    def __init__(self):
        self._providers: dict[str, ProviderEntry] = {}
        self._domain_map: dict[str, str] = {}  # domain -> provider name
        self.engine: Optional[SocraticEngine] = None

    def add_provider(
        self,
        name: str,
        provider: Any,
        domains: Optional[list[str]] = None,
    ) -> None:
        """Register a provider.  If *domains* is None, use provider.list_domains()."""
        if domains is None:
            try:
                domains = provider.list_domains()
            except Exception:
                domains = []

        entry = ProviderEntry(name, provider, domains)
        self._providers[name] = entry

        for domain in domains:
            if domain in self._domain_map:
                existing = self._domain_map[domain]
                logger.warning(
                    f"Domain '{domain}' already registered by "
                    f"'{existing}', overwritten by '{name}'"
                )
            self._domain_map[domain] = name

        logger.info(
            f"Registered provider '{name}' with {len(domains)} domains"
        )

    def remove_provider(self, name: str) -> None:
        """Unregister a provider and clean up domain mappings."""
        if name not in self._providers:
            return

        entry = self._providers.pop(name)
        to_remove = [d for d, n in self._domain_map.items() if n == name]
        for d in to_remove:
            del self._domain_map[d]

        logger.info(
            f"Removed provider '{name}' ({len(entry.domains)} domains)"
        )

    def register(self, engine: SocraticEngine) -> None:
        """Register all canon_* predicates on the engine."""
        self.engine = engine
        engine.register("canon_query")(self._canon_query)
        engine.register("canon_matches")(self._canon_matches)
        engine.register("canon_field_equals")(self._canon_field_equals)
        engine.register("canon_drift")(self._canon_drift)
        engine.register("canon_domains")(self._canon_domains)
        engine.register("canon_providers")(self._canon_providers)

    # ── helpers ─────────────────────────────────────────────────────────

    def _get_provider(self, domain: str) -> Optional[ProviderEntry]:
        """Look up the provider for a domain."""
        name = self._domain_map.get(domain)
        if name is None:
            return None
        return self._providers.get(name)

    def _records(
        self, domain: str, filter_arg: Any
    ) -> tuple[Optional[list[dict]], Optional[dict]]:
        """Query the correct provider for records.

        Returns (records, routing_info). routing_info is None if the
        domain is unknown. Otherwise it contains provider name and
        latency (GAP-7: routing observability).
        """
        filt = _normalize_filter(filter_arg)
        if filt is None:
            return None, None

        entry = self._get_provider(domain)
        if entry is None:
            return None, None  # unknown domain -> UNKNOWN

        t0 = time.monotonic()
        try:
            records = entry.query(domain, filt)
            latency_ms = (time.monotonic() - t0) * 1000
            routing = {
                "provider": entry.name,
                "domain": domain,
                "latency_ms": round(latency_ms, 1),
                "record_count": len(records) if records else 0,
            }
            return records, routing
        except (ValueError, KeyError, TypeError):
            latency_ms = (time.monotonic() - t0) * 1000
            routing = {
                "provider": entry.name,
                "domain": domain,
                "latency_ms": round(latency_ms, 1),
                "error": True,
            }
            return None, routing
        except Exception:
            latency_ms = (time.monotonic() - t0) * 1000
            routing = {
                "provider": entry.name,
                "domain": domain,
                "latency_ms": round(latency_ms, 1),
                "error": True,
            }
            return None, routing

    # ── predicates ──────────────────────────────────────────────────────

    def _canon_query(
        self, domain: str, filter_arg: Any = None, **kw
    ) -> PredicateResult:
        records, routing = self._records(domain, filter_arg)
        if records is None:
            entry = self._get_provider(domain)
            reason = "unknown_domain" if entry is None else "query_failed"
            evidence = {"domain": domain, "reason": reason}
            if routing:
                evidence["routing"] = routing
            return PredicateResult(
                truth=Truth.UNKNOWN,
                certified=False,
                evidence=evidence,
                source="canon_query",
            )
        if not records:
            evidence = {
                "domain": domain,
                "filter": filter_arg,
                "reason": "no_records",
            }
            if routing:
                evidence["routing"] = routing
            return PredicateResult(
                truth=Truth.UNKNOWN,
                certified=False,
                evidence=evidence,
                source="canon_query",
            )
        evidence = {"domain": domain, "count": len(records)}
        if routing:
            evidence["routing"] = routing
        return PredicateResult(
            truth=Truth.TRUE,
            certified=True,
            evidence=evidence,
            source="canon_query",
        )

    def _canon_matches(
        self,
        domain: str,
        filter_arg: Any,
        expected_arg: Any,
        **kw,
    ) -> PredicateResult:
        records, routing = self._records(domain, filter_arg)
        if records is None or not records:
            evidence = {"domain": domain, "reason": "no_evidence"}
            if routing:
                evidence["routing"] = routing
            return PredicateResult(
                truth=Truth.UNKNOWN,
                certified=False,
                evidence=evidence,
                source="canon_matches",
            )
        expected = _normalize_filter(expected_arg)
        if expected is None:
            return PredicateResult(
                truth=Truth.UNKNOWN,
                certified=False,
                evidence={
                    "domain": domain,
                    "reason": "invalid_expected",
                },
                source="canon_matches",
            )
        ok = all(
            all(r.get(k) == v for k, v in expected.items())
            for r in records
        )
        return PredicateResult(
            truth=Truth.TRUE if ok else Truth.FALSE,
            certified=True,
            evidence={
                "domain": domain,
                "expected": expected,
                "records": records,
            },
            source="canon_matches",
        )

    def _canon_field_equals(
        self,
        domain: str,
        filter_arg: Any,
        field: str,
        expected: Any,
        **kw,
    ) -> PredicateResult:
        records, routing = self._records(domain, filter_arg)
        if records is None or not records:
            evidence = {"domain": domain, "reason": "no_evidence"}
            if routing:
                evidence["routing"] = routing
            return PredicateResult(
                truth=Truth.UNKNOWN,
                certified=False,
                evidence=evidence,
                source="canon_field_equals",
            )
        if field not in records[0]:
            return PredicateResult(
                truth=Truth.UNKNOWN,
                certified=False,
                evidence={
                    "domain": domain,
                    "field": field,
                    "reason": "field_missing",
                },
                source="canon_field_equals",
            )
        ok = all(r.get(field) == expected for r in records)
        return PredicateResult(
            truth=Truth.TRUE if ok else Truth.FALSE,
            certified=True,
            evidence={
                "domain": domain,
                "field": field,
                "expected": expected,
                "values": [r.get(field) for r in records],
            },
            source="canon_field_equals",
        )

    def _canon_drift(
        self,
        domain: str,
        filter_arg: Any,
        declared_field: str,
        observed_field: str,
        **kw,
    ) -> PredicateResult:
        records, routing = self._records(domain, filter_arg)
        if records is None or not records:
            evidence = {"domain": domain, "reason": "no_evidence"}
            if routing:
                evidence["routing"] = routing
            return PredicateResult(
                truth=Truth.UNKNOWN,
                certified=False,
                evidence=evidence,
                source="canon_drift",
            )
        drift = [
            {
                "name": r.get("name", i),
                declared_field: r.get(declared_field),
                observed_field: r.get(observed_field),
            }
            for i, r in enumerate(records)
            if r.get(declared_field) != r.get(observed_field)
        ]
        if drift:
            return PredicateResult(
                truth=Truth.FALSE,
                certified=True,
                evidence={"domain": domain, "drift": drift},
                source="canon_drift",
            )
        return PredicateResult(
            truth=Truth.TRUE,
            certified=True,
            evidence={"domain": domain, "drift": []},
            source="canon_drift",
        )

    def _canon_domains(self, **kw) -> PredicateResult:
        """List all available domains across all providers."""
        all_domains: list[str] = []
        counts: dict[str, int] = {}
        for name, entry in self._providers.items():
            try:
                domains = entry.list_domains()
                all_domains.extend(domains)
                for d in domains:
                    counts[d] = counts.get(d, 0) + 1
            except Exception as e:
                logger.warning(
                    f"Provider '{name}' list_domains failed: {e}"
                )

        return PredicateResult(
            truth=Truth.TRUE,
            certified=True,
            evidence={
                "domains": sorted(set(all_domains)),
                "counts": counts,
                "total_providers": len(self._providers),
            },
            source="canon_domains",
        )

    def _canon_providers(self, **kw) -> PredicateResult:
        """List all registered providers with their status and health."""
        providers = []
        for name, entry in self._providers.items():
            try:
                domains = entry.list_domains()
                status = "active"
            except Exception:
                domains = entry.domains  # fallback to declared
                status = "error"

            providers.append(
                {
                    "name": name,
                    "domains": domains,
                    "status": status,
                    "declared_domains": entry.domains,
                    "health": entry.health,
                }
            )

        # Truth reflects reality: UNKNOWN if any provider is unhealthy
        unhealthy = [p for p in providers if not p["health"]["healthy"]]
        truth = Truth.UNKNOWN if unhealthy else Truth.TRUE

        return PredicateResult(
            truth=truth,
            certified=len(unhealthy) == 0,
            evidence={
                "providers": providers,
                "total": len(providers),
                "unhealthy_count": len(unhealthy),
            },
            source="canon_providers",
        )

    # ── config loading ──────────────────────────────────────────────────

    @classmethod
    def from_config(cls, config_path: str | Path) -> "MultiBridge":
        """Create a MultiBridge from a JSON config file.

        Config format::

            {
                "version": 1,
                "bridges": [
                    {
                        "name": "agent-state",
                        "provider_class": "VsmStateProvider",
                        "module": "instances.tasks_provider",
                        "init_args": {"vsm_path": "/path/to/TASKS.vsm"},
                        "domains": ["tasks", "sessions"]
                    },
                    ...
                ]
            }
        """
        config_path = Path(config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config not found: {config_path}")

        with open(config_path) as f:
            config = json.load(f)

        if config.get("version") != 1:
            raise ValueError(
                f"Unsupported config version: {config.get('version')}"
            )

        bridge = cls()

        for entry in config.get("bridges", []):
            name = entry["name"]
            module_path = entry["module"]
            class_name = entry["provider_class"]
            init_args = entry.get("init_args", {})
            domains = entry.get("domains")

            try:
                # Lazy import
                module = importlib.import_module(module_path)
                provider_class = getattr(module, class_name)
                provider = provider_class(**init_args)
                bridge.add_provider(name, provider, domains)
            except Exception as e:
                logger.error(f"Failed to load provider '{name}': {e}")
                # Continue with remaining providers

        return bridge


__all__ = ["MultiBridge", "ProviderEntry"]
