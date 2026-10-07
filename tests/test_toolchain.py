"""Unit tests that need no Mort compiler."""

import pytest

from mort_mcp.reference import Section, search
from mort_mcp.toolchain import SourceSet, ToolchainError, find_toolchain, parse_diagnostics


def test_missing_toolchain_is_explicit(monkeypatch):
    monkeypatch.delenv("MORT_HOME", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(ToolchainError, match="MORT_HOME"):
        find_toolchain()


def test_bad_mort_home(monkeypatch, tmp_path):
    monkeypatch.setenv("MORT_HOME", str(tmp_path))
    with pytest.raises(ToolchainError, match="no mortc.py"):
        find_toolchain()


def test_sourceset_requires_input_and_existing_files(tmp_path):
    with pytest.raises(ValueError):
        SourceSet(None, None)
    with pytest.raises(FileNotFoundError):
        SourceSet(None, [str(tmp_path / "missing.mx")])
    with SourceSet("fn main() -> int { return 0; }", None) as s:
        assert s.display(s.paths[0]) == "<source>"


def test_parse_diagnostics_skips_noise():
    out = 'mortc: wrote x\n{"severity": "error", "message": "m", "line": 2}\n{broken\n'
    assert parse_diagnostics(out) == [{"severity": "error", "message": "m", "line": 2}]


def test_search_ranks_heading_matches_first():
    secs = [
        Section("a.md", "Integers", "overflow wraps " * 3),
        Section("a.md", "Overflow semantics", "integers trap on overflow"),
    ]
    assert search(secs, "overflow", limit=1).startswith("## Overflow semantics")
