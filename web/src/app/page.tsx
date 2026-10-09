"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useData } from "@/components/DataProvider";
import { conditionsAt, forecastFor, useForecast } from "@/components/useForecast";
import { useLocation } from "@/components/useLocation";
import { useSettings } from "@/components/useSettings";
import { FitBadge } from "@/components/spot-ui";
import { Card, Chip, Notice, PageHeader, ScorePill, SectionTitle, StatusBadge, WindArrow } from "@/components/ui";
import type { Window } from "@/lib/conditions";
import { addDays, labelDay, monthDay, nextSaturday, ymdInTz } from "@/lib/dates";
import { bestPerProperty, rank, type Ranked } from "@/lib/rank";
import { METHOD_LABELS, nextOpening } from "@/lib/seasons";
import { formatClock } from "@/lib/sun";
import type { Method } from "@/lib/types";
import { describeCode } from "@/lib/weather";

const WINDOWS: { key: Window; label: string }[] = [
  { key: "morning", label: "Morning" },
  { key: "evening", label: "Evening" },
  { key: "allday", label: "All day" },
];
const METHODS: Method[] = ["archery", "muzzleloader", "firearm"];

export default function HuntPage() {
  const { catalog, regs, manifest, loading, error, spotById } = useData();
  const [settings, update] = useSettings();
  const { loc, locate } = useLocation();
  const today = ymdInTz(new Date());
  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => addDays(today, i)), [today]);
  const [ymd, setYmd] = useState<string | null>(null);
  const day = ymd ?? nextSaturday(today);
  const [showAll, setShowAll] = useState(false);
  const [everyBlock, setEveryBlock] = useState(false);

  const origin: [number, number] = loc.kind === "ok" ? [loc.lon, loc.lat] : [settings.home.lon, settings.home.lat];
  const originLabel = loc.kind === "ok" ? "your location" : settings.home.label;

  // Units that pass the legal-access gate; only these need forecasts.
  const candidatePoints = useMemo(() => {
    if (!catalog) return [] as [number, number][];
    const ok = new Set(
      catalog.properties.filter((p) => p.access.status === "verified" || (settings.includeUnknown && p.access.status === "unknown")).map((p) => p.id),
    );
    return catalog.units.filter((u) => ok.has(u.property_id)).map((u) => u.point);
  }, [catalog, settings.includeUnknown]);
  const fc = useForecast(candidatePoints);

  const result = useMemo(() => {
    if (!catalog || !regs) return null;
    return rank({
      catalog,
      regs,
      ymd: day,
      method: settings.method,
      origin,
      includeUnknown: settings.includeUnknown,
      factorWeights: settings.factorWeights ?? undefined,
      weights: settings.tripWeights,
      conditionsFor: (u) => conditionsAt(forecastFor(fc.byKey, u.point), u.point, day, settings.window, regs).conditions,
      spotsFor: (u) => (u.spot_ids ?? []).map((id) => spotById.get(id)).filter((x): x is NonNullable<typeof x> => !!x),
    });
    // origin is derived from loc/settings; listing them keeps this stable
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [catalog, regs, day, settings, fc.byKey, loc, spotById]);

  const headline = useMemo(() => {
    if (!regs) return null;
    return conditionsAt(forecastFor(fc.byKey, origin), origin, day, settings.window, regs);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [regs, fc.byKey, day, settings.window, loc, settings.home]);

  const list = useMemo(
    () => (result ? (everyBlock ? result.ranked.map((r) => ({ ...r, more: 0 })) : bestPerProperty(result.ranked)) : []),
    [result, everyBlock],
  );
  const shown = showAll ? list : list.slice(0, 12);
  // Which parts of the model are missing for most of what's shown (e.g. terrain not processed yet).
  const missingFactors = useMemo(() => {
    const top = shown.slice(0, 12);
    if (!top.length) return [] as string[];
    const counts = new Map<string, number>();
    for (const r of top) for (const f of r.unit.score.factors) if (f.value === null) counts.set(f.label, (counts.get(f.label) ?? 0) + 1);
    return [...counts.entries()].filter(([, n]) => n > top.length / 2).map(([label]) => label.toLowerCase());
  }, [shown]);

  return (
    <div>
      <PageHeader
        title="Where to hunt"
        sub={catalog ? `${catalog.region.name} · data built ${new Date(catalog.generated_at).toLocaleDateString()}` : "Northern New Hampshire public land"}
      />

      <div className="space-y-3 px-4">
        <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1" role="group" aria-label="Day">
          {days.map((d) => (
            <Chip key={d} active={d === day} onClick={() => setYmd(d)}>
              <span className="block leading-tight">{labelDay(d, today)}</span>
              <span className="block text-[11px] leading-tight opacity-75">{monthDay(d)}</span>
            </Chip>
          ))}
        </div>
        <div className="flex gap-2" role="group" aria-label="Time of day">
          {WINDOWS.map((w) => (
            <Chip key={w.key} active={settings.window === w.key} onClick={() => update({ window: w.key })}>
              {w.label}
            </Chip>
          ))}
        </div>
        <div className="flex gap-2" role="group" aria-label="Hunting method">
          {METHODS.map((m) => (
            <Chip key={m} active={settings.method === m} onClick={() => update({ method: m })}>
              {METHOD_LABELS[m]}
            </Chip>
          ))}
        </div>
        <div className="flex items-center justify-between gap-3 rounded-xl bg-surface px-3.5 py-2.5 ring-1 ring-line">
          <div className="min-w-0 text-sm">
            <div className="text-muted">Distances from</div>
            <div className="truncate font-medium">
              {loc.kind === "locating" ? "Finding you…" : originLabel}
              {loc.kind === "ok" && <span className="text-faint"> (±{Math.round(loc.accuracyM)} m)</span>}
            </div>
          </div>
          <button type="button" onClick={locate} className="min-h-11 shrink-0 rounded-xl bg-surface-2 px-3 text-sm font-medium ring-1 ring-line">
            Use my location
          </button>
        </div>
        {loc.kind === "error" && <Notice tone="bad">{loc.message}</Notice>}
        <label className="flex min-h-11 items-center justify-between gap-3 px-1 text-sm">
          <span>
            Include unverified land
            <span className="block text-xs text-muted">Research candidates where hunting permission isn&apos;t confirmed</span>
          </span>
          <input
            type="checkbox"
            className="h-6 w-6 accent-[var(--blaze)]"
            checked={settings.includeUnknown}
            onChange={(e) => update({ includeUnknown: e.target.checked })}
          />
        </label>
      </div>

      {loading && <p className="px-4 py-8 text-center text-muted">Loading properties…</p>}
      {error && (
        <div className="px-4 pt-4">
          <Notice tone="bad">{error}</Notice>
        </div>
      )}

      {regs && headline && (
        <div className="px-4">
          <SectionTitle>
            {labelDay(day, today)}, {monthDay(day)} · {WINDOWS.find((w) => w.key === settings.window)!.label.toLowerCase()}
          </SectionTitle>
          <Card className="p-4">
            <div className="flex items-start justify-between gap-4">
              <div className="text-sm">
                <div className="text-muted">Legal shooting hours</div>
                <div className="tabular text-lg font-semibold">
                  {headline.legal ? `${formatClock(headline.legal.start)} – ${formatClock(headline.legal.end)}` : "—"}
                </div>
                <div className="text-xs text-faint">Half hour before sunrise to half hour after sunset, near {originLabel}</div>
              </div>
              {headline.conditions && <ScorePill value={headline.conditions.score} label="Conditions" />}
            </div>
            {headline.conditions ? (
              <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-line pt-3 text-sm">
                <WindArrow fromDeg={headline.conditions.wind.fromDeg} mph={headline.conditions.wind.avgMph} />
                {headline.conditions.tempRange && (
                  <span className="tabular">
                    {Math.round(headline.conditions.tempRange[0])}–{Math.round(headline.conditions.tempRange[1])}°F
                  </span>
                )}
                <span className="text-muted">{describeCode(mode(headline.conditions.codes))}</span>
                {headline.conditions.precipIn > 0.01 && <span className="tabular">{headline.conditions.precipIn.toFixed(2)} in precip</span>}
                {!headline.conditions.wind.steady && <span className="text-warn">Shifting wind</span>}
              </div>
            ) : (
              <p className="mt-3 border-t border-line pt-3 text-sm text-muted">
                {fc.loading ? "Getting the forecast…" : fc.error ?? "No forecast for this day yet (forecasts reach 7 days out)."}
              </p>
            )}
            {day.slice(5) >= "11-12" && day.slice(5) <= "12-06" && (
              <p className="mt-2 text-sm text-info">
                Peak breeding season: Fish and Game says most breeding happens in the three weeks from mid-November, when bucks move more in daylight.
              </p>
            )}
            {headline.conditions?.safety.map((s) => (
              <p key={s} className="mt-2 text-sm text-bad">
                ⚠ {s}
              </p>
            ))}
          </Card>
          {fc.error && headline.conditions && <p className="mt-2 px-1 text-xs text-warn">{fc.error}</p>}
        </div>
      )}

      {result && regs && (
        <div className="px-4">
          <SectionTitle
            right={
              <button type="button" onClick={() => setEveryBlock((v) => !v)} className="text-xs text-info">
                {everyBlock ? "Best block per property" : "Show every block"}
              </button>
            }
          >
            Best bets
          </SectionTitle>
          {missingFactors.length > 0 && (
            <div className="mb-3">
              <Notice>Not in these scores yet: {missingFactors.join(", ")}. Each pick&apos;s &ldquo;Why&rdquo; shows what it&apos;s based on.</Notice>
            </div>
          )}
          {result.ranked.length === 0 ? (
            <EmptyState excluded={result.excluded} nextOpen={nextOpening(regs, day, settings.method, ["A"])} method={settings.method} />
          ) : (
            <ol className="space-y-3">
              {shown.map((r, i) => (
                <ResultCard key={r.unit.id} r={r} rankNo={i + 1} day={day} window={settings.window} />
              ))}
            </ol>
          )}
          {list.length > shown.length && (
            <button type="button" onClick={() => setShowAll(true)} className="mt-3 min-h-11 w-full rounded-xl bg-surface-2 text-sm font-medium ring-1 ring-line">
              Show all {list.length}
            </button>
          )}
          <p className="mt-4 px-1 text-xs text-faint">
            Hidden: {result.excluded.closed} closed for {METHOD_LABELS[settings.method].toLowerCase()} this day
            {!settings.includeUnknown && `, ${result.excluded.unknown} with unverified permission`}, {result.excluded.prohibited} with no public access.
          </p>
          {manifest && regs && !regs.verified_against_print && (
            <p className="mt-2 px-1 text-xs text-faint">
              Season dates come from the online {regs.season_year} digest and haven&apos;t been checked against the printed copy.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function mode(xs: number[]): number | null {
  if (!xs.length) return null;
  const c = new Map<number, number>();
  for (const x of xs) c.set(x, (c.get(x) ?? 0) + 1);
  return [...c.entries()].sort((a, b) => b[1] - a[1])[0][0];
}

function ResultCard({ r, rankNo, day, window }: { r: Ranked & { more: number }; rankNo: number; day: string; window: Window }) {
  const [open, setOpen] = useState(false);
  const href = `/property/?id=${encodeURIComponent(r.property.id)}&unit=${encodeURIComponent(r.unit.id)}&date=${day}&window=${window}`;
  return (
    <li>
      <Card className="overflow-hidden">
        <Link href={href} className="block p-4 active:bg-surface-2">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-xs text-faint">#{rankNo}</div>
              <div className="text-[17px] font-semibold leading-snug">{r.property.name}</div>
              <div className="mt-0.5 text-sm text-muted">
                {[r.unit.label, r.unit.town, r.unit.wmu.units.length ? `WMU ${r.unit.wmu.units.join("/")}` : null, `${Math.round(r.unit.acres).toLocaleString()} ac`]
                  .filter(Boolean)
                  .join(" · ")}
              </div>
            </div>
            <ScorePill value={r.trip} label="Trip" />
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <StatusBadge status={r.property.access.status} small />
            <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs ring-1 ring-line">
              {r.season.deer === "any" ? "Any deer" : "Antlered only"}
            </span>
            {r.season.certainty === "split-unit" && <span className="text-xs text-warn">Near a WMU line</span>}
            {r.more > 0 && <span className="text-xs text-muted">+{r.more} more open blocks here</span>}
          </div>
          {r.best && (
            <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
              <span className="text-muted">Best spot:</span>
              <span className="font-medium">
                {r.best.spot.kind === "saddle" ? "Saddle" : "Bench"} · {r.best.spot.elevation_ft.toLocaleString()} ft
              </span>
              <FitBadge fit={r.best.windFit} />
            </div>
          )}
          {r.windNote && <p className="mt-1 text-xs text-warn">{r.windNote}</p>}
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
            {r.conditions ? <WindArrow fromDeg={r.conditions.wind.fromDeg} mph={r.conditions.wind.avgMph} size={22} /> : <span className="text-muted">No forecast</span>}
            {r.miles !== null && (
              <span className="tabular text-muted">
                {r.miles < 10 ? r.miles.toFixed(1) : Math.round(r.miles)} mi · ~{r.driveMin} min drive (rough)
              </span>
            )}
          </div>
        </Link>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="flex min-h-11 w-full items-center justify-between border-t border-line px-4 text-sm text-muted"
          aria-expanded={open}
        >
          Why this pick
          <span aria-hidden>{open ? "−" : "+"}</span>
        </button>
        {open && (
          <div className="space-y-2 border-t border-line px-4 py-3 text-sm">
            {r.parts.map((p) => (
              <div key={p.label} className="flex justify-between">
                <span>{p.label}</span>
                <span className="tabular text-muted">
                  {Math.round(p.value)} × {Math.round(p.weight * 100)}%
                </span>
              </div>
            ))}
            <p className="text-xs text-faint">{r.unit.score.summary}</p>
            {r.conditions?.parts.map((p) => (
              <p key={p.label} className="text-xs text-muted">
                {p.label} ({p.delta}): {p.why}
              </p>
            ))}
            {r.conditions?.safety.map((s) => (
              <p key={s} className="text-xs text-bad">
                ⚠ {s}
              </p>
            ))}
          </div>
        )}
      </Card>
    </li>
  );
}

function EmptyState({ excluded, nextOpen, method }: { excluded: { prohibited: number; unknown: number; closed: number }; nextOpen: string | null; method: Method }) {
  return (
    <Card className="p-4 text-sm">
      <p className="font-medium">Nothing to recommend for this day.</p>
      {excluded.closed > 0 && (
        <p className="mt-1 text-muted">
          {METHOD_LABELS[method]} season is closed here on this date.
          {nextOpen && ` It opens ${monthDay(nextOpen)} in WMU A.`}
        </p>
      )}
      {excluded.unknown > 0 && (
        <p className="mt-1 text-muted">{excluded.unknown} spots are hidden because hunting permission isn&apos;t verified yet. Turn on &ldquo;Include unverified land&rdquo; to see them.</p>
      )}
    </Card>
  );
}
