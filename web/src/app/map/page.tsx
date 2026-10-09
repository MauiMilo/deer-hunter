"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useState } from "react";
import { useData } from "@/components/DataProvider";
import type { BaseLayer } from "@/components/MapView";
import { BASE_LABELS } from "@/components/MapView";
import { ScorePill, StatusBadge } from "@/components/ui";

const MapView = dynamic(() => import("@/components/MapView"), { ssr: false });

export default function MapPage() {
  const { propertyById, unitById, error } = useData();
  const [base, setBase] = useState<BaseLayer>("topo");
  const [blocks, setBlocks] = useState(true);
  const [sel, setSel] = useState<{ property: string; unit: string | null } | null>(null);

  const prop = sel ? propertyById.get(sel.property) : undefined;
  const unit = sel?.unit ? unitById.get(sel.unit) : undefined;
  const bestUnit = prop && !unit && prop.unit_ids.length === 1 ? unitById.get(prop.unit_ids[0]) : undefined;
  const shownUnit = unit ?? bestUnit;

  return (
    <div className="fixed inset-x-0 bottom-[calc(3.5rem+env(safe-area-inset-bottom))] top-0 mx-auto max-w-xl">
      <MapView
        className="h-full w-full"
        base={base}
        showBlocks={blocks}
        highlightPropertyId={sel?.property ?? null}
        highlightUnitId={sel?.unit ?? null}
        onSelectProperty={(id) => setSel({ property: id, unit: null })}
        onSelectUnit={(id) => {
          const u = unitById.get(id);
          if (u) setSel({ property: u.property_id, unit: id });
        }}
      />

      <div className="pt-safe pointer-events-none absolute inset-x-0 top-0 flex flex-col items-start gap-2 px-3">
        <div className="pointer-events-auto flex overflow-hidden rounded-xl bg-surface/95 text-sm shadow ring-1 ring-line backdrop-blur" role="group" aria-label="Base map">
          {(Object.keys(BASE_LABELS) as BaseLayer[]).map((b) => (
            <button
              key={b}
              type="button"
              aria-pressed={base === b}
              onClick={() => setBase(b)}
              className={`min-h-10 px-3 font-medium ${base === b ? "bg-blaze text-blaze-ink" : "text-text"}`}
            >
              {BASE_LABELS[b]}
            </button>
          ))}
        </div>
        <div className="pointer-events-auto flex items-center gap-3 rounded-xl bg-surface/95 px-3 py-2 text-xs shadow ring-1 ring-line backdrop-blur">
          <Legend color="#2fbf71" label="Allowed" />
          <Legend color="#e3b341" label="Unverified" />
          <Legend color="#e5534b" label="No access" />
          <label className="ml-1 flex items-center gap-1.5">
            <input type="checkbox" checked={blocks} onChange={(e) => setBlocks(e.target.checked)} className="accent-[var(--blaze)]" />
            Blocks
          </label>
        </div>
        {error && <div className="pointer-events-auto rounded-lg bg-bad/90 px-3 py-2 text-sm text-white">{error}</div>}
      </div>

      {prop && (
        <div className="absolute inset-x-3 bottom-3 rounded-2xl bg-surface p-4 shadow-lg ring-1 ring-line">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-[17px] font-semibold leading-snug">{prop.name}</div>
              <div className="mt-0.5 text-sm text-muted">
                {[shownUnit?.label, `${Math.round((shownUnit ?? prop).acres).toLocaleString()} ac`, prop.agency].filter(Boolean).join(" · ")}
              </div>
              <div className="mt-2">
                <StatusBadge status={prop.access.status} small />
              </div>
            </div>
            <div className="flex flex-col items-end gap-2">
              <button type="button" onClick={() => setSel(null)} className="-mr-1 -mt-1 h-9 w-9 rounded-full text-muted" aria-label="Close">
                ✕
              </button>
              {shownUnit && <ScorePill value={shownUnit.score.score} provisional={shownUnit.score.provisional} label="Quality" />}
            </div>
          </div>
          {!unit && prop.unit_ids.length > 1 && <p className="mt-2 text-xs text-faint">Zoom in and tap a block to pick a specific area.</p>}
          <Link
            href={`/property/?id=${encodeURIComponent(prop.id)}${sel?.unit ? `&unit=${encodeURIComponent(sel.unit)}` : ""}`}
            className="mt-3 flex min-h-11 items-center justify-center rounded-xl bg-blaze font-semibold text-blaze-ink"
          >
            Details
          </Link>
        </div>
      )}
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className="h-3 w-3 rounded-sm" style={{ background: color }} aria-hidden />
      {label}
    </span>
  );
}
