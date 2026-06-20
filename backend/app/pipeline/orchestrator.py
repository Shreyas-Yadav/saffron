"""Generate → synthesize → repair loop.

Depends only on the `LLMProvider` and `SchematicPipeline` abstractions (injected),
so it knows nothing about Gemini or yosys specifically and is fully unit-testable
with a fake LLM. This is the seam the auto-repair UX hangs on: when generated Verilog
fails synthesis, the tool error is fed back to the model and regeneration is retried.
"""
from __future__ import annotations

from ..models import ChatMessage, GenerateOutcome, SimResult
from ..llm.provider import LLMProvider
from .schematic import SchematicPipeline
from .simulation import SimulationPipeline


class GenerateOrchestrator:
    def __init__(
        self,
        llm: LLMProvider,
        schematic: SchematicPipeline,
        simulation: SimulationPipeline,
        max_attempts: int = 3,
    ):
        self._llm = llm
        self._schematic = schematic
        self._simulation = simulation
        self._max_attempts = max_attempts

    def generate(self, messages: list[ChatMessage]) -> GenerateOutcome:
        convo = list(messages)
        gen = self._llm.generate_verilog(convo)
        schem = self._schematic.build(gen.verilog, gen.top_module)
        attempt = 1

        while schem.error and attempt < self._max_attempts:
            # Show the model its own failed code, then the tool error, and retry.
            convo = convo + [ChatMessage(role="assistant", content=gen.verilog)]
            gen = self._llm.generate_verilog(convo, repair_hint=schem.error)
            schem = self._schematic.build(gen.verilog, gen.top_module)
            attempt += 1

        # Simulation is best-effort: a waveform failure never blocks the schematic.
        # The repair loop only targets synthesis (structure), not simulation.
        sim = SimResult()
        if schem.error is None and schem.netlist_json:
            sim = self._simulation.run(gen.verilog, schem.netlist_json, gen.top_module)

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
        )
