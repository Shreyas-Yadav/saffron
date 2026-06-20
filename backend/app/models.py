"""Typed contracts shared between units. Pydantic models are the only data that
crosses unit boundaries, so each unit can be understood and tested in isolation.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class SchematicResult(BaseModel):
    """Output of the synthesis + render pipeline."""

    svg: str | None = None
    renderer: str | None = None  # which SchematicRenderer produced the svg
    netlist_json: str | None = None  # yosys JSON (handy for debugging/waveform)
    error: str | None = None
    logs: str = ""


class SynthesizeRequest(BaseModel):
    """Step 1 endpoint: synthesize a known Verilog string into a schematic."""

    verilog: str = Field(..., description="Synthesizable Verilog source")
    top: str | None = Field(None, description="Top module name; auto-detected if omitted")


class GenResult(BaseModel):
    """What an LLMProvider returns: a synthesizable module + metadata."""

    top_module: str
    verilog: str
    explanation: str


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    """Full conversation so far; the latest user turn drives generation.

    Sending history (not just the last turn) is what makes iteration work in Step 4
    — 'now make it 4-bit' refines the prior module.
    """

    messages: list[ChatMessage]


class GenerateOutcome(BaseModel):
    """Result of generate→synthesize→repair: code AND schematic in one shot.

    `attempts` is how many generations it took to compile (1 = first try). `error` is
    non-null only if it still failed after the last attempt.
    """

    top_module: str
    verilog: str
    explanation: str
    svg: str | None = None
    renderer: str | None = None
    attempts: int = 1
    error: str | None = None
