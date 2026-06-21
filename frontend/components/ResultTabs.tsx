"use client";

import { useState } from "react";

import { FormalPanel } from "@/components/FormalPanel";
import { SchematicPanel } from "@/components/SchematicPanel";
import { WaveformPanel } from "@/components/WaveformPanel";
import type { SchematicResult } from "@/lib/types";

interface Props {
  result: SchematicResult | null;
  loading: boolean;
}

type Tab = "schematic" | "waveform" | "formal";

export function ResultTabs({ result, loading }: Props) {
  const [tab, setTab] = useState<Tab>("schematic");

  return (
    <div className="flex h-full flex-col">
      <div className="flex gap-1 border-b border-neutral-800 px-3 py-2">
        <TabButton active={tab === "schematic"} onClick={() => setTab("schematic")}>
          Schematic
        </TabButton>
        <TabButton active={tab === "waveform"} onClick={() => setTab("waveform")}>
          Waveform
        </TabButton>
        <TabButton active={tab === "formal"} onClick={() => setTab("formal")}>
          Formal
        </TabButton>
      </div>
      <div className="min-h-0 flex-1">
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
