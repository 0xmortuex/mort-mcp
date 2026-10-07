"""Offline language reference: std module signatures and doc search.

An agent has never seen Mort in training, so it needs to look things up the
way a person would: "what's in std.strings?", "how do resource structs
work?". These read the compiler's own std/ sources and docs/ markdown, so
answers always match the installed compiler.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

_DECL_RE = re.compile(r"^pub\s+(fn|struct|resource\s+struct|enum|const|type)\b")


def list_modules(std_dir: str) -> list[str]:
    return sorted(os.path.splitext(n)[0] for n in os.listdir(std_dir) if n.endswith(".mx"))


def module_api(std_dir: str, module: str) -> str:
    """Public declarations of a std module, with their leading // comments."""
    name = module.removeprefix("std.")
    path = os.path.join(std_dir, name + ".mx")
    if not os.path.isfile(path):
        raise KeyError(f"no std module {module!r}. Available: {', '.join(list_modules(std_dir))}")
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    out: list[str] = []
    header = [ln for ln in lines[:5] if ln.startswith("//")]
    if header:
        out.extend(header)
        out.append("")
    imports = [ln.strip() for ln in lines if ln.startswith("import ")]
    if imports:
        out.append("// depends on: " + ", ".join(i.removeprefix("import ").rstrip(";") for i in imports))
        out.append("")
    comment: list[str] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        stripped = ln.strip()
        if stripped.startswith("//") and not ln.startswith((" ", "\t")):
            comment.append(stripped)
        elif _DECL_RE.match(stripped):
            sig = stripped
            # Signatures can wrap; join until the body/terminator starts.
            while not sig.rstrip().endswith(("{", ";")) and i + 1 < len(lines):
                i += 1
                sig += " " + lines[i].strip()
            sig = sig.rstrip(" {").rstrip()
            if sig.startswith(("pub struct", "pub resource struct", "pub enum")):
                # Include the fields/variants: they're the API too.
                body = []
                while i + 1 < len(lines) and not lines[i + 1].startswith("}"):
                    i += 1
                    if lines[i].strip():
                        body.append("    " + lines[i].strip())
                sig += " {\n" + "\n".join(body) + "\n}"
            out.extend(comment)
            out.append(sig + ("" if sig.endswith("}") else ";"))
            out.append("")
            comment = []
        elif stripped:
            comment = []
        i += 1
    return f"// std.{name} ({os.path.basename(path)})\n" + "\n".join(out).rstrip()


@dataclass
class Section:
    doc: str
    heading: str
    body: str


def load_sections(docs_dir: str) -> list[Section]:
    sections: list[Section] = []
    for name in sorted(os.listdir(docs_dir)):
        if not name.endswith(".md"):
            continue
        with open(os.path.join(docs_dir, name), encoding="utf-8") as fh:
            text = fh.read()
        heading: str = name
        buf: list[str] = []
        for line in text.splitlines():
            if re.match(r"^#{1,4} ", line):
                if buf:
                    sections.append(Section(name, heading, "\n".join(buf).strip()))
                heading, buf = line.lstrip("#").strip(), []
            else:
                buf.append(line)
        if buf:
            sections.append(Section(name, heading, "\n".join(buf).strip()))
    return sections


def search(sections: list[Section], query: str, limit: int = 3,
           max_chars: int = 6000) -> str:
    terms = [t for t in re.findall(r"[\w.]+", query.lower()) if len(t) > 1]
    if not terms:
        raise ValueError("query has no searchable words")

    def score(s: Section) -> float:
        h, b = s.heading.lower(), s.body.lower()
        total = 0.0
        for t in terms:
            total += 8 * h.count(t) + min(b.count(t), 10)
        # Prefer sections that match every term.
        if all(t in h or t in b for t in terms):
            total *= 2
        return total

    ranked = sorted((s for s in sections if score(s) > 0), key=score, reverse=True)[:limit]
    if not ranked:
        headings = ", ".join(s.heading for s in sections if s.doc == "language-specification.md")[:800]
        return f"No matches for {query!r}. Spec sections: {headings}"
    out, used = [], 0
    for s in ranked:
        block = f"## {s.heading}  ({s.doc})\n\n{s.body}"
        if used + len(block) > max_chars:
            block = block[: max(max_chars - used, 500)] + "\n[...truncated]"
        out.append(block)
        used += len(block)
        if used >= max_chars:
            break
    return "\n\n---\n\n".join(out)
