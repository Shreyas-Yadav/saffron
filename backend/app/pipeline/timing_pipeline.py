"""Composes guard + timing analyzer into one call.

Mirrors `FormalPipeline`: derive the top module and detect a clock from the netlist
ports (reusing `find_clock`, so clock detection lives in exactly one place), hand
that to the injected `TimingAnalyzer`, and shape guard failures into a
`TimingResult(error=...)` so timing never blocks the schematic.
"""
from __future__ import annotations

from ..models import TimingResult
from .sandbox import SandboxError, UnsafeVerilogError, VerilogGuard
from .testbench import find_clock, ports_from_netlist, resolve_top
from .timing import TimingAnalyzer


class TimingPipeline:
    def __init__(self, analyzer: TimingAnalyzer, guard: VerilogGuard):
        self._analyzer = analyzer
        self._guard = guard

    def run(self, verilog: str, netlist_json: str, top: str | None) -> TimingResult:
        try:
            self._guard.check(verilog)
            top = resolve_top(netlist_json, top)
            inputs = [p for p in ports_from_netlist(netlist_json, top) if p.direction == "input"]
            clock = find_clock(inputs)
            return self._analyzer.analyze(verilog, top, clock)
        except (UnsafeVerilogError, SandboxError) as exc:
            return TimingResult(source="yosys-estimate", error=str(exc))
