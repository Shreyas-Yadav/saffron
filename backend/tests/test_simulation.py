"""Simulation pipeline tested against the REAL toolchain (yosys for ports, iverilog
for the sim). No LLM key required.
"""
from pathlib import Path

from app.api.deps import get_schematic_pipeline, get_simulation_pipeline
from app.pipeline.simulate import vcd_to_wavedrom
from app.pipeline.testbench import CombinationalTestbenchGenerator

FIXTURES = Path(__file__).parent.parent / "fixtures"
FULL_ADDER = (FIXTURES / "full_adder.v").read_text()


def _netlist(verilog: str, top: str) -> str:
    res = get_schematic_pipeline().build(verilog, top)
    assert res.error is None, res.error
    return res.netlist_json


def test_full_adder_waveform():
    netlist = _netlist(FULL_ADDER, "full_adder")
    sim = get_simulation_pipeline().run(FULL_ADDER, netlist, "full_adder")

    assert sim.error is None, sim.error
    names = [s["name"] for s in sim.wavedrom["signal"]]
    # Inputs first, then outputs, all present.
    assert names == ["a", "b", "cin", "sum", "cout"]
    waves = {s["name"]: s["wave"] for s in sim.wavedrom["signal"]}
    # 3 inputs -> exhaustive 8-step sweep; sum is high for odd popcount.
    assert len(waves["sum"]) == 8
    assert set(waves["sum"]) <= set("01.")


def test_testbench_rejects_sequential():
    # A clocked module: the combinational generator must bail out cleanly.
    seq = (
        "module ctr(input clk, output reg [3:0] q);\n"
        "  always @(posedge clk) q <= q + 1;\n"
        "endmodule"
    )
    netlist = _netlist(seq, "ctr")
    sim = get_simulation_pipeline().run(seq, netlist, "ctr")
    assert sim.wavedrom is None
    assert sim.error and "sequential" in sim.error.lower()


def test_multibit_bus_expands_to_per_bit_signals():
    netlist = _netlist(FULL_ADDER, "full_adder")
    gen = CombinationalTestbenchGenerator()
    tb = gen.generate(netlist, "full_adder")
    assert "full_adder dut" in tb
    assert "$dumpfile" in tb

    # A 4-bit bus value 0 -> 5 (0b0101) expands to 4 binary signals, MSB first.
    vcd = (
        "$timescale 1ns $end\n$scope module tb $end\n"
        "$var wire 4 ! x [3:0] $end\n$upscope $end\n$enddefinitions $end\n"
        "#0\nb0 !\n#10\nb101 !\n"
    )
    wd = vcd_to_wavedrom(vcd, ["x"])
    names = [s["name"] for s in wd["signal"]]
    assert names == ["x[3]", "x[2]", "x[1]", "x[0]"]
    waves = {s["name"]: s["wave"] for s in wd["signal"]}
    # x: 0 (0b0000) -> 5 (0b0101). Per bit across the two steps:
    assert waves["x[0]"] == "01"  # 0 -> 1
    assert waves["x[1]"] == "0."  # 0 -> 0 (held)
    assert waves["x[2]"] == "01"  # 0 -> 1
    assert waves["x[3]"] == "0."  # 0 -> 0 (held)
    assert set("".join(waves.values())) <= set("01.")
