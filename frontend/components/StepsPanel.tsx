// Student-facing pipeline walkthrough. Raw tool output is evidence, not the main
// experience, so technical details stay collapsed by default.
"use client";

import { useState } from "react";

import { explainStep } from "@/lib/api";
import type { ProcessStep, StepExplanation } from "@/lib/types";

interface Props {
  steps: ProcessStep[] | null;
  loading: boolean;
  verilog: string;
}

export function StepsPanel({ steps, loading, verilog }: Props) {
  if (loading) return <Centered>Running the circuit pipeline…</Centered>;
  if (!steps || steps.length === 0)
    return <Centered>Steps will appear here after generating or synthesizing.</Centered>;

  return (
    <div className="h-full w-full overflow-auto bg-ink p-5">
      <div className="mb-5">
        <h2 className="font-display text-xl font-semibold tracking-tight text-bone">
          What Saffron did
        </h2>
        <p className="mt-1 max-w-2xl text-sm text-bone-dim">
          A plain-language walkthrough of the tools and checks behind this result.
        </p>
      </div>

      <ol className="space-y-3">
        {steps.map((step, i) => (
          <StepCard key={`${step.id}-${i}`} step={step} index={i + 1} verilog={verilog} />
        ))}
      </ol>
    </div>
  );
}

function StepCard({
  step,
  index,
  verilog,
}: {
  step: ProcessStep;
  index: number;
  verilog: string;
}) {
  const s = styleFor(step.status);
  // On-demand LLM deepening of this step, tailored to the current circuit.
  const [explanation, setExplanation] = useState<StepExplanation | null>(null);
  const [explainState, setExplainState] = useState<"idle" | "loading" | "error">(
    "idle",
  );
  const [explainError, setExplainError] = useState<string | null>(null);

  async function onExplain() {
    setExplainState("loading");
    setExplainError(null);
    try {
      const res = await explainStep({ verilog, step });
      setExplanation(res);
      setExplainState("idle");
    } catch (err) {
      setExplainError(err instanceof Error ? err.message : "could not load explanation");
      setExplainState("error");
    }
  }
  return (
    <li className={`rounded-lg border ${s.card} p-4`}>
      <div className="flex gap-3">
        <div
          className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full font-mono text-xs ${s.dot}`}
        >
          {index}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-medium text-bone">{step.title}</h3>
            <span className={`rounded px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${s.badge}`}>
              {step.status}
            </span>
          </div>
          <p className="mt-1 text-sm text-bone-dim">{step.summary}</p>
          {step.details.length > 0 && (
            <ul className="mt-3 space-y-1 text-sm text-bone-dim">
              {step.details.map((d, i) => (
                <li key={i} className="flex gap-2">
                  <span className="mt-0.5 text-bone-faint">•</span>
                  <span>{d}</span>
                </li>
              ))}
            </ul>
          )}
          {step.technical && (
            <details className="mt-3">
              <summary className="cursor-pointer text-xs text-bone-faint hover:text-bone">
                Technical details
              </summary>
              <pre className="mt-2 max-h-48 overflow-auto rounded-md border border-hairline bg-ink-3 p-3 text-xs text-bone-dim">
                {step.technical}
              </pre>
            </details>
          )}

          {/* On-demand, learner-friendly deepening. The template above always stays.
              Presentation adapts to the step: errors → "How to fix" (numbered steps),
              results → "What this means" (takeaways). */}
          {explanation ? (
            <ExplanationCard status={step.status} explanation={explanation} />
          ) : (
            <div className="mt-3">
              <button
                onClick={onExplain}
                disabled={explainState === "loading"}
                className="inline-flex items-center gap-1.5 rounded-md border border-hairline px-2.5 py-1 text-xs text-bone-dim transition-colors hover:border-saffron hover:text-ember disabled:opacity-50"
              >
                <SparkleIcon />
                {explainState === "loading" ? "Explaining…" : "Explain in simple terms"}
              </button>
              {explainState === "error" && (
                <p className="mt-2 text-xs text-err">
                  {explainError} — please try again.
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </li>
  );
}

// The LLM explanation, framed by step status: actionable fix steps for problems,
// plain-language takeaways for results. Themed to match the card it sits in.
function ExplanationCard({
  status,
  explanation,
}: {
  status: ProcessStep["status"];
  explanation: StepExplanation;
}) {
  const t = explainTheme(status);
  const isFix = status === "error" || status === "warning";
  const Icon = status === "success" ? CheckIcon : status === "skipped" ? InfoIcon : AlertIcon;

  return (
    <div className={`mt-3 rounded-lg border ${t.box} p-3.5`}>
      <div className={`flex items-center gap-1.5 ${t.accent}`}>
        <Icon />
        <p className="text-xs font-semibold uppercase tracking-wide">
          {isFix ? "How to fix" : "What this means"}
        </p>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-bone">{explanation.headline}</p>

      {explanation.points.length > 0 &&
        (isFix ? (
          <ol className="mt-3 space-y-2">
            {explanation.points.map((p, i) => (
              <li key={i} className="flex gap-2.5 text-sm leading-relaxed text-bone-dim">
                <span
                  className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-medium ${t.num}`}
                >
                  {i + 1}
                </span>
                <span>{p}</span>
              </li>
            ))}
          </ol>
        ) : (
          <ul className="mt-3 space-y-1.5">
            {explanation.points.map((p, i) => (
              <li key={i} className="flex gap-2.5 text-sm leading-relaxed text-bone-dim">
                <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${t.dot}`} />
                <span>{p}</span>
              </li>
            ))}
          </ul>
        ))}
    </div>
  );
}

function explainTheme(status: ProcessStep["status"]) {
  return {
    error: {
      box: "border-err/30 bg-err/10",
      accent: "text-err",
      num: "bg-err/15 text-err ring-1 ring-err/30",
      dot: "bg-err",
    },
    warning: {
      box: "border-warn/30 bg-warn/10",
      accent: "text-warn",
      num: "bg-warn/15 text-warn ring-1 ring-warn/30",
      dot: "bg-warn",
    },
    success: {
      box: "border-ok/30 bg-ok/10",
      accent: "text-ok",
      num: "bg-ok/15 text-ok ring-1 ring-ok/30",
      dot: "bg-ok",
    },
    skipped: {
      box: "border-info/30 bg-info/10",
      accent: "text-info",
      num: "bg-info/15 text-info ring-1 ring-info/30",
      dot: "bg-info",
    },
  }[status];
}

function AlertIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
      <path
        fillRule="evenodd"
        d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 8a1 1 0 100-2 1 1 0 000 2z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
      <path
        fillRule="evenodd"
        d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function InfoIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
      <path
        fillRule="evenodd"
        d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function SparkleIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5">
      <path d="M10 2l1.6 4.4L16 8l-4.4 1.6L10 14l-1.6-4.4L4 8l4.4-1.6L10 2zM15.5 12l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2z" />
    </svg>
  );
}

function styleFor(status: ProcessStep["status"]) {
  return {
    success: {
      card: "border-ok/25 bg-ok/[0.07]",
      dot: "bg-ok text-ink",
      badge: "bg-ok/15 text-ok",
    },
    warning: {
      card: "border-warn/25 bg-warn/[0.07]",
      dot: "bg-warn text-ink",
      badge: "bg-warn/15 text-warn",
    },
    error: {
      card: "border-err/25 bg-err/[0.07]",
      dot: "bg-err text-ink",
      badge: "bg-err/15 text-err",
    },
    skipped: {
      card: "border-hairline bg-ink-2",
      dot: "bg-ink-3 text-bone",
      badge: "bg-ink-3 text-bone-dim",
    },
  }[status];
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center bg-ink p-6 text-center text-sm text-bone-dim">
      {children}
    </div>
  );
}
