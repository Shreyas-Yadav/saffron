"""FastAPI application entrypoint. Run: `uv run uvicorn app.main:app --reload`."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.routes import router
from .llm.provider import LLMError
from .pipeline.agentic import AgenticError

app = FastAPI(title="Saffron", description="AI hardware design assistant")


@app.exception_handler(LLMError)
@app.exception_handler(AgenticError)
def _llm_error_handler(_: Request, exc: Exception) -> JSONResponse:
    # Misconfigured key / upstream failure / agent turn-limit surfaces as a clean 502,
    # even when the provider fails to construct during dependency resolution.
    return JSONResponse(status_code=502, content={"detail": str(exc)})

# Dev CORS: allow the Next.js dev server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
