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

  async function onGenerate() {
    const text = prompt.trim();
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
        formal: res.formal,
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
        formal: null,
      });
    } finally {
      setSynthLoading(false);
    }
  }

  return (
    <main className="flex h-screen flex-col bg-neutral-950 text-neutral-100">
      <header className="border-b border-neutral-800 px-6 py-3">
        <h1 className="text-lg font-semibold">
          Saffron <span className="text-amber-400">·</span>{" "}
          <span className="font-normal text-neutral-400">
            natural language → verified circuit
          </span>
        </h1>
      </header>

      <div className="grid flex-1 grid-cols-2 overflow-hidden">
        {/* Left: prompt + generated Verilog */}
        <section className="flex min-h-0 flex-col border-r border-neutral-800">
          <div className="border-b border-neutral-800 p-3">
            <div className="flex gap-2">
              <input
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && onGenerate()}
                placeholder="e.g. a 4-bit ripple-carry adder"
                className="flex-1 rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm outline-none focus:border-amber-500"
              />
              <button
                onClick={onGenerate}
                disabled={genLoading}
                className="rounded-md bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-950 hover:bg-white disabled:opacity-50"
              >
                {genLoading ? "Generating…" : "Generate"}
              </button>
            </div>
            {note && <p className="mt-2 text-xs text-neutral-400">{note}</p>}
            {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
          </div>

          <textarea
            value={verilog}
            onChange={(e) => setVerilog(e.target.value)}
            spellCheck={false}
            className="min-h-0 flex-1 resize-none bg-neutral-950 p-4 font-mono text-sm text-neutral-200 outline-none"
          />

          <div className="border-t border-neutral-800 p-3">
            <button
              onClick={onSynthesize}
              disabled={synthLoading}
              className="rounded-md bg-amber-500 px-4 py-2 text-sm font-medium text-neutral-950 hover:bg-amber-400 disabled:opacity-50"
            >
              {synthLoading ? "Synthesizing…" : "Synthesize"}
            </button>
          </div>
        </section>

        {/* Right: schematic + waveform tabs */}
        <section className="overflow-hidden">
          <ResultTabs result={result} loading={synthLoading || genLoading} />
        </section>
      </div>
    </main>
  );
}
