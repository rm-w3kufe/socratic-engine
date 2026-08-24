"""VSM Document Provider for socratic-engine.

Provides structured access to VSM documentation files on the filesystem.
Parses VSM headers and returns metadata for certification queries.

Usage:
    from socratic_engine.providers.vsm_doc import VsmDocProvider

    provider = VsmDocProvider(root="/path/to/docs/spec_revision/system")
    domains = provider.list_domains()  # ['boot', 's1-operations', ...]
    records = provider.query('boot', {'name': 'covenant'})
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional


# VSM header pattern: ⟦ name | id | version | date ⟧
# Matches ⟦/⟧ (U+27E6/U+27E7) and ¦ (U+00A6) for backward compatibility
VSM_HEADER_RE = re.compile(
    r"[\u27e6\u00a6]\s*"
    r"(?P<name>[^|]+?)\s*\|\s*"
    r"(?P<id>[^|]+?)\s*\|\s*"
    r"vsm-(?P<version>[^|]+?)\s*\|\s*"
    r"(?P<date>[^\u27e6\u27e7\u00a6]+?)\s*[\u27e7\u00a6]"
)

# @status pattern
VSM_STATUS_RE = re.compile(r"@status\s+(\w+)")


def parse_vsm_header(filepath: Path) -> Optional[dict]:
    """Parse a VSM file header and return metadata.

    Returns dict with keys: name, id, version, date, status, path,
    filename, size_bytes, modified_at — or None if the file does not
    have a valid VSM header.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            # Read first 20 lines for header + status
            lines = [f.readline() for _ in range(20)]
    except (OSError, UnicodeDecodeError):
        return None

    header_match = None
    status = None

    for line in lines:
        if header_match is None:
            header_match = VSM_HEADER_RE.search(line)
        if status is None:
            status_match = VSM_STATUS_RE.search(line)
            if status_match:
                status = status_match.group(1)
        if header_match and status:
            break

    if header_match is None:
        return None

    stat = filepath.stat()

    return {
        "name": header_match.group("name").strip(),
        "id": header_match.group("id").strip(),
        "version": header_match.group("version").strip(),
        "date": header_match.group("date").strip(),
        "status": status or "unknown",
        "path": str(filepath),
        "filename": filepath.name,
        "size_bytes": stat.st_size,
        "modified_at": stat.st_mtime,
    }


class VsmDocProvider:
    """Provider for VSM documentation on the filesystem.

    Scans a root directory for ``.vsm`` files, parses their headers,
    and exposes them as queryable records.

    Domains are derived from the directory structure::

        root/boot/            -> domain ``boot``
        root/s1-operations/   -> domain ``s1-operations``
        root/s2-coordination/ -> domain ``s2-coordination``
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)
        if not self.root.exists():
            raise FileNotFoundError(
                f"VSM doc root not found: {self.root}"
            )
        if not self.root.is_dir():
            raise NotADirectoryError(
                f"VSM doc root is not a directory: {self.root}"
            )

        # Cache: domain -> list of parsed headers
        self._cache: dict[str, list[dict]] = {}
        self._scan()

    def _scan(self) -> None:
        """Scan root directory and parse all .vsm files."""
        self._cache.clear()

        for subdir in sorted(self.root.iterdir()):
            if not subdir.is_dir():
                continue
            if subdir.name.startswith("."):
                continue

            domain = subdir.name
            records = []

            for vsm_file in sorted(subdir.glob("**/*.vsm")):
                header = parse_vsm_header(vsm_file)
                if header:
                    header["domain"] = domain
                    records.append(header)

            if records:
                self._cache[domain] = records

    def query(
        self, domain: str, filter_dict: Optional[dict] = None
    ) -> list[dict]:
        """Query records in a domain with optional filter.

        Filter keys can be any field from the header:
            name, id, version, date, status, filename, domain
        """
        records = self._cache.get(domain, [])

        if filter_dict:
            records = [
                r
                for r in records
                if all(r.get(k) == v for k, v in filter_dict.items())
            ]

        return records

    def list_domains(self) -> list[str]:
        """Return all available domains."""
        return sorted(self._cache.keys())

    def schema(self, domain: str) -> dict:
        """Return field names and types for a domain."""
        records = self._cache.get(domain, [])
        if not records:
            return {}

        # Infer schema from first record
        return {key: type(value).__name__ for key, value in records[0].items()}

    def reload(self) -> None:
        """Force rescan of the filesystem."""
        self._scan()

    def get_full_content(
        self, domain: str, name: str
    ) -> Optional[str]:
        """Read the full content of a VSM file by domain and name.

        This is for predicates that need the full document content
        (e.g., doc_has_status, type_prefix on content).
        """
        records = self._cache.get(domain, [])
        for r in records:
            if r.get("name") == name:
                try:
                    with open(r["path"], "r", encoding="utf-8") as f:
                        return f.read()
                except (OSError, UnicodeDecodeError):
                    return None
        return None


__all__ = ["VsmDocProvider", "parse_vsm_header"]
