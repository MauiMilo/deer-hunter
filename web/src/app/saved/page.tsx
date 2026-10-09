"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useData } from "@/components/DataProvider";
import { useFieldLog } from "@/components/useFieldLog";
import { useLocation } from "@/components/useLocation";
import { useSaved } from "@/components/useSaved";
import { Card, Chip, Notice, PageHeader, SectionTitle, StatusBadge } from "@/components/ui";
import { ymdInTz } from "@/lib/dates";
import { newId, sightingRate, toGpx, WAYPOINT_KINDS, type Observation, type WaypointKind } from "@/lib/fieldlog";

type Tab = "places" | "waypoints" | "log";

export default function SavedPage() {
  const [tab, setTab] = useState<Tab>("places");
  return (
    <div>
      <PageHeader title="Saved" sub="Everything here stays on this phone." />
      <div className="flex gap-2 px-4 pb-2" role="tablist">
        <Chip active={tab === "places"} onClick={() => setTab("places")}>
          Places
        </Chip>
        <Chip active={tab === "waypoints"} onClick={() => setTab("waypoints")}>
          Waypoints
        </Chip>
        <Chip active={tab === "log"} onClick={() => setTab("log")}>
          Hunt log
        </Chip>
      </div>
      <div className="px-4">
        {tab === "places" && <Places />}
        {tab === "waypoints" && <Waypoints />}
        {tab === "log" && <HuntLog />}
      </div>
    </div>
  );
}

function Places() {
  const { items, toggle } = useSaved();
  const { propertyById } = useData();
  return (
    <div className="space-y-3">
      {items.length === 0 && <Card className="p-4 text-sm text-muted">Nothing saved yet. Open a property and tap Save to keep it here with your notes.</Card>}
      {items.map((i) => {
        const p = propertyById.get(i.id);
        return (
          <Card key={i.id} className="p-4">
            <div className="flex items-start justify-between gap-3">
              <Link href={`/property/?id=${encodeURIComponent(i.id)}`} className="min-w-0">
                <div className="font-semibold">{i.name}</div>
                {p ? (
                  <div className="mt-1">
                    <StatusBadge status={p.access.status} small />
                  </div>
                ) : (
                  <div className="mt-1 text-xs text-warn">No longer in the current data.</div>
                )}
              </Link>
              <button type="button" onClick={() => toggle(i.id, i.name)} className="min-h-11 shrink-0 px-2 text-sm text-muted">
                Remove
              </button>
            </div>
            {i.note && <p className="mt-2 whitespace-pre-wrap text-sm text-muted">{i.note}</p>}
          </Card>
        );
      })}
    </div>
  );
}

function Waypoints() {
  const { waypoints, addWaypoint, removeWaypoint } = useFieldLog();
  const { loc, locate } = useLocation();
  const [kind, setKind] = useState<WaypointKind>("Sign");
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  const [saved, setSaved] = useState<string | null>(null);

  const drop = () => {
    if (loc.kind !== "ok") return;
    const ok = addWaypoint({
      id: newId("wp"),
      kind,
      name: name.trim(),
      note: note.trim(),
      lon: loc.lon,
      lat: loc.lat,
      accuracyM: loc.accuracyM,
      at: new Date().toISOString(),
    });
    setSaved(ok ? "Waypoint saved." : "Couldn't save: this browser's storage is full or blocked.");
    setName("");
    setNote("");
  };

  const exportGpx = () => {
    const blob = new Blob([toGpx(waypoints)], { type: "application/gpx+xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `deer-scout-waypoints-${ymdInTz(new Date())}.gpx`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  };

  return (
    <>
      <Card className="space-y-3 p-4">
        <div className="text-sm font-medium">Mark where you are</div>
        <div className="flex flex-wrap gap-2">
          {WAYPOINT_KINDS.map((k) => (
            <Chip key={k} active={kind === k} onClick={() => setKind(k)}>
              {k}
            </Chip>
          ))}
        </div>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name (optional)" className="min-h-11 w-full rounded-xl bg-surface-2 px-3 ring-1 ring-line placeholder:text-faint" />
        <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} placeholder="What you saw" className="w-full rounded-xl bg-surface-2 p-3 ring-1 ring-line placeholder:text-faint" />
        {loc.kind === "ok" ? (
          <p className="text-xs text-muted">
            GPS fix: {loc.lat.toFixed(5)}, {loc.lon.toFixed(5)} (±{Math.round(loc.accuracyM)} m)
          </p>
        ) : loc.kind === "error" ? (
          <Notice tone="bad">{loc.message}</Notice>
        ) : null}
        <div className="flex gap-2">
          <button type="button" onClick={locate} className="min-h-11 flex-1 rounded-xl bg-surface-2 font-medium ring-1 ring-line">
            {loc.kind === "locating" ? "Getting GPS…" : loc.kind === "ok" ? "Refresh GPS" : "Get GPS fix"}
          </button>
          <button type="button" onClick={drop} disabled={loc.kind !== "ok"} className="min-h-11 flex-1 rounded-xl bg-blaze font-semibold text-blaze-ink disabled:opacity-40">
            Save waypoint
          </button>
        </div>
        {saved && <p className="text-xs text-muted">{saved}</p>}
      </Card>

      <SectionTitle
        right={
          waypoints.length > 0 && (
            <button type="button" onClick={exportGpx} className="text-xs text-info">
              Export GPX
            </button>
          )
        }
      >
        {waypoints.length} waypoints
      </SectionTitle>
      <div className="space-y-2">
        {waypoints.map((w) => (
          <Card key={w.id} className="flex items-start justify-between gap-3 p-3">
            <div className="min-w-0 text-sm">
              <div className="font-medium">
                {w.kind}
                {w.name ? ` · ${w.name}` : ""}
              </div>
              <div className="text-xs text-faint">
                {new Date(w.at).toLocaleString()} · {w.lat.toFixed(5)}, {w.lon.toFixed(5)}
              </div>
              {w.note && <div className="mt-1 text-muted">{w.note}</div>}
              <a href={`https://maps.apple.com/?ll=${w.lat},${w.lon}&q=${encodeURIComponent(w.name || w.kind)}`} className="mt-1 inline-block text-xs text-info" target="_blank" rel="noreferrer">
                Open in Maps
              </a>
            </div>
            <button type="button" onClick={() => removeWaypoint(w.id)} className="min-h-11 shrink-0 px-2 text-sm text-muted">
              Delete
            </button>
          </Card>
        ))}
      </div>
      <p className="mt-3 text-xs text-faint">Waypoints also show on the Map tab. GPX opens in most mapping apps.</p>
    </>
  );
}

function HuntLog() {
  const { observations, addObservation, removeObservation } = useFieldLog();
  const { items } = useSaved();
  const [draft, setDraft] = useState<Omit<Observation, "id">>({
    date: ymdInTz(new Date()),
    window: "morning",
    placeId: null,
    placeName: "",
    deerSeen: 0,
    hours: 3,
    note: "",
  });
  const overall = sightingRate(observations);
  const byPlace = useMemo(() => {
    const m = new Map<string, Observation[]>();
    for (const o of observations) m.set(o.placeName || "Unnamed", [...(m.get(o.placeName || "Unnamed") ?? []), o]);
    return [...m.entries()].map(([name, list]) => ({ name, ...sightingRate(list) })).sort((a, b) => (b.perHour ?? 0) - (a.perHour ?? 0));
  }, [observations]);

  return (
    <>
      <Card className="space-y-3 p-4 text-sm">
        <div className="font-medium">Log a sit</div>
        <div className="grid grid-cols-2 gap-2">
          <label className="block">
            <span className="text-xs text-muted">Date</span>
            <input type="date" value={draft.date} onChange={(e) => setDraft({ ...draft, date: e.target.value })} className="mt-1 min-h-11 w-full rounded-xl bg-surface-2 px-3 ring-1 ring-line" />
          </label>
          <label className="block">
            <span className="text-xs text-muted">When</span>
            <select value={draft.window} onChange={(e) => setDraft({ ...draft, window: e.target.value as Observation["window"] })} className="mt-1 min-h-11 w-full rounded-xl bg-surface-2 px-3 ring-1 ring-line">
              <option value="morning">Morning</option>
              <option value="evening">Evening</option>
              <option value="allday">All day</option>
            </select>
          </label>
        </div>
        <label className="block">
          <span className="text-xs text-muted">Where</span>
          <input
            list="saved-places"
            value={draft.placeName}
            onChange={(e) => {
              const hit = items.find((i) => i.name === e.target.value);
              setDraft({ ...draft, placeName: e.target.value, placeId: hit?.id ?? null });
            }}
            placeholder="Property or spot"
            className="mt-1 min-h-11 w-full rounded-xl bg-surface-2 px-3 ring-1 ring-line placeholder:text-faint"
          />
          <datalist id="saved-places">
            {items.map((i) => (
              <option key={i.id} value={i.name} />
            ))}
          </datalist>
        </label>
        <div className="grid grid-cols-2 gap-2">
          <label className="block">
            <span className="text-xs text-muted">Deer seen</span>
            <input type="number" min={0} inputMode="numeric" value={draft.deerSeen} onChange={(e) => setDraft({ ...draft, deerSeen: Number(e.target.value) })} className="mt-1 min-h-11 w-full rounded-xl bg-surface-2 px-3 ring-1 ring-line" />
          </label>
          <label className="block">
            <span className="text-xs text-muted">Hours hunted</span>
            <input type="number" min={0} step={0.5} inputMode="decimal" value={draft.hours} onChange={(e) => setDraft({ ...draft, hours: Number(e.target.value) })} className="mt-1 min-h-11 w-full rounded-xl bg-surface-2 px-3 ring-1 ring-line" />
          </label>
        </div>
        <textarea value={draft.note} onChange={(e) => setDraft({ ...draft, note: e.target.value })} rows={2} placeholder="Wind, sign, what moved where" className="w-full rounded-xl bg-surface-2 p-3 ring-1 ring-line placeholder:text-faint" />
        <button
          type="button"
          onClick={() => {
            addObservation({ ...draft, id: newId("obs") });
            setDraft({ ...draft, deerSeen: 0, note: "" });
          }}
          className="min-h-11 w-full rounded-xl bg-blaze font-semibold text-blaze-ink"
        >
          Save sit
        </button>
      </Card>

      {observations.length > 0 && (
        <>
          <SectionTitle>Your numbers</SectionTitle>
          <Card className="p-4 text-sm">
            <p>
              {overall.sits} sits, {overall.hours} hours, {overall.deer} deer seen
              {overall.perHour !== null && ` · ${overall.perHour.toFixed(2)} deer per hour`}.
            </p>
            <ul className="mt-2 space-y-1 text-muted">
              {byPlace.map((p) => (
                <li key={p.name} className="flex justify-between">
                  <span className="truncate">{p.name}</span>
                  <span className="tabular">
                    {p.perHour === null ? "–" : p.perHour.toFixed(2)}/hr · {p.sits} sits
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-faint">Once you have enough sits, these will be used to tune the scores to what you actually see.</p>
          </Card>
          <div className="mt-3 space-y-2">
            {observations.map((o) => (
              <Card key={o.id} className="flex items-start justify-between gap-3 p-3 text-sm">
                <div>
                  <div className="font-medium">
                    {o.date} · {o.window} · {o.placeName || "Unnamed"}
                  </div>
                  <div className="text-muted">
                    {o.deerSeen} deer in {o.hours} h{o.note ? ` · ${o.note}` : ""}
                  </div>
                </div>
                <button type="button" onClick={() => removeObservation(o.id)} className="min-h-11 shrink-0 px-2 text-muted">
                  Delete
                </button>
              </Card>
            ))}
          </div>
        </>
      )}
    </>
  );
}
