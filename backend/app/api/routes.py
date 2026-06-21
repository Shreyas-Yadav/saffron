"""HTTP endpoints. Thin: validate input, delegate to an injected interface, return
the typed contract. No tool or orchestration logic lives here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..llm.provider import LLMProvider
from ..models import (
    ChatRequest,
    ExplainStepRequest,
    GenerateOutcome,
    SchematicResult,
    StepExplanation,
    SynthesizeRequest,
)
from ..pipeline.agentic import AgenticOrchestrator
from ..pipeline.orchestrator import GenerateOrchestrator
from ..pipeline.sanitize import sanitize_verilog_with_report
from ..pipeline.schematic import SchematicPipeline
from ..pipeline.simulation import SimulationPipeline
from ..pipeline.steps import (
    formal_step,
    sanitize_step,
    schematic_step,
    simulation_step,
    skipped_step,
    timing_step,
)
from ..pipeline.timing_pipeline import TimingPipeline
from ..pipeline.verification import FormalPipeline
from .deps import (
    get_agentic_orchestrator,
    get_formal_pipeline,
    get_llm_provider,
    get_orchestrator,
    get_schematic_pipeline,
    get_simulation_pipeline,
    get_timing_pipeline,
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


@router.post("/chat-agentic", response_model=GenerateOutcome)
def chat_agentic(
    req: ChatRequest,
    orchestrator: AgenticOrchestrator = Depends(get_agentic_orchestrator),
) -> GenerateOutcome:
    """Agentic counterpart to /chat: Claude is given the pipeline as tools and drives
    the generate/synthesize/repair/verify loop itself, then submits the module. Returns
    the same GenerateOutcome shape as /chat. Requires a Claude backend; AgenticError and
    LLMError (e.g. missing key, turn limit) surface as 502 via the app exception handler."""
    return orchestrator.generate(req.messages)


@router.post("/synthesize", response_model=SchematicResult)
def synthesize(
    req: SynthesizeRequest,
    pipeline: SchematicPipeline = Depends(get_schematic_pipeline),
    simulation: SimulationPipeline = Depends(get_simulation_pipeline),
    formal: FormalPipeline = Depends(get_formal_pipeline),
    timing: TimingPipeline = Depends(get_timing_pipeline),
) -> SchematicResult:
    """Synthesize hand-written/edited Verilog into a schematic, plus a best-effort
    waveform, formal check, and timing analysis. Edited Verilog carries no LLM intent
    properties, so formal here runs the invariants (no loops / no latches) only."""
    # Clean copy-paste artifacts (non-breaking spaces, smart quotes, ...) before any
    # tool sees the code, then run every stage on the same cleaned source.
    verilog, report = sanitize_verilog_with_report(req.verilog)
    steps = [sanitize_step(report)]
    result = pipeline.build(verilog, req.top)
    steps.append(schematic_step(result.error))
    if result.error is None and result.netlist_json:
        sim = simulation.run(verilog, result.netlist_json, req.top)
        result.wavedrom = sim.wavedrom
        result.sim_error = sim.error
        result.testbench = sim.testbench
        result.formal = formal.run(verilog, result.netlist_json, req.top)
        result.timing = timing.run(verilog, result.netlist_json, req.top)
        steps.extend(
            [
                simulation_step(sim),
                formal_step(result.formal),
                timing_step(result.timing),
            ]
        )
    else:
        steps.extend(
            [
                skipped_step("simulate", "Simulated example inputs", "synthesis failed"),
                skipped_step("formal", "Checked formal rules", "synthesis failed"),
                skipped_step("timing", "Estimated speed and area", "synthesis failed"),
            ]
        )
    result.steps = steps
    return result


@router.post("/explain-step", response_model=StepExplanation)
def explain_step(
    req: ExplainStepRequest,
    llm: LLMProvider = Depends(get_llm_provider),
) -> StepExplanation:
    """On-demand, plain-language deepening of one pipeline step for a student, tailored
    to the current circuit. Additive: the frontend already shows the deterministic
    template. LLMError (e.g. missing key) is surfaced as 502 by the app handler."""
    return llm.explain_step(req.verilog, req.top_module, req.step)
