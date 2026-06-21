"""Composes guard + formal verifier into one call.

Mirrors `SimulationPipeline`: it owns sequencing and error shaping only — derive the
top module and its ports from the netlist, hand them to the injected `FormalVerifier`,
and turn guard/parse failures into a `FormalResult(status="error")` so a formal
hiccup never blocks the schematic.
"""
from __future__ import annotations

from ..models import FormalResult
from .formal import FormalVerifier
from .sandbox import SandboxError, UnsafeVerilogError, VerilogGuard
from .testbench import ports_from_netlist, resolve_top


class FormalPipeline:
    def __init__(self, verifier: FormalVerifier, guard: VerilogGuard):
        self._verifier = verifier
        self._guard = guard

    def run(
        self,
        verilog: str,
        netlist_json: str,
        top: str | None,
        properties: list[str] | None = None,
    ) -> FormalResult:
        try:
            self._guard.check(verilog)
            top = resolve_top(netlist_json, top)
            ports = ports_from_netlist(netlist_json, top)
            return self._verifier.verify(verilog, properties or [], top, ports)
        except (UnsafeVerilogError, SandboxError) as exc:
            return FormalResult(status="error", logs=str(exc))
