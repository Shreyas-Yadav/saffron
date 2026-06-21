// Pure presentational formal-verification report. Shows an overall verdict badge,
// the per-rule checklist (intent rules from the LLM + built-in invariants), and —
// when an intent rule is refuted — the failing input vector as a waveform (reusing
// WaveformPanel).
import { WaveformPanel } from "@/components/WaveformPanel";
import type { FormalCheck, FormalResult } from "@/lib/types";

interface Props {
  formal: FormalResult | null;
  loading: boolean;
}

export function FormalPanel({ formal, loading }: Props) {
  if (loading) return <Centered>Verifying…</Centered>;
  if (!formal)
    return <Centered>Formal results will appear here after generating.</Centered>;

  // Only claim "proven correct" when an intent rule was actually proven — a
  // *skipped* intent rule (clocked designs) must not earn the green badge.
  const provenIntent = formal.checks.some(
    (c) => c.kind === "intent" && c.status === "passed",
  );

  return (
    <div className="h-full w-full overflow-auto bg-neutral-950 p-5">
      <Verdict formal={formal} provenIntent={provenIntent} />

      <ul className="mt-5 space-y-2">
        {formal.checks.map((c, i) => (
          <CheckRow key={c.name + i} check={c} />
        ))}
      </ul>

      {formal.counterexample && (
        <div className="mt-6">
          <h3 className="mb-1 text-sm font-medium text-neutral-200">
            Counterexample — a failing input
          </h3>
          <p className="mb-2 text-xs text-neutral-500">
            The solver found this input vector where the property does not hold:
          </p>
          <div className="h-56 rounded-md border border-neutral-800">
            <WaveformPanel
              wavedrom={formal.counterexample}
              simError={null}
              loading={false}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function Verdict({
  formal,
  provenIntent,
}: {
  formal: FormalResult;
  provenIntent: boolean;
}) {
  const map = {
    proven: {
      cls: "border-emerald-700 bg-emerald-950/40 text-emerald-300",
      label: provenIntent
        ? formal.bounded
          ? `Proven (bounded, ${formal.cycles ?? "N"} cycles)`
          : "Proven correct — holds for all inputs"
        : "Well-formed — no loops or accidental latches",
    },
    refuted: {
      cls: "border-red-800 bg-red-950/40 text-red-300",
      label: "Refuted — a rule does not hold",
    },
    skipped: {
      cls: "border-neutral-700 bg-neutral-900 text-neutral-400",
      label: "No checks were applicable",
    },
    error: {
      cls: "border-amber-800 bg-amber-950/30 text-amber-300",
      label: "Formal check could not run",
    },
  }[formal.status];

  return (
    <div className={`rounded-lg border px-4 py-3 text-sm font-medium ${map.cls}`}>
      {map.label}
    </div>
  );
}

function CheckRow({ check }: { check: FormalCheck }) {
  const icon = {
    passed: { ch: "✓", cls: "text-emerald-400" },
    failed: { ch: "✗", cls: "text-red-400" },
    skipped: { ch: "–", cls: "text-neutral-500" },
    error: { ch: "!", cls: "text-amber-400" },
  }[check.status];

  return (
    <li className="flex gap-3 rounded-md bg-neutral-900/60 px-3 py-2">
      <span className={`mt-0.5 font-mono ${icon.cls}`}>{icon.ch}</span>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[13px] text-neutral-200 break-all">
            {check.name}
          </span>
          <span className="shrink-0 rounded bg-neutral-800 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-neutral-400">
            {check.kind}
          </span>
        </div>
        {check.detail && (
          <p className="mt-0.5 text-xs text-neutral-500">{check.detail}</p>
        )}
      </div>
    </li>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center p-6 text-center text-sm text-neutral-400">
      {children}
    </div>
  );
}
