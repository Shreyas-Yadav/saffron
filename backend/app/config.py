"""Runtime configuration, read once from the environment (.env supported).

Keeping config in one typed object means no module reaches into os.environ directly,
and the LLM model/key can change without editing provider code.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()  # load backend/.env if present; real env vars win


@dataclass(frozen=True)
class Settings:
    # Which LLM backend to use: "gemini" (Google AI Studio), "anthropic" (first-party
    # Claude API), or "vertex" (Claude on Google Cloud Vertex AI). All interchangeable
    # behind the LLMProvider seam.
    llm_provider: str
    gemini_api_key: str | None
    gemini_model: str
    # Claude on the first-party Anthropic API: just an API key, no GCP.
    anthropic_api_key: str | None
    anthropic_model: str
    # Claude-on-Vertex: GCP project + region (auth is GCP ADC, no API key). `region`
    # may be "global" (recommended), a multi-region ("us"/"eu"), or a specific region.
    vertex_project_id: str | None
    vertex_region: str
    vertex_model: str


def get_settings() -> Settings:
    return Settings(
        llm_provider=os.getenv("LLM_PROVIDER", "gemini").lower(),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8"),
        vertex_project_id=os.getenv("VERTEX_PROJECT_ID"),
        vertex_region=os.getenv("VERTEX_REGION", "global"),
        vertex_model=os.getenv("VERTEX_MODEL", "claude-opus-4-8"),
    )
