"""Tests for VsmDocProvider — VSM filesystem provider."""
from __future__ import annotations

import pytest

from socratic_engine.providers.vsm_doc import VsmDocProvider, parse_vsm_header


# ── parse_vsm_header ─────────────────────────────────────────────────────


class TestParseVsmHeader:
    def test_valid_header(self, tmp_path):
        f = tmp_path / "test.vsm"
        f.write_text(
            "\u00a6 test | TEST-v1 | vsm-1.0 | 2026-08-24 \u00a6\n"
            "@vsm 1.0\n"
            "@status active\n"
        )
        result = parse_vsm_header(f)
        assert result is not None
        assert result["name"] == "test"
        assert result["id"] == "TEST-v1"
        assert result["version"] == "1.0"
        assert result["date"] == "2026-08-24"
        assert result["status"] == "active"
        assert result["filename"] == "test.vsm"

    def test_no_header(self, tmp_path):
        f = tmp_path / "plain.txt"
        f.write_text("just some text\n")
        assert parse_vsm_header(f) is None

    def test_header_no_status(self, tmp_path):
        f = tmp_path / "no_status.vsm"
        f.write_text(
            "\u00a6 test | TEST-v1 | vsm-1.0 | 2026-08-24 \u00a6\n"
            "@vsm 1.0\n"
        )
        result = parse_vsm_header(f)
        assert result is not None
        assert result["status"] == "unknown"

    def test_nonexistent_file(self, tmp_path):
        f = tmp_path / "missing.vsm"
        assert parse_vsm_header(f) is None


# ── VsmDocProvider ───────────────────────────────────────────────────────


class TestVsmDocProvider:
    @pytest.fixture
    def doc_root(self, tmp_path):
        """Create a minimal VSM doc tree."""
        # boot/
        boot = tmp_path / "boot"
        boot.mkdir()
        (boot / "covenant.vsm").write_text(
            "\u00a6 covenant | VSF-COVENANT-v1.2 | vsm-1.2 | 2026-08-16 \u00a6\n"
            "@vsm 1.2\n"
            "@status ratified\n"
        )
        (boot / "hard_rules.vsm").write_text(
            "\u00a6 hard_rules | VSL-HARD-RULES-v1 | vsm-1.2 | 2026-08-16 \u00a6\n"
            "@vsm 1.2\n"
            "@status ratified\n"
        )

        # s1-operations/
        s1 = tmp_path / "s1-operations"
        s1.mkdir()
        (s1 / "s1_spec.vsm").write_text(
            "\u00a6 s1_spec | S1-SPEC-v1 | vsm-1.0 | 2026-08-01 \u00a6\n"
            "@vsm 1.0\n"
            "@status active\n"
        )

        return tmp_path

    def test_list_domains(self, doc_root):
        provider = VsmDocProvider(doc_root)
        domains = provider.list_domains()
        assert "boot" in domains
        assert "s1-operations" in domains

    def test_query_all(self, doc_root):
        provider = VsmDocProvider(doc_root)
        records = provider.query("boot")
        assert len(records) == 2

    def test_query_filter(self, doc_root):
        provider = VsmDocProvider(doc_root)
        records = provider.query("boot", {"name": "covenant"})
        assert len(records) == 1
        assert records[0]["id"] == "VSF-COVENANT-v1.2"
        assert records[0]["status"] == "ratified"

    def test_query_empty_domain(self, doc_root):
        provider = VsmDocProvider(doc_root)
        records = provider.query("nonexistent")
        assert records == []

    def test_schema(self, doc_root):
        provider = VsmDocProvider(doc_root)
        schema = provider.schema("boot")
        assert "name" in schema
        assert "version" in schema

    def test_get_full_content(self, doc_root):
        provider = VsmDocProvider(doc_root)
        content = provider.get_full_content("boot", "covenant")
        assert content is not None
        assert "ratified" in content

    def test_get_full_content_missing(self, doc_root):
        provider = VsmDocProvider(doc_root)
        assert provider.get_full_content("boot", "nonexistent") is None

    def test_reload(self, doc_root):
        provider = VsmDocProvider(doc_root)
        assert len(provider.query("boot")) == 2

        # Add a new file
        (doc_root / "boot" / "new_doc.vsm").write_text(
            "\u00a6 new | NEW-v1 | vsm-1.0 | 2026-08-24 \u00a6\n"
            "@vsm 1.0\n"
            "@status draft\n"
        )
        provider.reload()
        assert len(provider.query("boot")) == 3

    def test_nonexistent_root(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            VsmDocProvider(tmp_path / "nonexistent")

    def test_file_as_root(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("not a dir")
        with pytest.raises(NotADirectoryError):
            VsmDocProvider(f)
