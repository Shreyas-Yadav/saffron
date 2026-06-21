"""Composition root: the ONE place that constructs concrete implementations and
wires them together. Routes ask for interfaces via FastAPI's `Depends`, so swapping
an implementation (or injecting a mock in tests) happens here and nowhere else.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from ..config import get_settings
from ..llm.provider import (
    AnthropicProvider,
    AnthropicVertexProvider,
    GeminiProvider,
    LLMError,
    LLMProvider,
)
from ..pipeline.agentic import AgenticOrchestrator
from ..pipeline.formal import YosysFormalVerifier
from ..pipeline.orchestrator import GenerateOrchestrator
from ..pipeline.sandbox import LocalSandbox, Sandbox, VerilogGuard
from ..pipeline.schematic import SchematicPipeline
from ..pipeline.simulate import IcarusSimulator
from ..pipeline.simulation import SimulationPipeline
from ..pipeline.synthesize import NetlistSvgRenderer, YosysSynthesizer
from ..pipeline.timing import OpenStaTimingAnalyzer
from ..pipeline.timing_pipeline import TimingPipeline
from ..pipeline.verification import FormalPipeline

_LIBERTY_GZ = (
    Path(__file__).parents[2] / "fixtures" / "liberty" / "nangate45_typ.lib.gz"
)


@lru_cache
def get_sandbox() -> Sandbox:
    return LocalSandbox()


@lru_cache
def get_llm_provider() -> LLMProvider:
    # The one place that picks an LLM backend. Swap via LLM_PROVIDER in .env; nothing
    # else in the app references a concrete provider.
    settings = get_settings()
    if settings.llm_provider == "anthropic":
        return AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model)
    if settings.llm_provider == "vertex":
        return AnthropicVertexProvider(
            settings.vertex_project_id, settings.vertex_region, settings.vertex_model
        )
    if settings.llm_provider == "gemini":
        return GeminiProvider(settings.gemini_api_key, settings.gemini_model)
    raise LLMError(
        f"Unknown LLM_PROVIDER '{settings.llm_provider}'. "
        "Use 'gemini', 'anthropic', or 'vertex'."
    )


@lru_cache
def get_schematic_pipeline() -> SchematicPipeline:
    sandbox = get_sandbox()
    return SchematicPipeline(
        synthesizer=YosysSynthesizer(sandbox),
        renderer=NetlistSvgRenderer(sandbox),
        guard=VerilogGuard(),
    )


@lru_cache
def get_simulation_pipeline() -> SimulationPipeline:
    # Default testbench generator is AutoTestbenchGenerator (combinational or
    # sequential based on the module's ports).
    return SimulationPipeline(
        simulator=IcarusSimulator(get_sandbox()),
        guard=VerilogGuard(),
    )


@lru_cache
def get_formal_pipeline() -> FormalPipeline:
    return FormalPipeline(
        verifier=YosysFormalVerifier(get_sandbox()),
        guard=VerilogGuard(),
    )


@lru_cache
def get_timing_pipeline() -> TimingPipeline:
    # OpenSTA runs in a Docker container; the analyzer degrades to a yosys area/cell
    # estimate when Docker/the image is unavailable, so this is always constructible.
    return TimingPipeline(
        analyzer=OpenStaTimingAnalyzer(get_sandbox(), liberty_gz=_LIBERTY_GZ),
        guard=VerilogGuard(),
    )


def get_orchestrator() -> GenerateOrchestrator:
    # Not cached: depends on the LLM provider, which validates the key at build time;
    # rebuilding per request keeps a missing/rotated key from being cached as a failure.
    return GenerateOrchestrator(
        llm=get_llm_provider(),
        schematic=get_schematic_pipeline(),
        simulation=get_simulation_pipeline(),
        formal=get_formal_pipeline(),
        timing=get_timing_pipeline(),
    )


def _build_claude_client(settings) -> tuple[object, str, str]:
    """Construct a raw Claude client for the agentic tool-use loop, plus its model and
    a human label. Tool use is Claude-specific, so agentic mode requires a Claude
    backend; Gemini is rejected with a clear message."""
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise LLMError(
                "ANTHROPIC_API_KEY is not set. Add it to backend/.env (see .env.example)."
            )
        from anthropic import Anthropic

        return Anthropic(api_key=settings.anthropic_api_key), settings.anthropic_model, "Claude (Anthropic API)"
    if settings.llm_provider == "vertex":
        if not settings.vertex_project_id:
            raise LLMError(
                "VERTEX_PROJECT_ID is not set. Add it to backend/.env (see .env.example) "
                "and run `gcloud auth application-default login`."
            )
        from anthropic import AnthropicVertex

        client = AnthropicVertex(
            project_id=settings.vertex_project_id, region=settings.vertex_region
        )
        return client, settings.vertex_model, "Claude (Vertex)"
    raise LLMError(
        f"Agentic mode requires a Claude backend, but LLM_PROVIDER is "
        f"'{settings.llm_provider}'. Set LLM_PROVIDER to 'anthropic' or 'vertex'."
    )


def get_agentic_orchestrator() -> AgenticOrchestrator:
    # Not cached, for the same key-validation reason as get_orchestrator: the client is
    # built per request so a missing/rotated key isn't cached as a permanent failure.
    settings = get_settings()
    client, model, label = _build_claude_client(settings)
    return AgenticOrchestrator(
        client=client,
        model=model,
        schematic=get_schematic_pipeline(),
        simulation=get_simulation_pipeline(),
        formal=get_formal_pipeline(),
        timing=get_timing_pipeline(),
        max_turns=settings.agentic_max_turns,
        label=label,
    )
