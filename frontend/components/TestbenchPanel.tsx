// Shows the auto-generated Verilog testbench that drove the simulation. Read-only:
// it's evidence of how the circuit was exercised, not something the user edits.
"use client";

import { useState } from "react";

interface Props {
  testbench: string | null;
  loading: boolean;
}

export function TestbenchPanel({ testbench, loading }: Props) {
  const [copied, setCopied] = useState(false);

  if (loading) return <Centered>Building the testbench…</Centered>;
  if (!testbench)
    return (
      <Centered>The generated testbench will appear here after synthesizing.</Centered>
    );

  async function onCopy() {
    try {
      await navigator.clipboard.writeText(testbench ?? "");
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard can be blocked (insecure context); fail quietly.
    }
  }

  return (
    <div className="flex h-full w-full flex-col bg-ink">
      <div className="flex items-center justify-between border-b border-hairline px-4 py-2">
        <div>
          <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-bone-faint">
            Auto-generated testbench
          </span>
          <p className="mt-0.5 text-xs text-bone-dim">
            Stimulus derived from the module&apos;s ports and run with Icarus Verilog.
          </p>
        </div>
        <button
          onClick={onCopy}
          className="shrink-0 rounded-md border border-hairline px-3 py-1.5 text-xs font-medium text-bone transition-colors hover:border-saffron hover:text-ember"
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="min-h-0 flex-1 overflow-auto p-4 font-mono text-sm leading-relaxed text-bone">
        {testbench}
      </pre>
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center bg-ink p-6 text-center text-sm text-bone-dim">
      {children}
    </div>
  );
}
