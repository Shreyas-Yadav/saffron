"""Normalize copy-paste artifacts in Verilog before any tool sees it.

Code pasted from docs, chat, or web pages often carries characters that *look* like
plain ASCII but aren't -- a non-breaking space instead of a space, "smart quotes",
en/em dashes, zero-width spaces. yosys/iverilog reject these as `invalid token`,
pointing at a line where the offending character is invisible (a fake space looks
exactly like a real one). That makes for a baffling "syntax error" on code that
looks perfectly fine.

This maps the common look-alikes to their ASCII equivalents so an honest paste just
works. It is intentionally conservative: it only rewrites characters with an
unambiguous ASCII counterpart, and leaves anything else (e.g. a comment arrow or
mid-dot, which the tools tolerate) untouched.

Characters are referenced by codepoint on purpose -- embedding the literal invisible
characters here would be exactly the bug this module exists to fix.
"""
from __future__ import annotations

# Unicode spaces that render like a normal space but aren't (the usual culprit is
# U+00A0, the non-breaking space). All map to a plain ASCII space.
_SPACE_LIKE = [
    0x00A0, 0x1680, 0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006,
    0x2007, 0x2008, 0x2009, 0x200A, 0x202F, 0x205F, 0x3000,
]
# Zero-width / invisible formatting characters and the BOM -- removed outright.
_ZERO_WIDTH = [0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF]

_TRANSLATE: dict[int, str | None] = {
    **{cp: " " for cp in _SPACE_LIKE},
    **{cp: None for cp in _ZERO_WIDTH},
    0x2018: "'", 0x2019: "'", 0x201A: "'", 0x201B: "'",  # single curly quotes -> '
    0x201C: '"', 0x201D: '"', 0x201E: '"', 0x201F: '"',  # double curly quotes -> "
    0x2013: "-", 0x2014: "-", 0x2012: "-", 0x2015: "-",  # en/em/other dashes -> -
    0x2212: "-",                                          # minus sign -> -
}


def sanitize_verilog(text: str) -> str:
    """Return `text` with copy-paste look-alike characters normalized to ASCII."""
    return text.translate(_TRANSLATE)
