"use client";

import { useState } from "react";

import { FormalPanel } from "@/components/FormalPanel";
import { SchematicPanel } from "@/components/SchematicPanel";
import { StepsPanel } from "@/components/StepsPanel";
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

type Tab = "steps" | "schematic" | "waveform" | "formal" | "timing";

export function ResultTabs({ result, loading, verilog }: Props) {
  const [tab, setTab] = useState<Tab>("steps");

  return (
    <div className="flex h-full flex-col">
      <div className="flex gap-1 border-b border-neutral-800 px-3 py-2">
        <TabButton active={tab === "steps"} onClick={() => setTab("steps")}>
          Steps
        </TabButton>
        <TabButton active={tab === "schematic"} onClick={() => setTab("schematic")}>
          Schematic
        </TabButton>
        <TabButton active={tab === "waveform"} onClick={() => setTab("waveform")}>
          Waveform
        </TabButton>
        <TabButton active={tab === "formal"} onClick={() => setTab("formal")}>
          Formal
        </TabButton>
        <TabButton active={tab === "timing"} onClick={() => setTab("timing")}>
          Timing
        </TabButton>
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
      className={`rounded-md px-3 py-1 text-sm ${
        active
          ? "bg-neutral-800 text-neutral-100"
          : "text-neutral-400 hover:text-neutral-200"
      }`}
    >
      {children}
    </button>
  );
}
