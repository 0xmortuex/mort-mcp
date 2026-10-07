"""Tools against a real Mort compiler (MORT_HOME). Needs a C compiler or
`pip install ziglang` for the mort_run cases."""

import pytest

from mort_mcp import server as S

pytestmark = pytest.mark.needs_mort

HELLO = "fn main() -> int {\n    print(42);\n    return 0;\n}\n"


def test_version_reports_source():
    out = S.mort_version()
    assert "MORT_HOME=" in out and "language" in out


def test_check_ok_and_error_location():
    assert S.mort_check(source=HELLO) == "OK: no errors."
    bad = "fn main() -> int {\n    let x: int = 5\n    print(x);\n    return 0;\n}\n"
    out = S.mort_check(source=bad)
    assert out.startswith("FAILED:")
    assert "<source>:3" in out and "expected ';'" in out


def test_check_type_error():
    out = S.mort_check(source='fn main() -> int {\n    let x: int = "hi";\n    return 0;\n}\n')
    assert out.startswith("FAILED:") and "<source>:2" in out


def test_run_prints_output():
    assert S.mort_run(source=HELLO) == "[exit 0]\n42"


def test_run_nonzero_exit_and_compile_error():
    assert S.mort_run(source="fn main() -> int {\n    return 3;\n}\n").startswith("[EXIT 3]")
    assert S.mort_run(source="fn main() -> int {\n    retrun 0;\n}\n").startswith("COMPILE FAILED:")


def test_run_timeout_kills_program():
    src = "fn main() -> int {\n    while true {\n    }\n    return 0;\n}\n"
    assert S.mort_run(source=src, timeout_s=2).startswith("TIMED OUT after 2")


def test_run_with_std_import():
    src = (
        "import std.strings;\n\n"
        "fn main() -> int {\n"
        '    if strings.starts_with(slice("mortos" as *const u8, 6), slice("mort" as *const u8, 4)) {\n'
        "        print(1);\n"
        "    }\n"
        "    return 0;\n"
        "}\n"
    )
    assert S.mort_run(source=src) == "[exit 0]\n1"


def test_emit_c():
    c = S.mort_emit_c(source=HELLO)
    assert "main" in c and "42" in c


def test_format_roundtrip():
    out = S.mort_format("fn main() -> int {\nprint(42);\nreturn 0;\n}\n")
    assert "    print(42);" in out


def test_std_listing_and_module_api():
    assert "strings" in S.mort_std()
    api = S.mort_std("std.strings")
    assert "pub fn starts_with(text: []const u8, prefix: []const u8) -> bool;" in api
    assert "// First byte offset of `needle`" in api
    with pytest.raises(KeyError, match="Available"):
        S.mort_std("nope")


def test_docs_search():
    out = S.mort_docs("ownership cleanup")
    assert "##" in out and "ownership" in out.lower()
    assert "No matches" in S.mort_docs("zzzqqq")


def test_examples():
    assert "hello.mx" in S.mort_examples()
    assert "print(42)" in S.mort_examples("hello")


def test_files_mode(tmp_path):
    p = tmp_path / "a.mx"
    p.write_text(HELLO)
    assert S.mort_run(files=[str(p)]) == "[exit 0]\n42"
