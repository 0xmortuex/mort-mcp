"""Locate and drive the Mort compiler (`mortc`) as a subprocess.

mort-mcp talks to Mort only through its CLI, so it keeps working as the
compiler evolves. Resolution order:

1. MORT_HOME - a checkout of github.com/0xmortuex/Mort. Runs
   `python $MORT_HOME/mortc.py`, and also provides docs/ (spec, stdlib).
2. `mortc` on PATH (e.g. `pip install git+https://github.com/0xmortuex/Mort`).
   Compiling and std lookup work; the prose docs aren't installed by pip, so
   mort_docs needs MORT_HOME.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Any


class ToolchainError(RuntimeError):
    pass


@dataclass
class Toolchain:
    command: list[str]
    home: str | None  # repo checkout, if known

    @property
    def docs_dir(self) -> str | None:
        if self.home is None:
            return None
        d = os.path.join(self.home, "docs")
        return d if os.path.isdir(d) else None

    def run(self, args: list[str], timeout: float = 120.0, cwd: str | None = None,
            stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [*self.command, *args], capture_output=True, text=True, timeout=timeout,
                cwd=cwd, input=stdin, encoding="utf-8", errors="replace",
            )
        except subprocess.TimeoutExpired:
            raise ToolchainError(f"mortc {' '.join(args[:2])} timed out after {timeout}s") from None

    def std_dir(self) -> str:
        if self.home is not None and os.path.isdir(os.path.join(self.home, "std")):
            return os.path.join(self.home, "std")
        proc = self.run(["std", "--path"])
        if proc.returncode != 0:
            raise ToolchainError(f"mortc std --path failed: {proc.stderr.strip()}")
        return proc.stdout.splitlines()[0].strip()


def find_toolchain() -> Toolchain:
    home = os.environ.get("MORT_HOME")
    if home:
        driver = os.path.join(home, "mortc.py")
        if not os.path.isfile(driver):
            raise ToolchainError(f"MORT_HOME={home} has no mortc.py - point it at a Mort checkout")
        return Toolchain([sys.executable, driver], os.path.abspath(home))
    exe = shutil.which("mortc")
    if exe:
        return Toolchain([exe], None)
    raise ToolchainError(
        "Mort compiler not found. Either set MORT_HOME to a checkout of "
        "https://github.com/0xmortuex/Mort, or install it so `mortc` is on PATH: "
        "pip install git+https://github.com/0xmortuex/Mort"
    )


class SourceSet:
    """Materialise `source` text and/or existing `files` into compiler inputs.

    Inline source is written to a temp dir as main.mx so imports and file-
    based compilation work exactly as they do for a user's files.
    """

    def __init__(self, source: str | None, files: list[str] | None):
        if not source and not files:
            raise ValueError("pass `source` (Mort code) or `files` (paths to .mx files)")
        self.tmp = tempfile.TemporaryDirectory(prefix="mort-mcp-")
        self.paths: list[str] = []
        if source:
            p = os.path.join(self.tmp.name, "main.mx")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(source)
            self.paths.append(p)
        for f in files or []:
            if not os.path.isfile(f):
                raise FileNotFoundError(f"no such file: {f}")
            self.paths.append(os.path.abspath(f))

    @property
    def dir(self) -> str:
        return self.tmp.name

    def display(self, path: str | None) -> str:
        if not path:
            return "?"
        if os.path.dirname(os.path.abspath(path)) == os.path.abspath(self.tmp.name):
            return "<source>"
        return path

    def __enter__(self) -> SourceSet:
        return self

    def __exit__(self, *exc: object) -> None:
        self.tmp.cleanup()


def parse_diagnostics(output: str) -> list[dict[str, Any]]:
    """mortc --diagnostic-format json prints one JSON object per line."""
    out = []
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def format_diagnostics(diags: list[dict[str, Any]], srcs: SourceSet) -> str:
    lines = []
    for d in diags:
        loc = srcs.display(d.get("file"))
        if d.get("line"):
            loc += f":{d['line']}"
            col = d.get("column") or (d.get("range") or {}).get("start", {}).get("column")
            if col:
                loc += f":{col}"
        lines.append(f"{d.get('severity', 'error')}: {loc}: {d.get('message', '')}")
        if d.get("source"):
            lines.append(f"    {d['source'].rstrip()}")
    return "\n".join(lines)
