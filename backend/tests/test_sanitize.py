"""Paste-artifact sanitizer, verified against the REAL yosys lexer: the exact
non-breaking-space failure a user hit must synthesize cleanly after sanitizing.
"""
from app.api.deps import get_schematic_pipeline
from app.pipeline.sanitize import sanitize_verilog

NBSP = " "
ZWSP = "​"


def test_non_breaking_space_becomes_real_space():
    # A NBSP where a normal space belongs -> yosys "unexpected invalid token".
    dirty = f"module m (input{NBSP}wire a, output y); assign y = a; endmodule"
    clean = sanitize_verilog(dirty)
    assert NBSP not in clean
    assert clean.isascii()
    # And it now actually synthesizes.
    res = get_schematic_pipeline().build(clean, "m")
    assert res.error is None, res.error


def test_strips_zero_width_and_normalizes_quotes_and_dashes():
    dirty = f"a{ZWSP}b “x” ‘y’ – — −"
    clean = sanitize_verilog(dirty)
    assert clean == 'ab "x" \'y\' - - -'


def test_leaves_plain_ascii_untouched():
    src = "module full_adder(input a, output y);\n  assign y = a;\nendmodule\n"
    assert sanitize_verilog(src) == src


def test_leaves_tolerated_comment_symbols_alone():
    # Visible non-ASCII inside comments (arrow, mid-dot) is fine for the tools; we
    # only rewrite the dangerous look-alikes, not every non-ASCII byte.
    src = "// AND plane → OR plane, P0·C0\nmodule m(input a, output y); assign y=a; endmodule"
    clean = sanitize_verilog(src)
    assert "→" in clean and "·" in clean  # left untouched
    assert get_schematic_pipeline().build(clean, "m").error is None
