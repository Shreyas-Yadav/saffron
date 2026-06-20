"""Auto-generate a Verilog testbench for a module.

Stimulus is derived from the module's ports as reported by the yosys JSON netlist
(robust — no Verilog parsing). Two strategies behind one interface:
  - combinational: sweep the inputs (exhaustive when small, else random)
  - sequential:    generate a clock, pulse reset, hold enable, drive data per cycle
`AutoTestbenchGenerator` picks based on whether a clock port is present.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass


class TestbenchError(ValueError):
    """The module can't be auto-stimulated."""


@dataclass
class Port:
    name: str
    direction: str  # "input" | "output" | "inout"
    width: int


def resolve_top(netlist_json: str, hint: str | None = None) -> str:
    """Return the actual top module name in the netlist, preferring `hint`."""
    modules = json.loads(netlist_json).get("modules", {})
    if hint and hint in modules:
        return hint
    return next(iter(modules))


def ports_from_netlist(netlist_json: str, top: str | None) -> list[Port]:
    data = json.loads(netlist_json)
    modules = data.get("modules", {})
    mod = modules.get(top) if top else None
    mod = mod or next(iter(modules.values()))
    ports = []
    for name, p in mod.get("ports", {}).items():
        ports.append(
            Port(name=name, direction=p["direction"], width=len(p["bits"]))
        )
    return ports


# --- port-role detection (name heuristics) --------------------------------------

_CLOCK_NAMES = {"clk", "clock", "clk_in", "clkin", "clock_in"}
_ENABLE_NAMES = {"en", "ena", "enable", "valid", "vld"}


def find_clock(inputs: list[Port]) -> Port | None:
    for p in inputs:
        if p.width == 1 and p.name.lower() in _CLOCK_NAMES:
            return p
    return None


def is_reset(p: Port) -> bool:
    n = p.name.lower()
    return p.width == 1 and (n.startswith("rst") or n.startswith("reset"))


def reset_active_low(p: Port) -> bool:
    # rst_n / rstn / resetn / nreset → active low.
    n = p.name.lower()
    return n.endswith("n") or n.endswith("_n") or n.startswith("n")


def _range(width: int) -> str:
    return "" if width <= 1 else f"[{width - 1}:0] "


class TestbenchGenerator(ABC):
    @abstractmethod
    def generate(self, netlist_json: str, top: str) -> str:
        """Return testbench Verilog that instantiates `top` and dumps a VCD."""


class CombinationalTestbenchGenerator(TestbenchGenerator):
    """Sweeps inputs: exhaustive when the total input width is small, otherwise a
    fixed number of pseudo-random vectors. Dumps `dut.vcd`.
    """

    def __init__(self, max_steps: int = 16):
        self._max_steps = max_steps

    def generate(self, netlist_json: str, top: str) -> str:
        ports = ports_from_netlist(netlist_json, top)
        inputs = [p for p in ports if p.direction == "input"]
        outputs = [p for p in ports if p.direction == "output"]

        if not inputs or not outputs:
            raise TestbenchError("module has no inputs or no outputs to exercise")
        if find_clock(inputs):
            raise TestbenchError(
                "clocked module; use the sequential testbench generator"
            )

        total_bits = sum(p.width for p in inputs)
        # Sweep exhaustively only when it fits the step budget (keeps the waveform
        # on-screen); otherwise drive a fixed number of pseudo-random vectors.
        exhaustive = (1 << total_bits) <= self._max_steps
        steps = (1 << total_bits) if exhaustive else self._max_steps

        decls = "\n".join(f"    reg {_range(p.width)}{p.name};" for p in inputs)
        decls += "\n" + "\n".join(
            f"    wire {_range(p.width)}{p.name};" for p in outputs
        )
        conns = ", ".join(f".{p.name}({p.name})" for p in ports)

        if exhaustive:
            assigns, bit = [], 0
            for p in inputs:
                assigns.append(f"{{{p.name}}} = (i >> {bit});")
                bit += p.width
            body = "\n            ".join(assigns)
        else:
            body = "\n            ".join(f"{p.name} = $random;" for p in inputs)

        stim = f"""        for (i = 0; i < {steps}; i = i + 1) begin
            {body}
            #10;
        end"""

        return f"""// Auto-generated combinational testbench for `{top}`.
`timescale 1ns/1ps
module tb;
{decls}
    integer i;

    {top} dut ({conns});

    initial begin
        $dumpfile("dut.vcd");
        $dumpvars(0, tb);
{stim}
        $finish;
    end
endmodule
"""


class SequentialTestbenchGenerator(TestbenchGenerator):
    """Clocked stimulus: toggle a clock, pulse reset, hold enables high, and drive
    a fresh random value onto each data input every cycle for `cycles` cycles.
    """

    def __init__(self, cycles: int = 8, reset_cycles: int = 2, half_period: int = 5):
        self._cycles = cycles
        self._reset_cycles = reset_cycles
        self._half = half_period

    def generate(self, netlist_json: str, top: str) -> str:
        ports = ports_from_netlist(netlist_json, top)
        inputs = [p for p in ports if p.direction == "input"]
        outputs = [p for p in ports if p.direction == "output"]

        clk = find_clock(inputs)
        if clk is None:
            raise TestbenchError("no clock found; use the combinational generator")

        resets = [p for p in inputs if is_reset(p)]
        reset_names = {p.name for p in resets}
        enables = [
            p
            for p in inputs
            if p.width == 1 and p.name.lower() in _ENABLE_NAMES
        ]
        enable_names = {p.name for p in enables}
        data = [
            p
            for p in inputs
            if p.name != clk.name
            and p.name not in reset_names
            and p.name not in enable_names
        ]

        decls = "\n".join(f"    reg {_range(p.width)}{p.name};" for p in inputs)
        decls += "\n" + "\n".join(
            f"    wire {_range(p.width)}{p.name};" for p in outputs
        )
        conns = ", ".join(f".{p.name}({p.name})" for p in ports)

        def asserted(p: Port) -> int:
            return 0 if reset_active_low(p) else 1

        init = [f"{clk.name} = 0;"]
        init += [f"{p.name} = {asserted(p)};" for p in resets]
        init += [f"{p.name} = 0;" for p in enables]
        init += [f"{p.name} = 0;" for p in data]
        init_block = "\n        ".join(init)

        deassert = [f"{p.name} = {1 - asserted(p)};" for p in resets]
        deassert += [f"{p.name} = 1;" for p in enables]
        deassert_block = "\n        ".join(deassert) or "// no reset/enable"

        drive = "\n            ".join(f"{p.name} = $random;" for p in data)
        drive = drive or "// no data inputs to drive"

        return f"""// Auto-generated sequential testbench for `{top}`.
`timescale 1ns/1ps
module tb;
{decls}
    integer i;

    {top} dut ({conns});

    always #{self._half} {clk.name} = ~{clk.name};

    initial begin
        $dumpfile("dut.vcd");
        $dumpvars(0, tb);
        {init_block}
        repeat ({self._reset_cycles}) @(negedge {clk.name});
        {deassert_block}
        for (i = 0; i < {self._cycles}; i = i + 1) begin
            {drive}
            @(negedge {clk.name});
        end
        $finish;
    end
endmodule
"""


class AutoTestbenchGenerator(TestbenchGenerator):
    """Routes to the sequential generator when the module has a clock, else the
    combinational one. Same interface, so the pipeline is unaware of the choice.
    """

    def __init__(
        self,
        combinational: TestbenchGenerator | None = None,
        sequential: TestbenchGenerator | None = None,
    ):
        self._comb = combinational or CombinationalTestbenchGenerator()
        self._seq = sequential or SequentialTestbenchGenerator()

    def generate(self, netlist_json: str, top: str) -> str:
        inputs = [p for p in ports_from_netlist(netlist_json, top) if p.direction == "input"]
        gen = self._seq if find_clock(inputs) else self._comb
        return gen.generate(netlist_json, top)
