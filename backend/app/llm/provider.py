"""LLM-backed Verilog generation, behind the `LLMProvider` interface.

Only `GeminiProvider` knows about the google-genai SDK. Swapping to another model =
a new class implementing `LLMProvider` + one wiring line in deps.py; nothing else in
the app references a provider directly.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel

from ..models import ChatMessage, GenResult


class LLMError(RuntimeError):
    """Provider misconfigured or the upstream call failed."""


class LLMProvider(ABC):
    @abstractmethod
    def generate_verilog(
        self, messages: list[ChatMessage], repair_hint: str | None = None
    ) -> GenResult:
        """Produce a synthesizable module from the conversation so far.

        `repair_hint` carries tool errors back to the model (used by the Step-3
        repair loop); providers must regenerate fixing those errors when present.
        """


_SYSTEM = """You are an expert Verilog designer. Given a natural-language request \
(and any prior conversation), output ONE synthesizable Verilog module.

Rules:
- Synthesizable RTL only. No testbenches, no `$display`/`$system`/`$fopen`/`$readmem`.
- Prefer clean combinational logic for the demo unless sequential state is required.
- `top_module` MUST exactly match the module name you declare.
- `verilog` is the complete module source, nothing else.
- `explanation` is one or two sentences for a human.
"""


class _Schema(BaseModel):
    """Structured-output contract handed to Gemini (subset of GenResult)."""

    top_module: str
    verilog: str
    explanation: str


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str | None, model: str):
        if not api_key:
            raise LLMError(
                "GEMINI_API_KEY is not set. Add it to backend/.env (see .env.example)."
            )
        # Imported lazily so the app boots even if the SDK/key is absent.
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model

    def generate_verilog(
        self, messages: list[ChatMessage], repair_hint: str | None = None
    ) -> GenResult:
        from google.genai import types

        contents = [
            types.Content(
                role="model" if m.role == "assistant" else "user",
                parts=[types.Part(text=m.content)],
            )
            for m in messages
        ]
        if repair_hint:
            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            text=(
                                "The previous module failed the toolchain. Fix it and "
                                f"return the corrected module.\n\nErrors:\n{repair_hint}"
                            )
                        )
                    ],
                )
            )
        try:
            resp = self._client.models.generate_content(
                model=self._model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=_SYSTEM,
                    response_mime_type="application/json",
                    response_schema=_Schema,
                ),
            )
        except Exception as exc:  # SDK raises a variety of error types
            raise LLMError(f"Gemini request failed: {exc}") from exc

        parsed = resp.parsed
        if not isinstance(parsed, _Schema):
            raise LLMError("Gemini returned no structured content")
        return GenResult(
            top_module=parsed.top_module,
            verilog=parsed.verilog,
            explanation=parsed.explanation,
        )
