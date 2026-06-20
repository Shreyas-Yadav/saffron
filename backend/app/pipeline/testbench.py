"""Auto-generate a Verilog testbench for a module.

Stimulus is derived from the module's ports as reported by the yosys JSON netlist
(robust — no Verilog parsing). Combinational-first: drive the inputs through a set
of vectors and dump every signal to VCD. Sequential modules (with a clock) are out
of scope and reported as such, so the schematic still renders.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass


class TestbenchError(ValueError):
    """The module can't be auto-stimulated (e.g. needs a clock)."""


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


# Heuristic clock/reset names we can't meaningfully sweep combinationally.
_CLOCKISH = {"clk", "clock", "rst", "reset", "rstn", "resetn", "clk_in"}


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
        clockish = [p for p in inputs if p.name.lower() in _CLOCKISH]
        if clockish:
            raise TestbenchError(
                "sequential module (clock/reset present); waveform not auto-generated"
            )

        total_bits = sum(p.width for p in inputs)
        # Sweep exhaustively only when it fits the step budget (keeps the waveform
        # on-screen); otherwise drive a fixed number of pseudo-random vectors.
        exhaustive = (1 << total_bits) <= self._max_steps
        steps = (1 << total_bits) if exhaustive else self._max_steps

        decls = "\n".join(
            f"    reg {self._range(p.width)}{p.name};" for p in inputs
        )
        decls += "\n" + "\n".join(
            f"    wire {self._range(p.width)}{p.name};" for p in outputs
        )
        conns = ", ".join(f".{p.name}({p.name})" for p in ports)

        # Drive each input from a slice of the loop counter (exhaustive) or $random.
        if exhaustive:
            assigns, bit = [], 0
            for p in inputs:
                assigns.append(f"{{{p.name}}} = (i >> {bit});")
                bit += p.width
            assign_block = "\n            ".join(assigns)
            stim = f"""        for (i = 0; i < {steps}; i = i + 1) begin
            {assign_block}
            #10;
        end"""
        else:
            rnd = "\n            ".join(
                f"{p.name} = $random;" for p in inputs
            )
            stim = f"""        for (i = 0; i < {steps}; i = i + 1) begin
            {rnd}
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

    @staticmethod
    def _range(width: int) -> str:
        return "" if width <= 1 else f"[{width - 1}:0] "
