"""Composes a Synthesizer + SchematicRenderer (+ safety guard) into one call.

This is the seam the API and the (later) repair-orchestrator depend on. It owns no
tool logic itself — only sequencing and error shaping — so swapping either stage
leaves it untouched.
"""
from __future__ import annotations

from ..models import SchematicResult
from .sandbox import SandboxError, UnsafeVerilogError, VerilogGuard
from .synthesize import SchematicRenderer, Synthesizer


class SchematicPipeline:
    def __init__(
        self,
        synthesizer: Synthesizer,
        renderer: SchematicRenderer,
        guard: VerilogGuard,
    ):
        self._synth = synthesizer
        self._renderer = renderer
        self._guard = guard

    def build(self, verilog: str, top: str | None = None) -> SchematicResult:
        try:
            self._guard.check(verilog)
            netlist = self._synth.to_netlist(verilog, top)
            svg = self._renderer.render(netlist)
        except (UnsafeVerilogError, SandboxError) as exc:
            return SchematicResult(error=str(exc))
        return SchematicResult(
            svg=svg, renderer=self._renderer.name, netlist_json=netlist
        )
