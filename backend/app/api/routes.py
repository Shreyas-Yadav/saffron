"""HTTP endpoints. Thin: validate input, delegate to an injected interface, return
the typed contract. No tool or orchestration logic lives here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..models import ChatRequest, GenerateOutcome, SchematicResult, SynthesizeRequest
from ..pipeline.orchestrator import GenerateOrchestrator
from ..pipeline.schematic import SchematicPipeline
from ..pipeline.simulation import SimulationPipeline
from .deps import (
    get_orchestrator,
    get_schematic_pipeline,
    get_simulation_pipeline,
)

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/chat", response_model=GenerateOutcome)
def chat(
    req: ChatRequest,
    orchestrator: GenerateOrchestrator = Depends(get_orchestrator),
) -> GenerateOutcome:
    """Generate a module from the conversation, synthesize it, and auto-repair on
    tool errors (up to N attempts). Returns code AND schematic together. LLMError
    (e.g. missing key) is surfaced as 502 by the app exception handler."""
    return orchestrator.generate(req.messages)


@router.post("/synthesize", response_model=SchematicResult)
def synthesize(
    req: SynthesizeRequest,
    pipeline: SchematicPipeline = Depends(get_schematic_pipeline),
    simulation: SimulationPipeline = Depends(get_simulation_pipeline),
) -> SchematicResult:
    """Synthesize hand-written/edited Verilog into a schematic, plus a best-effort
    waveform (combinational modules)."""
    result = pipeline.build(req.verilog, req.top)
    if result.error is None and result.netlist_json:
        sim = simulation.run(req.verilog, result.netlist_json, req.top)
        result.wavedrom = sim.wavedrom
        result.sim_error = sim.error
    return result
