"""Formal verification tested against the REAL yosys SAT engine. No LLM key needed:
properties are supplied directly, the way an LLMProvider would emit them.
"""
from pathlib import Path

from app.api.deps import get_formal_pipeline, get_schematic_pipeline

FIXTURES = Path(__file__).parent.parent / "fixtures"
FULL_ADDER = (FIXTURES / "full_adder.v").read_text()

COUNTER = (
    "module ctr(input clk, input rst_n, input en, output reg [3:0] q);\n"
    "  always @(posedge clk)\n"
    "    if (!rst_n) q <= 0; else if (en) q <= q + 1;\n"
    "endmodule"
)

# An `always @*` missing an assignment for `q` when `!en` -> Yosys infers a latch.
LATCHY = (
    "module latchy(input en, input d, output reg q);\n"
    "  always @* if (en) q = d;\n"
    "endmodule"
)


def _netlist(verilog: str, top: str) -> str:
    res = get_schematic_pipeline().build(verilog, top)
    assert res.error is None, res.error
    return res.netlist_json


def _check(result, name_kind):
    return next(c for c in result.checks if c.kind == name_kind)


def test_correct_property_is_proven():
    net = _netlist(FULL_ADDER, "full_adder")
    res = get_formal_pipeline().run(
        FULL_ADDER, net, "full_adder", ["{cout, sum} == a + b + cin"]
    )
    assert res.status == "proven"
    assert _check(res, "intent").status == "passed"
    # Invariants run too, and pass for a clean combinational module.
    assert all(c.status == "passed" for c in res.checks if c.kind == "invariant")


def test_wrong_property_is_refuted_with_counterexample():
    net = _netlist(FULL_ADDER, "full_adder")
    res = get_formal_pipeline().run(
        FULL_ADDER, net, "full_adder", ["sum == (a ^ b)"]  # drops cin -> false
    )
    assert res.status == "refuted"
    assert _check(res, "intent").status == "failed"
    # The failing input vector is rendered as a waveform.
    assert res.counterexample is not None
    names = [s["name"] for s in res.counterexample["signal"]]
    assert "a" in names and "sum" in names


def test_invariants_run_without_properties():
    net = _netlist(FULL_ADDER, "full_adder")
    res = get_formal_pipeline().run(FULL_ADDER, net, "full_adder", [])
    assert res.status == "proven"
    assert {c.kind for c in res.checks} == {"invariant"}
    assert all(c.status == "passed" for c in res.checks)


def test_accidental_latch_fails_invariant():
    net = _netlist(LATCHY, "latchy")
    res = get_formal_pipeline().run(LATCHY, net, "latchy", [])
    assert res.status == "refuted"
    latch = next(c for c in res.checks if "latch" in c.name.lower())
    assert latch.status == "failed"


def test_clocked_module_skips_intent_but_runs_invariants():
    net = _netlist(COUNTER, "ctr")
    res = get_formal_pipeline().run(COUNTER, net, "ctr", ["q == 0"])
    # Intent is skipped on clocked designs; invariants still run (and pass here).
    assert _check(res, "intent").status == "skipped"
    assert any(c.kind == "invariant" and c.status == "passed" for c in res.checks)
    assert res.status == "proven"
