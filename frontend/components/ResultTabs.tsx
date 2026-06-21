"use client";

import { useState } from "react";

import { FormalPanel } from "@/components/FormalPanel";
import { SchematicPanel } from "@/components/SchematicPanel";
import { StepsPanel } from "@/components/StepsPanel";
import { TestbenchPanel } from "@/components/TestbenchPanel";
import { TimingPanel } from "@/components/TimingPanel";
import { WaveformPanel } from "@/components/WaveformPanel";
import type { SchematicResult } from "@/lib/types";

interface Props {
  result: SchematicResult | null;
  loading: boolean;
  // The current circuit source — sent alongside a step when asking the LLM to
  // explain it in plain language.
  verilog: string;
}

type Tab = "steps" | "schematic" | "waveform" | "testbench" | "formal" | "timing";

export function ResultTabs({ result, loading, verilog }: Props) {
  const [tab, setTab] = useState<Tab>("steps");

  const tabs: { id: Tab; label: string }[] = [
    { id: "steps", label: "Steps" },
    { id: "schematic", label: "Schematic" },
    { id: "waveform", label: "Waveform" },
    { id: "testbench", label: "Testbench" },
    { id: "formal", label: "Formal" },
    { id: "timing", label: "Timing" },
  ];

  return (
    <div className="flex h-full flex-col">
      <div className="flex gap-1 overflow-x-auto border-b border-hairline px-3 py-2">
        {tabs.map((t) => (
          <TabButton
            key={t.id}
            active={tab === t.id}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </TabButton>
        ))}
      </div>
      <div className="min-h-0 flex-1">
        {tab === "steps" && (
          <StepsPanel
            steps={result?.steps ?? null}
            loading={loading}
            verilog={verilog}
          />
        )}
        {tab === "schematic" && (
          <SchematicPanel result={result} loading={loading} />
        )}
        {tab === "waveform" && (
          <WaveformPanel
            wavedrom={result?.wavedrom ?? null}
            simError={result?.sim_error ?? null}
            loading={loading}
          />
        )}
        {tab === "testbench" && (
          <TestbenchPanel
            testbench={result?.testbench ?? null}
            loading={loading}
          />
        )}
        {tab === "formal" && (
          <FormalPanel formal={result?.formal ?? null} loading={loading} />
        )}
        {tab === "timing" && (
          <TimingPanel timing={result?.timing ?? null} loading={loading} />
        )}
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`relative shrink-0 px-3 py-1.5 text-sm transition-colors ${
        active ? "text-bone" : "text-bone-dim hover:text-bone"
      }`}
    >
      <span className={active ? "signal-underline" : undefined}>{children}</span>
    </button>
  );
}
