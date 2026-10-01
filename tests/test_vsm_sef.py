"""Tests A3 — VSM→SEF derivation (roadmap v030 §3.4, FASE 1-3).

FASE 1: mapping + templates (test_derive_kind_*, shapes)
FASE 2: reglas de derivación + invariantes (derive_from_vsm_block, check_*)
FASE 3: template files (render, generate, round-trip, evaluación)
"""
from __future__ import annotations

import pytest

from socratic_engine.engine import SocraticEngine
from socratic_engine.tree import SocraticTreeBuilder, load_tree, parse_socratic_block
from socratic_engine.vsm_sef import (
    SYSTEM_KIND,
    check_invariants,
    check_vsm_block_invariants,
    derive_from_vsm_block,
    derive_kind,
    derive_tree,
    generate_template_files,
    render_template_file,
    template_stem,
)


# ── FASE 1: mapping ────────────────────────────────────────────────────────


class TestDeriveKind:
    def test_maps_five_systems(self):
        assert derive_kind("S1") == "execution"
        assert derive_kind("S2") == "routing"
        assert derive_kind("S3") == "validation"
        assert derive_kind("S4") == "hypothesis"
        assert derive_kind("S5") == "covenant"

    def test_unknown_system_raises(self):
        with pytest.raises(ValueError, match="desconocido"):
            derive_kind("S0")

    def test_system_kind_covers_s1_to_s5(self):
        assert set(SYSTEM_KIND) == {"S1", "S2", "S3", "S4", "S5"}


class TestTemplates:
    def test_every_template_builds(self):
        """El builder valida estructura + predicados de todos los templates."""
        engine = SocraticEngine()
        for system in SYSTEM_KIND:
            SocraticTreeBuilder(engine).build(derive_tree(system))

    def test_shapes_are_distinct_per_system(self):
        """Cada sistema deriva un shape distinto (se preserva la identidad)."""
        shapes = {
            system: str(derive_tree(system)) for system in SYSTEM_KIND
        }
        # S3 y S4 comparten profundidad AND/NOT pero difieren en root op o hijos
        assert derive_tree("S1") != derive_tree("S2")  # AND vs OR
        assert derive_tree("S3") != derive_tree("S4")  # AND vs IMPLIES
        assert derive_tree("S1") != derive_tree("S5")  # slots distintos
        assert len(set(shapes.values())) == 5

    def test_deterministic(self):
        """R10: mismos inputs → mismos outputs."""
        for system in SYSTEM_KIND:
            assert derive_tree(system) == derive_tree(system)


# ── FASE 2: derivation rules + invariantes ────────────────────────────────


def _full_block() -> dict:
    return {
        "S1": {"V": "vos-kernel"},
        "S2": {"V": "vsl-bus"},
        "S3": {"V": "vsf-nucleus"},
        "S4": {"V": "sci-01"},
        "S5": "rmw3",
        "S3*_channel": "rmw3 @sporadic",  # canal, no subsystemo
        "E": {"L_phys": "hardware"},
    }


class TestDerivationRules:
    def test_full_block_yields_five_trees(self):
        derived = derive_from_vsm_block(_full_block())
        assert set(derived) == {"S1", "S2", "S3", "S4", "S5"}
        for system, entry in derived.items():
            assert entry["kind"] == SYSTEM_KIND[system]
            assert entry["tree"] == derive_tree(system)

    def test_channel_and_metadata_ignored(self):
        derived = derive_from_vsm_block(_full_block())
        assert "S3*_channel" not in derived
        assert "E" not in derived

    def test_missing_systems_reported(self):
        block = {"S1": "x", "S2": "y"}
        violations = check_vsm_block_invariants(block)
        assert "missing-S3" in violations[0]
        assert len(violations) == 3  # S3, S4, S5

    def test_full_block_invariants_clean(self):
        assert check_vsm_block_invariants(_full_block()) == []


class TestCheckInvariants:
    def test_ok_template_has_no_violations(self):
        for system in SYSTEM_KIND:
            assert check_invariants(system, derive_tree(system)) == []

    def test_detects_template_swap(self):
        """Template S2 usado como S1 → mismatch (propiedades no preservadas)."""
        violations = check_invariants("S1", derive_tree("S2"))
        assert any(v.startswith("template-mismatch") for v in violations)

    def test_detects_invalid_tree(self):
        """NOT con 2 hijos → invalid-tree (arity violada)."""
        bad = {"op": "NOT", "children": [
            {"predicate": "ctx_has", "args": ["a"]},
            {"predicate": "ctx_has", "args": ["b"]},
        ]}
        violations = check_invariants("S1", bad)
        assert any(v.startswith("invalid-tree") for v in violations)

    def test_unknown_system(self):
        violations = check_invariants("S9", derive_tree("S1"))
        assert len(violations) == 1
        assert "desconocido" in violations[0]


class TestEvaluation:
    """Los templates evaluados con slots llenos certifican TRUE (trivaluado)."""

    @pytest.fixture
    def engine(self):
        return SocraticEngine()

    @staticmethod
    def _true_ctx(system: str) -> dict:
        """Contexto que certifica TRUE para el template del sistema."""
        if system == "S3":
            return {"invariant_holds": True}  # violation ausente → ctx_not_has TRUE
        if system == "S4":
            return {"observed": True}  # refuted ausente → ctx_not_has TRUE
        from socratic_engine.vsm_sef import template_slot_keys
        return {k: True for k in template_slot_keys(system)}

    @pytest.mark.parametrize("system", sorted(SYSTEM_KIND))
    def test_filled_slots_certify_true(self, engine, system):
        ev = engine.evaluate(derive_tree(system), self._true_ctx(system))
        assert ev.is_true and ev.certified

    @pytest.mark.parametrize("system", sorted(SYSTEM_KIND))
    def test_missing_slots_are_unknown_not_false(self, engine, system):
        ev = engine.evaluate(derive_tree(system), {})
        assert not ev.is_true  # UNKNOWN sin dato (R10), no TRUE

    def test_s3_template_fails_on_violation(self, engine):
        ctx = {"invariant_holds": True, "violation": True}
        ev = engine.evaluate(derive_tree("S3"), ctx)
        assert not ev.is_true  # AND ... NOT violation → FALSE

    def test_s4_template_fails_when_refuted(self, engine):
        ctx = {"observed": True, "refuted": True}
        ev = engine.evaluate(derive_tree("S4"), ctx)
        assert not ev.is_true  # observed AND NOT refuted → FALSE

    def test_s2_primary_route_suffices(self, engine):
        ctx = {"route_primary": True, "route_fallback": None}
        # fallback vacío → UNKNOWN, pero OR con un TRUE certifica
        ev = engine.evaluate(derive_tree("S2"), ctx)
        assert ev.is_true


# ── FASE 3: template files ─────────────────────────────────────────────────


class TestTemplateFiles:
    def test_stem_matches_roadmap(self):
        assert template_stem("S1") == "s1_execution"
        assert template_stem("S2") == "s2_routing"
        assert template_stem("S3") == "s3_validation"
        assert template_stem("S4") == "s4_hypothesis"
        assert template_stem("S5") == "s5_covenant"

    @pytest.mark.parametrize("system", sorted(SYSTEM_KIND))
    def test_render_parses_back_to_same_tree(self, system):
        parsed = parse_socratic_block(render_template_file(system))
        assert parsed == derive_tree(system)

    def test_generate_writes_five_valid_files(self, tmp_path):
        paths = generate_template_files(tmp_path)
        assert len(paths) == 5
        assert sorted(p.name for p in paths) == sorted(
            f"{template_stem(s)}.tree.vsm" for s in SYSTEM_KIND
        )
        for path in paths:
            tree = load_tree(path)
            assert tree is not None, path.name
            system = path.name.split("_")[0].upper()
            assert check_invariants(system, tree) == []

    def test_generated_file_evaluates(self, tmp_path, engine=None):
        paths = generate_template_files(tmp_path)
        engine = engine or SocraticEngine()
        s3 = next(p for p in paths if p.name.startswith("s3_"))
        tree = load_tree(s3)
        ev = engine.evaluate(tree, {"invariant_holds": True, "violation": ""})
        assert ev.is_true and ev.certified

    def test_render_contains_header_and_status(self):
        text = render_template_file("S5")
        assert "vsm-1.2.1" in text
        assert "@status active" in text
        assert "socratic(\"s5_covenant\")" in text
        assert "/s5_covenant_tree" in text
