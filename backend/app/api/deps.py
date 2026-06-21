"""Composition root: the ONE place that constructs concrete implementations and
wires them together. Routes ask for interfaces via FastAPI's `Depends`, so swapping
an implementation (or injecting a mock in tests) happens here and nowhere else.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from ..config import get_settings
from ..llm.provider import GeminiProvider, LLMProvider
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
    settings = get_settings()
    return GeminiProvider(settings.gemini_api_key, settings.gemini_model)


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
