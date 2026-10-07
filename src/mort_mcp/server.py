"""mort-mcp: an MCP server that lets an AI agent write, check and run Mort code."""

from __future__ import annotations

import functools
import os
import subprocess
import sys
from collections.abc import Callable
from typing import Any, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import reference as refmod
from .toolchain import (
    SourceSet,
    ToolchainError,
    find_toolchain,
    format_diagnostics,
    parse_diagnostics,
)

mcp = MCPServer(
    "mort",
    instructions=(
        "Write, type-check and run programs in Mort, a statically typed systems "
        "language that compiles to C (github.com/0xmortuex/Mort). You have not seen "
        "Mort in training - look things up before guessing: mort_docs for language "
        "rules (search the spec), mort_std for a std module's exact signatures. Loop: "
        "write code -> mort_check (fast, no C compiler) -> fix diagnostics -> mort_run. "
        "Programs start at `fn main() -> int`; statements end with `;`; std modules are "
        "imported with `import std.strings;` and called as `strings.trim(...)`. "
        "String literals are `*u8`, not slices: pass one to a `[]const u8` parameter as "
        '`slice("text" as *const u8, 4)`. mort_examples has known-good programs.'
    ),
)


F = TypeVar("F", bound=Callable[..., Any])

# Failures an agent can act on. MCPServer only forwards a ToolError's message
# to the client - anything else arrives as a bare "Error executing tool X" -
# so these are re-raised as ToolError with their text intact. Anything not
# listed here is a genuine bug and stays hidden from the client.
_EXPECTED = (ToolchainError, KeyError, ValueError, FileNotFoundError)


def tool(fn: F) -> F:
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except _EXPECTED as e:
            # KeyError's str() wraps the message in quotes; use the raw text.
            msg = e.args[0] if isinstance(e, KeyError) and e.args else str(e)
            raise ToolError(str(msg)) from e

    mcp.tool()(wrapper)
    return fn


def _out(proc: subprocess.CompletedProcess[str], limit: int = 20000) -> str:
    text = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr.strip() else "")
    text = text.strip()
    if len(text) > limit:
        text = text[:limit] + f"\n[... {len(text) - limit} more characters truncated]"
    return text


@tool
def mort_version() -> str:
    """Report the Mort compiler version, language version and where it was found."""
    tc = find_toolchain()
    v = tc.run(["--version"])
    lv = tc.run(["--language-version"])
    where = f"MORT_HOME={tc.home}" if tc.home else f"PATH: {tc.command[0]}"
    return f"{v.stdout.strip()} (language {lv.stdout.strip()})\nfound via {where}"


@tool
def mort_check(source: str | None = None, files: list[str] | None = None,
               warn_unused: bool = False) -> str:
    """Type-check Mort code without building it (fast; needs no C compiler).

    Pass `source` (a whole program as text) and/or `files` (paths to .mx
    files compiled together as one program). Returns OK or the compiler's
    diagnostics with file:line:column and the offending source line.
    """
    tc = find_toolchain()
    with SourceSet(source, files) as srcs:
        args = ["--check", "--diagnostic-format", "json", *srcs.paths]
        if warn_unused:
            args.insert(0, "--warn-unused")
        proc = tc.run(args, cwd=srcs.dir)
        diags = parse_diagnostics(proc.stdout + "\n" + proc.stderr)
        if proc.returncode == 0 and not diags:
            return "OK: no errors."
        if not diags:
            return f"mortc exited {proc.returncode} without structured diagnostics:\n{_out(proc)}"
        verdict = "OK with warnings" if proc.returncode == 0 else "FAILED"
        return f"{verdict}:\n{format_diagnostics(diags, srcs)}"


@tool
def mort_run(source: str | None = None, files: list[str] | None = None,
             stdin: str = "", args: list[str] | None = None, timeout_s: float = 30.0,
             opt_level: str = "0") -> str:
    """Compile Mort code to a native binary and run it, capturing its output.

    Needs a C compiler (cc/gcc/clang, or `pip install ziglang`). `stdin` is
    fed to the program, `args` are its command-line arguments, and it is
    killed after timeout_s. Reports compile errors the same way mort_check does.
    """
    if opt_level not in ("0", "1", "2", "3", "s"):
        raise ValueError("opt_level must be 0, 1, 2, 3 or s")
    tc = find_toolchain()
    with SourceSet(source, files) as srcs:
        exe = os.path.join(srcs.dir, "prog.exe" if sys.platform == "win32" else "prog")
        build = tc.run(["--diagnostic-format", "json", "-O", opt_level, "-o", exe, *srcs.paths],
                       cwd=srcs.dir, timeout=180)
        if build.returncode != 0 or not os.path.isfile(exe):
            diags = parse_diagnostics(build.stdout + "\n" + build.stderr)
            if diags:
                return "COMPILE FAILED:\n" + format_diagnostics(diags, srcs)
            return f"BUILD FAILED (exit {build.returncode}):\n{_out(build)}"
        try:
            proc = subprocess.run([exe, *(args or [])], input=stdin, capture_output=True,
                                  text=True, timeout=timeout_s, cwd=srcs.dir,
                                  encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired as e:
            partial = (e.stdout or "") if isinstance(e.stdout, str) else ""
            return f"TIMED OUT after {timeout_s}s (killed). Output so far:\n{partial.strip()}"
        status = "exit 0" if proc.returncode == 0 else f"EXIT {proc.returncode}"
        body = _out(proc)
        return f"[{status}]\n{body}" if body else f"[{status}] (no output)"


@tool
def mort_emit_c(source: str | None = None, files: list[str] | None = None,
                freestanding: bool = False) -> str:
    """Show the C that Mort generates for a program (useful to see what a
    construct compiles to, or to debug codegen). freestanding=True emits
    bare-metal C (no libc, no main) as used for the MORT OS kernel."""
    tc = find_toolchain()
    with SourceSet(source, files) as srcs:
        args = ["--emit-c", *srcs.paths]
        if freestanding:
            args.insert(0, "--freestanding")
        proc = tc.run(args, cwd=srcs.dir)
        if proc.returncode != 0:
            diags = parse_diagnostics(proc.stdout + "\n" + proc.stderr)
            return "FAILED:\n" + (format_diagnostics(diags, srcs) if diags else _out(proc))
        return _out(proc, limit=60000)


@tool
def mort_format(source: str) -> str:
    """Format Mort source with the official formatter (`mortc fmt`) and
    return the formatted text."""
    tc = find_toolchain()
    with SourceSet(source, None) as srcs:
        proc = tc.run(["fmt", srcs.paths[0]], cwd=srcs.dir)
        if proc.returncode != 0:
            raise ToolchainError(f"mortc fmt failed:\n{_out(proc)}")
        with open(srcs.paths[0], encoding="utf-8") as fh:
            return fh.read()


@tool
def mort_std(module: str | None = None) -> str:
    """Look up the standard library.

    With no module: list every std module. With a module (e.g. "strings" or
    "std.vec"): its public functions, structs and enums with exact
    signatures and doc comments, read from the installed compiler's source.
    """
    std_dir = find_toolchain().std_dir()
    if module is None:
        mods = refmod.list_modules(std_dir)
        return ("std modules (import with `import std.<name>;`, call as `<name>.fn(...)`):\n"
                + ", ".join(mods))
    return refmod.module_api(std_dir, module)


@tool
def mort_docs(query: str, limit: int = 3) -> str:
    """Search the Mort language specification and reference docs.

    Returns the best-matching sections, e.g. query="resource struct cleanup",
    "integer overflow", "slices", "error propagation ?". Requires MORT_HOME
    (a Mort checkout) since pip installs don't ship the docs.
    """
    tc = find_toolchain()
    docs = tc.docs_dir
    if docs is None:
        raise ToolchainError(
            "Mort docs not available: set MORT_HOME to a checkout of "
            "https://github.com/0xmortuex/Mort (pip installs don't include docs/)."
        )
    if not 1 <= limit <= 10:
        raise ValueError("limit must be between 1 and 10")
    return refmod.search(refmod.load_sections(docs), query, limit)


@tool
def mort_examples(name: str | None = None) -> str:
    """List the compiler's bundled example programs, or show one by name.
    Examples are known-good Mort - a fast way to learn idioms. Needs MORT_HOME."""
    tc = find_toolchain()
    if tc.home is None:
        raise ToolchainError("examples need MORT_HOME set to a Mort checkout")
    ex_dir = os.path.join(tc.home, "examples")
    names = sorted(n for n in os.listdir(ex_dir) if n.endswith(".mx"))
    if name is None:
        return "Examples:\n" + "\n".join(names)
    fname = name if name.endswith(".mx") else name + ".mx"
    if fname not in names:
        raise KeyError(f"no example {name!r}. Available: {', '.join(names)}")
    with open(os.path.join(ex_dir, fname), encoding="utf-8") as fh:
        return fh.read()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
