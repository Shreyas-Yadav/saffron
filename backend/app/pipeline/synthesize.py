"""Synthesis + schematic rendering.

Two small interfaces, deliberately separate (interface segregation):
  - `Synthesizer`:       Verilog  -> yosys JSON netlist
  - `SchematicRenderer`: netlist  -> SVG

They are composed by `SchematicPipeline` but never reference each other, so a new
renderer (e.g. a Graphviz fallback) drops in without touching synthesis, and vice
versa.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .sandbox import Sandbox, SandboxError


class Synthesizer(ABC):
    @abstractmethod
    def to_netlist(self, verilog: str, top: str | None = None) -> str:
        """Return a JSON netlist string for the given Verilog."""


class SchematicRenderer(ABC):
    name: str

    @abstractmethod
    def render(self, netlist_json: str) -> str:
        """Return an SVG string for the given JSON netlist."""


class YosysSynthesizer(Synthesizer):
    """Uses yosys' `prep` flow (NOT full `synth`) so netlistsvg gets a readable
    gate-level graph rather than abstract RTL blocks or a tech-cell wall.
    """

    def __init__(self, sandbox: Sandbox):
        self._sandbox = sandbox

    def to_netlist(self, verilog: str, top: str | None = None) -> str:
        prep = f"prep -top {top}" if top else "hierarchy -auto-top; prep"
        # `-sv`: accept the synthesizable SystemVerilog subset (logic, always_comb/_ff,
        # inline `for (int i ...)`), which LLMs emit by default. Mirrors formal.py's
        # reader so the same source parses across synthesis, simulation, and formal.
        script = f"read_verilog -sv design.v; {prep}; write_json netlist.json"
        with self._sandbox.workspace() as ws:
            ws.write("design.v", verilog)
            result = ws.run(["yosys", "-q", "-p", script])
            if not result.ok:
                raise SandboxError(result.stderr.strip() or "yosys synthesis failed")
            return ws.read("netlist.json")


class NetlistSvgRenderer(SchematicRenderer):
    name = "netlistsvg"

    def __init__(self, sandbox: Sandbox):
        self._sandbox = sandbox

    def render(self, netlist_json: str) -> str:
        with self._sandbox.workspace() as ws:
            ws.write("netlist.json", netlist_json)
            result = ws.run(["netlistsvg", "netlist.json", "-o", "out.svg"])
            if not result.ok:
                raise SandboxError(result.stderr.strip() or "netlistsvg failed")
            return ws.read("out.svg")
