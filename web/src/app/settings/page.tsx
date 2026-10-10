"use client";

import { useData } from "@/components/DataProvider";
import { DEFAULT_HOME, DEFAULT_SETTINGS, useSettings } from "@/components/useSettings";
import { Card, Notice, PageHeader, SectionTitle } from "@/components/ui";
import { OfflineAreas } from "@/components/OfflineSave";
import { DEFAULT_TRIP_WEIGHTS, type TripWeights } from "@/lib/rank";
import type { FactorKey } from "@/lib/types";

const FACTOR_LABELS: Record<FactorKey, string> = {
  habitat: "Habitat, food and cover",
  pressure: "Low hunting pressure",
  terrain: "Terrain and travel features",
  access: "Access and huntability",
  abundance: "Regional deer abundance",
};

const TRIP_LABELS: Record<keyof TripWeights, string> = {
  quality: "Property quality",
  conditions: "Day's weather conditions",
  travel: "Short drive",
};

export default function SettingsPage() {
  const [s, update] = useSettings();
  const { catalog, manifest } = useData();
  const base = catalog?.scoring.weights ?? DEFAULT_SETTINGS.factorWeights ?? null;
  const fw = s.factorWeights ?? base;

  return (
    <div>
      <PageHeader title="Settings" />
      <div className="px-4">
        <SectionTitle>Starting point</SectionTitle>
        <Card className="space-y-2 p-4 text-sm">
          <p>
            Distances are measured from <strong>{s.home.label}</strong> unless you tap &ldquo;Use my location&rdquo;.
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              className="min-h-11 rounded-xl bg-surface-2 px-3 font-medium ring-1 ring-line"
              onClick={() =>
                navigator.geolocation?.getCurrentPosition((p) =>
                  update({ home: { label: "Saved spot", lon: p.coords.longitude, lat: p.coords.latitude } }),
                )
              }
            >
              Save current spot
            </button>
            <button type="button" className="min-h-11 rounded-xl px-3 text-muted" onClick={() => update({ home: DEFAULT_HOME })}>
              Reset to Pittsburg
            </button>
          </div>
          <p className="text-xs text-faint">Stored only on this phone.</p>
        </Card>

        <SectionTitle>Offline maps</SectionTitle>
        <Card className="p-4">
          <OfflineAreas />
        </Card>

        <SectionTitle>Property score weights</SectionTitle>
        <Card className="space-y-4 p-4">
          <p className="text-sm text-muted">
            Starting guesses, not proven science. Factors without data yet are skipped, so changing them has no effect until that data is loaded.
          </p>
          {fw &&
            (Object.keys(FACTOR_LABELS) as FactorKey[]).map((k) => (
              <Slider
                key={k}
                label={FACTOR_LABELS[k]}
                value={fw[k]}
                onChange={(v) => update({ factorWeights: { ...fw, [k]: v } })}
              />
            ))}
          <button type="button" onClick={() => update({ factorWeights: null })} className="text-sm text-info">
            Reset to defaults
          </button>
        </Card>

        <SectionTitle>Trip ranking blend</SectionTitle>
        <Card className="space-y-4 p-4">
          {(Object.keys(TRIP_LABELS) as (keyof TripWeights)[]).map((k) => (
            <Slider key={k} label={TRIP_LABELS[k]} value={s.tripWeights[k]} onChange={(v) => update({ tripWeights: { ...s.tripWeights, [k]: v } })} />
          ))}
          <button type="button" onClick={() => update({ tripWeights: DEFAULT_TRIP_WEIGHTS })} className="text-sm text-info">
            Reset to defaults
          </button>
        </Card>

        <SectionTitle>Data and sources</SectionTitle>
        {manifest ? (
          <Card className="space-y-3 p-4 text-sm">
            <p>
              Built {new Date(manifest.finished_at).toLocaleString()} · {manifest.counts.properties} properties, {manifest.counts.units} rankable areas,{" "}
              {manifest.counts.total_acres.toLocaleString()} acres.
            </p>
            <p className="text-muted">
              Permission: {manifest.counts.access_status.verified ?? 0} verified, {manifest.counts.access_status.unknown ?? 0} unverified,{" "}
              {manifest.counts.access_status.prohibited ?? 0} no public access.
            </p>
            <ul className="space-y-2">
              {manifest.sources.map((src) => (
                <li key={src.name} className="flex items-start justify-between gap-3">
                  <span>
                    {src.name}
                    {src.retrieved_at && <span className="block text-xs text-faint">Fetched {new Date(src.retrieved_at).toLocaleString()}</span>}
                    {src.error && <span className="block text-xs text-bad">{src.error}</span>}
                  </span>
                  <span className={src.status === "ok" ? "text-ok" : "text-bad"}>{src.status}</span>
                </li>
              ))}
            </ul>
            {[...manifest.warnings, ...manifest.limitations].map((w) => (
              <p key={w} className="text-xs text-warn">
                {w}
              </p>
            ))}
          </Card>
        ) : (
          <Notice>Data hasn&apos;t loaded.</Notice>
        )}
        <p className="mt-4 px-1 text-xs text-faint">
          Weather: Open-Meteo (CC BY 4.0). Maps and elevation: USGS The National Map and 3DEP. Land records: NH GRANIT (not for legal use). Not a
          substitute for the NH Hunting Digest or posted signs.
        </p>
      </div>
    </div>
  );
}

function Slider({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <label className="block">
      <div className="flex justify-between text-sm">
        <span>{label}</span>
        <span className="tabular text-muted">{Math.round(value * 100)}</span>
      </div>
      <input
        type="range"
        min={0}
        max={1}
        step={0.05}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-1 h-8 w-full accent-[var(--blaze)]"
      />
    </label>
  );
}
