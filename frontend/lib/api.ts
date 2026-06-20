// The one module that knows how to talk to the backend. Components depend on these
// functions, never on `fetch` directly, so the transport can change in one place.
import type {
  ChatMessage,
  GenerateOutcome,
  SchematicResult,
  SynthesizeRequest,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    // Surface the backend's {detail: ...} message when present (e.g. missing key).
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export function synthesize(
  req: SynthesizeRequest,
): Promise<SchematicResult> {
  return postJSON<SchematicResult>("/api/synthesize", req);
}

export function chat(messages: ChatMessage[]): Promise<GenerateOutcome> {
  return postJSON<GenerateOutcome>("/api/chat", { messages });
}
