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
    gemini_api_key: str | None
    gemini_model: str


def get_settings() -> Settings:
    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    )
