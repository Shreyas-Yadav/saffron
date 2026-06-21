"""Composes guard + testbench generator + simulator + converter into one call.

This is also where `VerilogGuard` gates the *simulate* path — `vvp` actually executes
the module, so the system-task guard matters more here than at synthesis time.
"""
from __future__ import annotations

from ..models import SimResult
from .sandbox import SandboxError, UnsafeVerilogError, VerilogGuard
from .simulate import Simulator, vcd_to_wavedrom
from .testbench import (
    AutoTestbenchGenerator,
    TestbenchError,
    TestbenchGenerator,
    ports_from_netlist,
    resolve_top,
)


class SimulationPipeline:
    def __init__(
        self,
        simulator: Simulator,
        guard: VerilogGuard,
        testbench: TestbenchGenerator | None = None,
    ):
        self._simulator = simulator
        self._guard = guard
        self._testbench = testbench or AutoTestbenchGenerator()

    def run(self, verilog: str, netlist_json: str, top: str | None) -> SimResult:
        # Guard + testbench generation can fail before there's anything to show.
        try:
            self._guard.check(verilog)  # vvp executes — guard before running
            top = resolve_top(netlist_json, top)
            tb = self._testbench.generate(netlist_json, top)
        except (UnsafeVerilogError, TestbenchError) as exc:
            return SimResult(error=str(exc))
        # From here the testbench exists, so surface it even if simulation fails.
        try:
            vcd = self._simulator.run(verilog, tb, top)
            # Show inputs first, then outputs, in declaration order.
            ports = ports_from_netlist(netlist_json, top)
            names = [p.name for p in ports if p.direction == "input"] + [
                p.name for p in ports if p.direction == "output"
            ]
            return SimResult(wavedrom=vcd_to_wavedrom(vcd, names), testbench=tb)
        except SandboxError as exc:
            return SimResult(error=str(exc), testbench=tb)
