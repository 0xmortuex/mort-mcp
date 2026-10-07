# mort-mcp

**Let an AI agent write a language it has never seen.**

<!-- mcp-name: io.github.0xmortuex/mort-mcp -->

[Mort](https://github.com/0xmortuex/Mort) is a statically typed systems language that
compiles to C. It's the language [MORT OS](https://github.com/0xmortuex/MortOS) is
written in. No model has Mort in its training data, so an agent asked to write it
will guess Rust-like syntax and get it wrong.

mort-mcp gives the agent what a human newcomer would use: a fast type checker with
precise errors, a way to run programs, the language spec to search, and the exact
signatures of the standard library.

```
> mort_check
FAILED:
error: <source>:4:1: argument 1 of 'strings.starts_with' expects []const u8, got *u8
        if strings.starts_with("mortos", "mort") {

> mort_std strings
// First byte offset of `needle` in `text`, or None if it does not occur.
pub fn index_of(text: []const u8, needle: []const u8) -> Option<u64>;
...

> mort_run
[exit 0]
1
```

## Install

You need the Mort compiler. The simplest setup is a checkout, which also brings the
docs and examples:

```bash
git clone https://github.com/0xmortuex/Mort
pip install mort-mcp ziglang     # ziglang = zero-install C backend for mort_run
claude mcp add mort --env MORT_HOME=/path/to/Mort -- mort-mcp
```

Without `MORT_HOME`, mort-mcp uses a `mortc` on your PATH
(`pip install git+https://github.com/0xmortuex/Mort`). Checking, running and std
lookup all work that way. `mort_docs` and `mort_examples` need the checkout.

## Tools

| Tool | What it does |
|------|--------------|
| `mort_check` | Type-check `source` text or `files` without building. Fast, and needs no C compiler. Returns diagnostics as `file:line:col` with the source line. |
| `mort_run` | Compile and run, with `stdin`, `args` and a timeout. Reports output and exit code. |
| `mort_emit_c` | Show the generated C. `freestanding=True` shows the kernel-mode output. |
| `mort_format` | Format with the official formatter (`mortc fmt`). |
| `mort_std` | List std modules, or show one module's public API: exact signatures, struct fields and doc comments. |
| `mort_docs` | Search the language specification and reference docs, e.g. "resource struct cleanup" or "integer overflow". |
| `mort_examples` | List or read the compiler's example programs. |
| `mort_version` | Compiler and language version, and where the compiler was found. |

Every tool calls `mortc` through its command-line interface, and reads std signatures
and docs from the installed compiler. Answers therefore match the version you're
running, even as the language changes.

## Tests

```bash
pip install ".[test]" "ruff==0.16.0" "mypy==2.3.0" ziglang
ruff check src tests && mypy --strict src
MORT_HOME=/path/to/Mort pytest tests
```

Without `MORT_HOME`, only the unit tests and the MCP handshake test run. CI checks
out the latest Mort and also runs every night, so a change to the compiler's CLI or
docs layout shows up as a failing build.

## License

MIT
