"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { useData } from "@/components/DataProvider";
import { BASE_LABELS, type BaseLayer } from "@/components/MapView";
import { conditionsAt, forecastFor, useForecast } from "@/components/useForecast";
import { useSaved } from "@/components/useSaved";
import { useSettings } from "@/components/useSettings";
import { SpotCard, WindRose } from "@/components/spot-ui";
import { Card, Chip, FactorList, Notice, ScorePill, SectionTitle, Sources, StatusBadge, WindArrow } from "@/components/ui";
import type { Window } from "@/lib/conditions";
import { addDays, labelDay, monthDay, ymdInTz } from "@/lib/dates";
import { METHOD_LABELS, seasonStatus } from "@/lib/seasons";
import { formatClock } from "@/lib/sun";
import { evaluateSpot } from "@/lib/spots";
import type { Property, Spot, Unit, WindHistory } from "@/lib/types";
import { compassName, downwind } from "@/lib/wind";

const MapView = dynamic(() => import("@/components/MapView"), { ssr: false });

export default function PropertyPage() {
  return (
    <Suspense fallback={<p className="p-6 text-muted">Loading…</p>}>
      <PropertyInner />
    </Suspense>
  );
}

function PropertyInner() {
  const params = useSearchParams();
  const router = useRouter();
  const { propertyById, unitById, spotById, catalog, regs, loading, windHistory } = useData();
  const [focusSpot, setFocusSpot] = useState<Spot | null>(null);
  const [settings] = useSettings();
  const id = params.get("id") ?? "";
  const prop = propertyById.get(id);
  const today = ymdInTz(new Date());
  const day = params.get("date") ?? today;
  const window = (params.get("window") as Window) ?? settings.window;

  const units = useMemo(
    () =>
      (prop?.unit_ids ?? [])
        .map((u) => unitById.get(u))
        .filter((u): u is Unit => !!u)
        .sort((a, b) => (b.score.score ?? -1) - (a.score.score ?? -1)),
    [prop, unitById],
  );
  const unit = unitById.get(params.get("unit") ?? "") ?? units[0];
  const unitPoints = useMemo(() => (unit ? [unit.point] : []), [unit]);
  const fc = useForecast(unitPoints);
  const dayWind =
    unit && regs ? conditionsAt(forecastFor(fc.byKey, unit.point), unit.point, day, window, regs).conditions?.wind.fromDeg ?? null : null;
  const unitSpots = useMemo(
    () => (unit?.spot_ids ?? []).map((id) => spotById.get(id)).filter((x): x is Spot => !!x),
    [unit, spotById],
  );

  const setParam = (k: string, v: string) => {
    const p = new URLSearchParams(params.toString());
    p.set(k, v);
    router.replace(`/property/?${p.toString()}`, { scroll: false });
  };

  if (loading) return <p className="p-6 text-muted">Loading…</p>;
  if (!prop || !catalog || !regs) {
    return (
      <div className="p-4">
        <Notice tone="bad">That property isn&apos;t in the current data.</Notice>
        <Link href="/" className="mt-4 inline-block text-info underline">
          Back to Hunt
        </Link>
      </div>
    );
  }

  return (
    <div>
      <Header prop={prop} />
      <PropertyMap
        prop={prop}
        unit={unit}
        focusSpot={focusSpot}
        onUnit={(uid) => {
          setFocusSpot(null);
          setParam("unit", uid);
        }}
        onSpot={(id) => setFocusSpot(spotById.get(id) ?? null)}
      />

      <div className="px-4">
        {units.length > 1 && (
          <>
            <SectionTitle right={<span className="text-xs text-faint">{units.length} blocks, best first</span>}>Blocks</SectionTitle>
            <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
              {units.map((u) => (
                <Chip key={u.id} active={u.id === unit?.id} onClick={() => setParam("unit", u.id)}>
                  {u.label?.replace("Block ", "")} · {u.score.score ?? "–"}
                </Chip>
              ))}
            </div>
          </>
        )}

        <AccessSection prop={prop} />
        {unit && <DaySection unit={unit} day={day} window={window} today={today} fc={fc} onDay={(d) => setParam("date", d)} />}
        {unit && (
          <SpotsSection
            terrainAnalyzed={unit.score.factors.some((f) => f.key === "terrain" && f.value !== null)}
            spots={unitSpots}
            windFromDeg={dayWind}
            focus={focusSpot}
            onShow={(sp) => {
              setFocusSpot(sp);
              globalThis.scrollTo?.({ top: 0, behavior: "smooth" });
            }}
          />
        )}
        {unit && windHistory && <WindHistorySection history={windHistory} point={unit.point} day={day} />}
        {unit && (
          <>
            <SectionTitle right={<ScorePill value={unit.score.score} provisional={unit.score.provisional} />}>
              Property quality{unit.label ? ` · ${unit.label}` : ""}
            </SectionTitle>
            <Card className="px-4 pb-2 pt-3">
              <p className="text-sm text-muted">{unit.score.summary}</p>
              {unit.score.provisional && (
                <p className="mt-1 text-xs text-warn">Provisional: too little of the model has data to treat this as a real ranking yet.</p>
              )}
              <FactorList factors={unit.score.factors} />
            </Card>
          </>
        )}
        <Records prop={prop} />
        <SavedNote prop={prop} />
      </div>
    </div>
  );
}

function Header({ prop }: { prop: Property }) {
  const { isSaved, toggle } = useSaved();
  const saved = isSaved(prop.id);
  return (
    <header className="pt-safe px-4 pb-3">
      <Link href="/" className="text-sm text-info">
        ‹ Back
      </Link>
      <div className="mt-1 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-[24px] font-bold leading-tight tracking-tight">{prop.name}</h1>
          <p className="mt-0.5 text-sm text-muted">
            {[prop.agency, prop.protection_type, `${Math.round(prop.acres).toLocaleString()} acres in ${prop.towns.join(", ") || "Coos County"}`]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>
        <button
          type="button"
          onClick={() => toggle(prop.id, prop.name)}
          className={`min-h-11 shrink-0 rounded-xl px-3 text-sm font-medium ring-1 ${saved ? "bg-blaze text-blaze-ink ring-blaze" : "bg-surface-2 ring-line"}`}
          aria-pressed={saved}
        >
          {saved ? "Saved" : "Save"}
        </button>
      </div>
      <div className="mt-2">
        <StatusBadge status={prop.access.status} />
      </div>
    </header>
  );
}

function PropertyMap({
  prop,
  unit,
  focusSpot,
  onUnit,
  onSpot,
}: {
  prop: Property;
  unit?: Unit;
  focusSpot: Spot | null;
  onUnit: (id: string) => void;
  onSpot: (id: string) => void;
}) {
  const { landcover } = useData();
  const [base, setBase] = useState<BaseLayer>("topo");
  const [lcOn, setLcOn] = useState(false);
  const bbox: [number, number, number, number] = focusSpot
    ? [focusSpot.point[0] - 0.006, focusSpot.point[1] - 0.004, focusSpot.point[0] + 0.006, focusSpot.point[1] + 0.004]
    : unit?.is_block
      ? unit.bbox
      : prop.bbox;
  return (
    <div className="relative">
      <MapView
        className="h-72 w-full"
        base={base}
        fitBbox={bbox}
        highlightPropertyId={prop.id}
        highlightUnitId={unit?.is_block ? unit.id : null}
        highlightSpotId={focusSpot?.id ?? null}
        landcover={landcover}
        showLandcover={lcOn}
        onSelectUnit={(id) => id.startsWith(`${prop.id}~`) && onUnit(id)}
        onSelectSpot={onSpot}
      />
      <div className="absolute left-3 top-3 flex overflow-hidden rounded-lg bg-surface/95 text-xs shadow ring-1 ring-line">
        {(Object.keys(BASE_LABELS) as BaseLayer[]).map((b) => (
          <button key={b} type="button" onClick={() => setBase(b)} className={`min-h-9 px-2.5 font-medium ${base === b ? "bg-blaze text-blaze-ink" : ""}`}>
            {BASE_LABELS[b]}
          </button>
        ))}
        {landcover && (
          <button type="button" onClick={() => setLcOn((v) => !v)} className={`min-h-9 px-2.5 font-medium ${lcOn ? "bg-blaze text-blaze-ink" : ""}`} aria-pressed={lcOn}>
            Cover
          </button>
        )}
      </div>
    </div>
  );
}

function AccessSection({ prop }: { prop: Property }) {
  const { catalog } = useData();
  const a = prop.access;
  return (
    <>
      <SectionTitle>Hunting permission</SectionTitle>
      <Card className="space-y-3 p-4">
        <StatusBadge status={a.status} />
        <p className="text-[15px]">{a.summary}</p>
        {a.notes.map((n) => (
          <Notice key={n} tone="warn">
            {n}
          </Notice>
        ))}
        {a.restrictions.length > 0 && (
          <div>
            <div className="text-sm font-medium">Rules here</div>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-muted">
              {a.restrictions.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </div>
        )}
        <div>
          <div className="text-sm font-medium">Sources{a.checked_on ? ` (checked ${a.checked_on})` : ""}</div>
          <div className="mt-1">
            <Sources sources={a.sources} />
          </div>
        </div>
        {a.status !== "verified" && (
          <p className="text-xs text-faint">
            To mark this verified, check with the landowner or managing agency, then add it to <code>pipeline/data/verifications.yaml</code> with the source and date.
          </p>
        )}
      </Card>
      {catalog && (
        <ul className="mt-2 space-y-1 px-1 text-xs text-faint">
          {catalog.general_restrictions.map((g) => (
            <li key={g.text}>• {g.text}</li>
          ))}
        </ul>
      )}
    </>
  );
}

function DaySection({
  unit,
  day,
  window,
  today,
  fc,
  onDay,
}: {
  unit: Unit;
  day: string;
  window: Window;
  today: string;
  fc: ReturnType<typeof useForecast>;
  onDay: (d: string) => void;
}) {
  const { regs } = useData();
  const [settings] = useSettings();
  if (!regs) return null;
  const forecast = forecastFor(fc.byKey, unit.point);
  const season = seasonStatus(regs, day, settings.method, unit.wmu.units);
  const { conditions, legal } = conditionsAt(forecast, unit.point, day, window, regs);
  const days = Array.from({ length: 7 }, (_, i) => addDays(today, i));

  return (
    <>
      <SectionTitle>
        {labelDay(day, today)}, {monthDay(day)} · {METHOD_LABELS[settings.method]}
      </SectionTitle>
      <Card className="space-y-3 p-4">
        <div className={`text-sm font-medium ${season.open ? "text-ok" : "text-bad"}`}>{season.message}</div>
        {settings.method !== "firearm" && regs.method_notes.crossbow && (
          <p className="text-xs text-muted">{regs.method_notes.crossbow}</p>
        )}
        {(settings.method === "firearm" || settings.method === "muzzleloader") && regs.method_notes.registration && (
          <p className="text-xs text-muted">{regs.method_notes.registration}</p>
        )}
        {unit.wmu.confidence !== "mapped" && <p className="text-xs text-warn">{unit.wmu.note}</p>}
        {legal && (
          <div className="text-sm">
            <span className="text-muted">Legal hours: </span>
            <span className="tabular font-medium">
              {formatClock(legal.start)} – {formatClock(legal.end)}
            </span>
            <span className="text-faint"> (sunrise {formatClock(legal.sunrise)}, sunset {formatClock(legal.sunset)})</span>
          </div>
        )}
        {conditions ? (
          <div className="border-t border-line pt-3">
            <div className="flex items-center justify-between">
              <WindArrow fromDeg={conditions.wind.fromDeg} mph={conditions.wind.avgMph} />
              <ScorePill value={conditions.score} label="Conditions" />
            </div>
            {conditions.wind.fromDeg !== null && (
              <p className="mt-2 text-sm text-muted">
                Wind from the {compassName(conditions.wind.fromDeg)} carries your scent {compassName(downwind(conditions.wind.fromDeg))}. Set up where deer are
                likely to come from the {compassName(conditions.wind.fromDeg)} or from the side, and walk in from the {compassName(downwind(conditions.wind.fromDeg))}.
                {!conditions.wind.steady && " The forecast wind shifts a lot in this window; expect swirling."}
              </p>
            )}
            <p className="mt-1 text-xs text-faint">
              Regional forecast only. Hills, hollows and morning thermals can turn the wind on the ground; check it when you get there.
            </p>
            {conditions.safety.map((s) => (
              <p key={s} className="mt-2 text-sm text-bad">
                ⚠ {s}
              </p>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted">{fc.loading ? "Getting the forecast…" : fc.error ?? "No forecast for this day."}</p>
        )}
      </Card>

      {forecast && (
        <div className="-mx-4 mt-2 flex gap-2 overflow-x-auto px-4 pb-1">
          {days.map((d) => {
            const am = conditionsAt(forecast, unit.point, d, "morning", regs).conditions;
            const pm = conditionsAt(forecast, unit.point, d, "evening", regs).conditions;
            return (
              <button
                key={d}
                type="button"
                onClick={() => onDay(d)}
                className={`min-w-[5.5rem] shrink-0 rounded-xl px-2.5 py-2 text-left text-xs ring-1 ${d === day ? "bg-surface-2 ring-blaze" : "bg-surface ring-line"}`}
              >
                <div className="font-semibold">{labelDay(d, today)}</div>
                <div className="mt-1 flex items-center justify-between">
                  <span className="text-faint">AM</span>
                  <span className="tabular">{am?.score ?? "–"}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-faint">PM</span>
                  <span className="tabular">{pm?.score ?? "–"}</span>
                </div>
                {am && <WindArrow fromDeg={am.wind.fromDeg} size={16} />}
              </button>
            );
          })}
        </div>
      )}
    </>
  );
}

function Records({ prop }: { prop: Property }) {
  const rows: [string, string | number | null][] = [
    ["Manager / protecting agency", prop.agency],
    ["Second agency", prop.secondary_agency],
    ["Protection", prop.protection_type],
    ["Ownership", prop.owner_type],
    ["Program", prop.program],
    ["Management", prop.management_status],
    ["Public access (GRANIT)", prop.public_access],
    ["Boundary accuracy", prop.boundary_accuracy],
    ["Mapped acres here", Math.round(prop.acres).toLocaleString()],
    ["Whole project acres", prop.parent_acres ? Math.round(prop.parent_acres).toLocaleString() : null],
    ["Towns", prop.towns.join(", ")],
    ["GRANIT tract IDs", prop.tract_ids.join(", ")],
    ["Last changed in GRANIT", prop.date_altered],
  ];
  return (
    <>
      <SectionTitle>Records</SectionTitle>
      <Card className="p-4">
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
          {rows
            .filter(([, v]) => v !== null && v !== "")
            .map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-muted">{k}</dt>
                <dd className="break-words">{v}</dd>
              </div>
            ))}
        </dl>
        {prop.clipped_to_region && <p className="mt-3 text-xs text-faint">This property continues past the county line; only the Coos County part is shown.</p>}
        {prop.overlaps.length > 0 && (
          <p className="mt-3 text-xs text-faint">
            Overlaps: {prop.overlaps.map((o) => `${o.name} (${o.shared_acres.toLocaleString()} ac shared)`).join("; ")}.
          </p>
        )}
        {prop.notes && <p className="mt-3 text-xs text-faint">GRANIT notes: {prop.notes}</p>}
      </Card>
    </>
  );
}

function SavedNote({ prop }: { prop: Property }) {
  const { items, setNote } = useSaved();
  const item = items.find((i) => i.id === prop.id);
  if (!item) return null;
  return (
    <>
      <SectionTitle>Your notes</SectionTitle>
      <textarea
        defaultValue={item.note}
        onBlur={(e) => setNote(prop.id, e.target.value)}
        rows={4}
        placeholder="Sign, scrapes, where you parked… (stays on this phone)"
        className="w-full rounded-2xl bg-surface p-3 text-[15px] ring-1 ring-line placeholder:text-faint"
      />
    </>
  );
}

function SpotsSection({
  terrainAnalyzed,
  spots,
  windFromDeg,
  focus,
  onShow,
}: {
  terrainAnalyzed: boolean;
  spots: Spot[];
  windFromDeg: number | null;
  focus: Spot | null;
  onShow: (s: Spot) => void;
}) {
  const sorted = [...spots].sort((a, b) => evaluateSpot(b, windFromDeg).dayScore - evaluateSpot(a, windFromDeg).dayScore);
  return (
    <>
      <SectionTitle right={<span className="text-xs text-faint">{windFromDeg === null ? "no forecast wind" : "ranked for this day's wind"}</span>}>
        Scouting spots
      </SectionTitle>
      {sorted.length === 0 && !terrainAnalyzed ? (
        <Card className="p-4 text-sm text-muted">The elevation data for this area hasn&apos;t been processed yet, so there are no terrain spots to show.</Card>
      ) : sorted.length === 0 ? (
        <Card className="p-4 text-sm text-muted">
          No saddles or benches stood out in the elevation data here. On flatter ground, deer travel tends to follow cover edges, wetland margins and
          streams instead; check the land cover layer.
        </Card>
      ) : (
        <div className="space-y-3">
          {sorted.map((sp, i) => (
            <SpotCard key={sp.id} spot={sp} rank={i + 1} windFromDeg={windFromDeg} selected={focus?.id === sp.id} onShow={() => onShow(sp)} />
          ))}
        </div>
      )}
    </>
  );
}

function nearestRose(history: WindHistory, point: [number, number]) {
  let best: { key: string; d: number } | null = null;
  for (const [key, p] of Object.entries(history.points)) {
    const d = (p.lat - point[1]) ** 2 + ((p.lon - point[0]) * Math.cos((point[1] * Math.PI) / 180)) ** 2;
    if (!best || d < best.d) best = { key, d };
  }
  return best ? history.points[best.key] : null;
}

const MONTH_NAMES: Record<string, string> = { "9": "September", "10": "October", "11": "November", "12": "December" };

function WindHistorySection({ history, point, day }: { history: WindHistory; point: [number, number]; day: string }) {
  const p = nearestRose(history, point);
  const month = String(Number(day.slice(5, 7)));
  const m = p?.seasons[month] ?? p?.seasons["11"];
  if (!p || !m) return null;
  const label = MONTH_NAMES[month] ?? "November";
  return (
    <>
      <SectionTitle>Usual {label} winds</SectionTitle>
      <Card className="p-4">
        <div className="grid grid-cols-2 gap-3">
          {(["morning", "evening"] as const).map((w) =>
            m[w] ? (
              <div key={w} className="flex flex-col items-center text-center">
                <div className="text-sm font-medium">{w === "morning" ? "Mornings" : "Evenings"}</div>
                <WindRose cell={m[w]!} size={140} />
                <div className="text-xs text-muted">
                  Mostly from the {m[w]!.mean_from_deg === null ? "—" : compassName(m[w]!.mean_from_deg!)}
                  {m[w]!.median_mph !== null && ` · typical ${Math.round(m[w]!.median_mph!)} mph`}
                  {m[w]!.calm_share !== null && m[w]!.calm_share! > 0.15 && ` · calm ${Math.round(100 * m[w]!.calm_share!)}% of hours`}
                </div>
              </div>
            ) : null,
          )}
        </div>
        <p className="mt-3 text-xs text-faint">
          {history.period[0].slice(0, 4)}–{history.period[1].slice(0, 4)} hourly model winds near here (Open-Meteo). {history.note}
        </p>
      </Card>
    </>
  );
}
