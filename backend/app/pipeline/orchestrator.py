"""Generate → synthesize → repair loop.

Depends only on the `LLMProvider` and `SchematicPipeline` abstractions (injected),
so it knows nothing about Gemini or yosys specifically and is fully unit-testable
with a fake LLM. This is the seam the auto-repair UX hangs on: when generated Verilog
fails synthesis, the tool error is fed back to the model and regeneration is retried.
"""
from __future__ import annotations

from ..models import (
    ChatMessage,
    FormalResult,
    GenerateOutcome,
    SimResult,
    TimingResult,
)
from ..llm.provider import LLMProvider
from .sanitize import sanitize_verilog
from .schematic import SchematicPipeline
from .simulation import SimulationPipeline
from .timing_pipeline import TimingPipeline
from .verification import FormalPipeline


class GenerateOrchestrator:
    def __init__(
        self,
        llm: LLMProvider,
        schematic: SchematicPipeline,
        simulation: SimulationPipeline,
        formal: FormalPipeline,
        timing: TimingPipeline,
        max_attempts: int = 3,
    ):
        self._llm = llm
        self._schematic = schematic
        self._simulation = simulation
        self._formal = formal
        self._timing = timing
        self._max_attempts = max_attempts

    def generate(self, messages: list[ChatMessage]) -> GenerateOutcome:
        convo = list(messages)
        gen = self._llm.generate_verilog(convo)
        gen.verilog = sanitize_verilog(gen.verilog)
        schem = self._schematic.build(gen.verilog, gen.top_module)
        attempt = 1

        while schem.error and attempt < self._max_attempts:
            # Show the model its own failed code, then the tool error, and retry.
            convo = convo + [ChatMessage(role="assistant", content=gen.verilog)]
            gen = self._llm.generate_verilog(convo, repair_hint=schem.error)
            gen.verilog = sanitize_verilog(gen.verilog)
            schem = self._schematic.build(gen.verilog, gen.top_module)
            attempt += 1

        # Simulation, formal, and timing are best-effort: none blocks the schematic,
        # and the repair loop only targets synthesis (structure), not these analyses.
        sim = SimResult()
        formal: FormalResult | None = None
        timing: TimingResult | None = None
        if schem.error is None and schem.netlist_json:
            sim = self._simulation.run(gen.verilog, schem.netlist_json, gen.top_module)
            formal = self._formal.run(
                gen.verilog, schem.netlist_json, gen.top_module, gen.properties
            )
            timing = self._timing.run(gen.verilog, schem.netlist_json, gen.top_module)

        return GenerateOutcome(
            top_module=gen.top_module,
            verilog=gen.verilog,
            explanation=gen.explanation,
            svg=schem.svg,
            renderer=schem.renderer,
            attempts=attempt,
            error=schem.error,
            wavedrom=sim.wavedrom,
            sim_error=sim.error,
            formal=formal,
            timing=timing,
        )
