"use client";

import { useState } from "react";

import { ResultTabs } from "@/components/ResultTabs";
import { chat, synthesize } from "@/lib/api";
import type { ChatMessage, SchematicResult } from "@/lib/types";

const SEED_VERILOG = `// Describe a circuit above, or edit Verilog directly, then Synthesize.
module full_adder (
    input  wire a,
    input  wire b,
    input  wire cin,
    output wire sum,
    output wire cout
);
    assign sum  = a ^ b ^ cin;
    assign cout = (a & b) | (cin & (a ^ b));
endmodule`;

const EXAMPLES = [
  "a 4-bit ripple-carry adder",
  "a 2-to-1 multiplexer",
  "a D flip-flop with reset",
  "a 3-bit up counter",
];

export default function Home() {
  const [verilog, setVerilog] = useState(SEED_VERILOG);
  const [result, setResult] = useState<SchematicResult | null>(null);
  const [synthLoading, setSynthLoading] = useState(false);

  // Conversation history drives iteration ("now make it 4-bit") in Step 4.
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [prompt, setPrompt] = useState("");
  const [genLoading, setGenLoading] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Lets the user jump straight into the editor from the hero, before any result.
  const [showEditor, setShowEditor] = useState(false);

  // The prompt is the hero until there's something to show or the user opts into
  // the editor; then the workspace takes over.
  const inWorkspace =
    result !== null ||
    messages.length > 0 ||
    showEditor ||
    genLoading ||
    synthLoading;

  async function onGenerate(override?: string) {
    const text = (override ?? prompt).trim();
    if (!text || genLoading) return;
    setGenLoading(true);
    setError(null);
    setNote(null);
    setResult(null);
    const history: ChatMessage[] = [...messages, { role: "user", content: text }];
    try {
      // Backend generates, synthesizes, and auto-repairs in one call, returning
      // both the Verilog and the rendered schematic.
      const res = await chat(history);
      setVerilog(res.verilog);
      setMessages([...history, { role: "assistant", content: res.verilog }]);
      setPrompt("");
      const repaired = res.attempts > 1 ? ` (auto-fixed in ${res.attempts} tries)` : "";
      setNote(res.explanation + repaired);
      setResult({
        svg: res.svg,
        renderer: res.renderer,
        netlist_json: null,
        logs: "",
        error: res.error,
        wavedrom: res.wavedrom,
        sim_error: res.sim_error,
        testbench: res.testbench,
        formal: res.formal,
        timing: res.timing,
        steps: res.steps,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "generation failed");
    } finally {
      setGenLoading(false);
    }
  }

  async function onSynthesize() {
    setSynthLoading(true);
    setResult(null);
    try {
      setResult(await synthesize({ verilog }));
    } catch (err) {
      setResult({
        svg: null,
        renderer: null,
        netlist_json: null,
        logs: "",
        error: err instanceof Error ? err.message : "request failed",
        wavedrom: null,
        sim_error: null,
        testbench: null,
        formal: null,
        timing: null,
        steps: [],
      });
    } finally {
      setSynthLoading(false);
    }
  }

  if (!inWorkspace) {
    return (
      <Hero
        prompt={prompt}
        setPrompt={setPrompt}
        onGenerate={onGenerate}
        onExamplePick={(t) => {
          setPrompt(t);
          onGenerate(t);
        }}
        onWriteVerilog={() => setShowEditor(true)}
        error={error}
      />
    );
  }

  return (
    <main className="flex h-screen flex-col bg-ink text-bone">
      <header className="flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-hairline px-6 py-3">
        <Wordmark />
        <form
          className="flex min-w-0 flex-1 gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            onGenerate();
          }}
        >
          <input
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Describe a change — e.g. now make it 4-bit"
            className="min-w-0 flex-1 rounded-md border border-hairline bg-ink-2 px-3 py-2 text-sm text-bone placeholder:text-bone-faint outline-none focus:border-saffron"
          />
          <button
            type="submit"
            disabled={genLoading}
            className="shrink-0 rounded-md bg-saffron px-4 py-2 text-sm font-medium text-ink transition-colors hover:bg-ember disabled:opacity-50"
          >
            {genLoading ? "Generating…" : "Generate"}
          </button>
        </form>
        {(note || error) && (
          <p
            className={`w-full text-xs ${error ? "text-err" : "text-bone-dim"}`}
          >
            {error ?? note}
          </p>
        )}
      </header>

      <div className="flex flex-1 flex-col overflow-hidden lg:flex-row">
        {/* Left: generated / editable Verilog */}
        <section className="flex min-h-0 flex-1 flex-col border-hairline max-lg:border-b lg:border-r">
          <div className="flex items-center justify-between border-b border-hairline px-4 py-2">
            <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-bone-faint">
              Verilog source
            </span>
            <button
              onClick={onSynthesize}
              disabled={synthLoading}
              className="rounded-md border border-hairline px-3 py-1.5 text-xs font-medium text-bone transition-colors hover:border-saffron hover:text-ember disabled:opacity-50"
            >
              {synthLoading ? "Synthesizing…" : "Synthesize"}
            </button>
          </div>
          <textarea
            value={verilog}
            onChange={(e) => setVerilog(e.target.value)}
            spellCheck={false}
            className="min-h-0 flex-1 resize-none bg-ink p-4 font-mono text-sm leading-relaxed text-bone outline-none"
          />
        </section>

        {/* Right: schematic + waveform tabs */}
        <section className="min-h-0 flex-1 overflow-hidden">
          <ResultTabs
            result={result}
            loading={synthLoading || genLoading}
            verilog={verilog}
          />
        </section>
      </div>
    </main>
  );
}

function Hero({
  prompt,
  setPrompt,
  onGenerate,
  onExamplePick,
  onWriteVerilog,
  error,
}: {
  prompt: string;
  setPrompt: (v: string) => void;
  onGenerate: () => void;
  onExamplePick: (text: string) => void;
  onWriteVerilog: () => void;
  error: string | null;
}) {
  return (
    <main className="relative flex h-screen flex-col items-center justify-center overflow-hidden bg-ink px-6 text-bone">
      {/* Ember wash — the warmth behind the hero */}
      <div aria-hidden className="hero-wash pointer-events-none absolute inset-0" />

      {/* A flex column owns the layout: items-center centers every child and gap
          sets the rhythm. Type and width scale fluidly with the viewport so the
          hero fills large screens instead of leaving a fixed column of margin. */}
      <div className="hero-stagger relative z-10 flex w-full max-w-2xl flex-col items-center gap-[clamp(1.25rem,2.5vw,2.5rem)] text-center lg:max-w-4xl">
        <Wordmark className="rise" />

        <h1 className="rise font-display text-[clamp(2.5rem,7vw,6.5rem)] font-semibold leading-[1.03] tracking-tight text-bone">
          Describe a circuit.
        </h1>
        <p className="rise max-w-lg text-[clamp(1rem,1.5vw,1.375rem)] leading-relaxed text-bone-dim lg:max-w-2xl">
          We synthesize it to gates, simulate the waveform, and formally prove it
          correct.
        </p>

        <form
          className="rise flex w-full max-w-xl gap-2 lg:max-w-2xl"
          onSubmit={(e) => {
            e.preventDefault();
            onGenerate();
          }}
        >
          <div className="signal-underline flex-1">
            <input
              autoFocus
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="e.g. a 4-bit ripple-carry adder"
              className="w-full rounded-md border border-hairline bg-ink-2 px-4 py-3 text-base text-bone placeholder:text-bone-faint outline-none focus:border-saffron lg:px-5 lg:py-4 lg:text-lg"
            />
          </div>
          <button
            type="submit"
            className="shrink-0 rounded-md bg-saffron px-6 py-3 text-base font-medium text-ink transition-colors hover:bg-ember lg:px-8 lg:py-4 lg:text-lg"
          >
            Generate
          </button>
        </form>

        {error && <p className="rise text-sm text-err">{error}</p>}

        <div className="rise flex flex-wrap justify-center gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              onClick={() => onExamplePick(ex)}
              className="rounded-full border border-hairline px-3.5 py-1.5 text-sm text-bone-dim transition-colors hover:border-saffron hover:text-ember"
            >
              {ex}
            </button>
          ))}
        </div>

        <button
          onClick={onWriteVerilog}
          className="rise text-sm text-bone-faint underline-offset-4 transition-colors hover:text-bone hover:underline"
        >
          or write Verilog directly →
        </button>
      </div>
    </main>
  );
}

function Wordmark({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-2 font-display text-sm font-semibold uppercase tracking-[0.3em] text-bone ${className}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-saffron" />
      Saffron
    </span>
  );
}
