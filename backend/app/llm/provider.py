"""LLM-backed Verilog generation, behind the `LLMProvider` interface.

Only `GeminiProvider` knows about the google-genai SDK. Swapping to another model =
a new class implementing `LLMProvider` + one wiring line in deps.py; nothing else in
the app references a provider directly.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel

from ..models import ChatMessage, GenResult, ProcessStep, StepExplanation


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

    @abstractmethod
    def explain_step(
        self, verilog: str, top_module: str | None, step: ProcessStep
    ) -> StepExplanation:
        """Deepen one pipeline step into plain-language teaching for a student.

        On-demand and additive: the caller already shows the deterministic template;
        this returns a richer, circuit-specific explanation of what happened in that
        step (and, for errors, how to fix it).
        """


_SYSTEM = """You are an expert Verilog designer. Given a natural-language request \
(and any prior conversation), output ONE synthesizable Verilog module.

Rules:
- Synthesizable RTL only. No testbenches, no `$display`/`$system`/`$fopen`/`$readmem`.
- The toolchain accepts the synthesizable SystemVerilog subset (yosys `read_verilog -sv`,
  iverilog `-g2012`): `logic`, `always_comb`/`always_ff`, and `for (int i = ...)` loops
  are fine. Avoid non-synthesizable constructs (delays, `initial`, dynamic arrays).
- Prefer clean combinational logic for the demo unless sequential state is required.
- `top_module` MUST exactly match the module name you declare.
- `verilog` is the complete module source, nothing else.
- `explanation` is one or two sentences for a human.
- `properties`: a short list of formal assertions describing the intended behavior,
  to be proven by a SAT solver. Each is a SINGLE boolean Verilog expression over the
  module's OWN ports only (no `assert`, no `;`), true for every input — e.g. for an
  adder `"{cout, sum} == a + b + cin"`, for a 2:1 mux `"y == (sel ? b : a)"`. Only
  emit properties for COMBINATIONAL modules; for clocked modules return an empty list.
  If you can't state a sound property, return an empty list rather than a weak one.
"""


_EXPLAIN_SYSTEM = """You are a friendly digital-design tutor. A student is learning \
how a natural-language circuit request becomes verified hardware, one pipeline step at \
a time. Explain ONE step to them in simple, encouraging language.

Rules:
- Plain language for a beginner. Explain any term you must use; avoid unexplained jargon.
- Be specific to THIS circuit: refer to the actual module, its ports, and signals from
  the provided Verilog. Don't give a generic textbook definition.
- If the step is an error or warning, focus on what went wrong and the concrete steps
  the student can take to fix it.
- If the step is a result (simulation/formal/timing), explain what the result means for
  this design and what the student should take away from it.
- `headline` is ONE short, plain sentence capturing the takeaway.
- `points` is 2-4 short bullets (each one sentence). For errors, make them actionable
  fix steps. Don't repeat the headline.
- Stay accurate. If the provided evidence is thin, keep it general rather than inventing
  details that aren't supported by the Verilog or tool output.
"""


class _Schema(BaseModel):
    """Structured-output contract handed to Gemini (subset of GenResult)."""

    top_module: str
    verilog: str
    explanation: str
    properties: list[str] = []


class _ExplainSchema(BaseModel):
    """Structured-output contract for explain_step (matches StepExplanation)."""

    headline: str
    points: list[str] = []


def _repair_message(repair_hint: str) -> str:
    """The feedback turn sent to any provider when synthesis rejects a module.

    Provider-agnostic so Gemini and Claude give the model identical repair guidance.
    """
    return (
        "Your previous module (the last assistant message) failed the toolchain. Fix "
        "ONLY what the error reports and return the complete corrected module.\n"
        "- Keep the same module name and port list unless the error is about them.\n"
        "- Read the error carefully and address its exact cause; do not reintroduce "
        "earlier mistakes.\n"
        "- The synthesizable SystemVerilog subset is allowed (logic, always_comb/"
        "always_ff, for (int i ...)); prefer fixing the real bug over downgrading "
        "syntax.\n\n"
        f"Errors:\n{repair_hint}"
    )


def _explain_prompt(verilog: str, top_module: str | None, step: ProcessStep) -> str:
    """The user turn for explain_step — provider-agnostic so both backends match."""
    module = top_module or "(unknown)"
    evidence = step.technical or "(no raw tool output for this step)"
    return (
        f"Top module: {module}\n\n"
        f"Verilog:\n{verilog}\n\n"
        f"Pipeline step to explain:\n"
        f"- title: {step.title}\n"
        f"- status: {step.status}\n"
        f"- current short summary: {step.summary}\n"
        f"- raw tool output / evidence:\n{evidence}\n\n"
        "Explain this step to the student."
    )


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
                    parts=[types.Part(text=_repair_message(repair_hint))],
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
            properties=parsed.properties,
        )

    def explain_step(
        self, verilog: str, top_module: str | None, step: ProcessStep
    ) -> StepExplanation:
        from google.genai import types

        prompt = _explain_prompt(verilog, top_module, step)
        try:
            resp = self._client.models.generate_content(
                model=self._model,
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                config=types.GenerateContentConfig(
                    system_instruction=_EXPLAIN_SYSTEM,
                    response_mime_type="application/json",
                    response_schema=_ExplainSchema,
                ),
            )
        except Exception as exc:  # SDK raises a variety of error types
            raise LLMError(f"Gemini request failed: {exc}") from exc

        parsed = resp.parsed
        if not isinstance(parsed, _ExplainSchema):
            raise LLMError("Gemini returned no structured content")
        return StepExplanation(headline=parsed.headline, points=parsed.points)


class _ClaudeProvider(LLMProvider):
    """Shared Claude request logic (same structured-output contract as Gemini).

    Subclasses only build `self._client` (first-party API vs Vertex) and set
    `self._model` + `self._label`; the request/parse path is identical because both
    clients expose the same `messages.parse` surface.
    """

    _client: object
    _model: str
    _label: str = "Claude"

    def _to_messages(self, messages: list[ChatMessage]) -> list[dict]:
        return [
            {"role": "assistant" if m.role == "assistant" else "user", "content": m.content}
            for m in messages
        ]

    def generate_verilog(
        self, messages: list[ChatMessage], repair_hint: str | None = None
    ) -> GenResult:
        convo = self._to_messages(messages)
        if repair_hint:
            convo.append({"role": "user", "content": _repair_message(repair_hint)})
        try:
            resp = self._client.messages.parse(
                model=self._model,
                max_tokens=16000,
                system=_SYSTEM,
                messages=convo,
                output_format=_Schema,
            )
        except Exception as exc:  # SDK raises a variety of error types
            raise LLMError(f"{self._label} request failed: {exc}") from exc

        parsed = resp.parsed_output
        if not isinstance(parsed, _Schema):
            raise LLMError("Claude returned no structured content")
        return GenResult(
            top_module=parsed.top_module,
            verilog=parsed.verilog,
            explanation=parsed.explanation,
            properties=parsed.properties,
        )

    def explain_step(
        self, verilog: str, top_module: str | None, step: ProcessStep
    ) -> StepExplanation:
        try:
            resp = self._client.messages.parse(
                model=self._model,
                max_tokens=2000,
                system=_EXPLAIN_SYSTEM,
                messages=[{"role": "user", "content": _explain_prompt(verilog, top_module, step)}],
                output_format=_ExplainSchema,
            )
        except Exception as exc:  # SDK raises a variety of error types
            raise LLMError(f"{self._label} request failed: {exc}") from exc

        parsed = resp.parsed_output
        if not isinstance(parsed, _ExplainSchema):
            raise LLMError("Claude returned no structured content")
        return StepExplanation(headline=parsed.headline, points=parsed.points)


class AnthropicProvider(_ClaudeProvider):
    """Claude on the first-party Anthropic API (api.anthropic.com).

    Auth is a plain Anthropic API key — no GCP project, billing, or Model Garden.
    Model IDs are the bare first-party strings (e.g. `claude-opus-4-8`).
    """

    _label = "Claude (Anthropic API)"

    def __init__(self, api_key: str | None, model: str):
        if not api_key:
            raise LLMError(
                "ANTHROPIC_API_KEY is not set. Add it to backend/.env (see .env.example)."
            )
        # Imported lazily so the app boots even if the SDK/key is absent.
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key)
        self._model = model


class AnthropicVertexProvider(_ClaudeProvider):
    """Claude on Google Cloud Vertex AI.

    Auth is GCP Application Default Credentials (`gcloud auth application-default
    login`), not an Anthropic API key. Model IDs are the bare first-party strings
    (e.g. `claude-opus-4-8`); the model must be enabled in the project's Vertex
    Model Garden for the chosen region.
    """

    _label = "Claude (Vertex)"

    def __init__(self, project_id: str | None, region: str, model: str):
        if not project_id:
            raise LLMError(
                "VERTEX_PROJECT_ID is not set. Add it to backend/.env (see .env.example) "
                "and run `gcloud auth application-default login`."
            )
        # Imported lazily so the app boots even if the SDK/creds are absent.
        from anthropic import AnthropicVertex

        self._client = AnthropicVertex(project_id=project_id, region=region)
        self._model = model
