"use client";

import { evaluateSpot, FIT_TEXT, type SpotEval } from "@/lib/spots";
import type { Spot, WindRoseCell } from "@/lib/types";
import { compass, type Fit } from "@/lib/wind";

const FIT_CLASS: Record<Fit, string> = {
  good: "bg-ok/15 text-ok ring-ok/40",
  marginal: "bg-warn/15 text-warn ring-warn/40",
  bad: "bg-bad/15 text-bad ring-bad/40",
};

export function FitBadge({ fit }: { fit: Fit | null }) {
  if (!fit) return null;
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${FIT_CLASS[fit]}`}>{FIT_TEXT[fit]}</span>;
}

function arcText([a, b]: [number, number]): string {
  return `${compass(a, 8)}–${compass(b, 8)}`;
}

export function goodWindText(spot: Spot): string {
  return spot.good_winds_from.map(arcText).join(" or ");
}

export function SpotCard({
  spot,
  windFromDeg,
  rank,
  selected,
  onShow,
}: {
  spot: Spot;
  windFromDeg: number | null;
  rank?: number;
  selected?: boolean;
  onShow?: () => void;
}) {
  const ev: SpotEval = evaluateSpot(spot, windFromDeg);
  const kind = spot.kind === "saddle" ? "Saddle" : "Bench";
  const a = spot.approach;
  return (
    <div className={`rounded-2xl bg-surface p-4 ring-1 ${selected ? "ring-blaze" : "ring-line"}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs text-faint">{rank ? `Spot ${rank}` : "Spot"}</div>
          <div className="text-[17px] font-semibold">
            {kind} · {spot.elevation_ft.toLocaleString()} ft
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <FitBadge fit={ev.windFit} />
            <span className="text-xs text-muted">Best winds from {goodWindText(spot)}</span>
          </div>
        </div>
        <div className="text-right">
          <div className="tabular text-2xl font-semibold">{Math.round(windFromDeg === null ? spot.score : ev.dayScore)}</div>
          <div className="text-[11px] uppercase tracking-wide text-faint">{windFromDeg === null ? "Spot" : "Today"}</div>
        </div>
      </div>
      {a && (
        <p className="mt-3 text-sm">
          {a.road_name ? `From ${a.road_name}` : "From the nearest mapped road"}, walk about {(a.distance_m / 1609.34).toFixed(1)} mi heading{" "}
          {compass(ev.approachBearing ?? 0)}. <span className="text-faint">Check that the road is open to trucks.</span>
          {ev.approachFit && ev.approachFit !== "marginal" && (
            <span className={ev.approachFit === "good" ? "text-ok" : "text-bad"}>
              {" "}
              {ev.approachFit === "good" ? "Wind in your face on the way in." : "Wind at your back on the way in: circle around."}
            </span>
          )}
        </p>
      )}
      <ul className="mt-2 space-y-0.5 text-sm text-muted">
        {ev.notes
          .filter((n) => !n.startsWith("Walking in") && !n.startsWith("The walk in"))
          .map((n) => (
            <li key={n}>{n}</li>
          ))}
        {spot.reasons
          .filter((r) => r !== spot.lidar?.detail)
          .map((r) => (
            <li key={r}>{r}</li>
          ))}
      </ul>
      <LidarLine spot={spot} />
      <div className="mt-2 flex items-center justify-between text-xs text-faint">
        <span>Confidence: {spot.confidence} · a terrain candidate, not confirmed sign</span>
        <a
          href={`https://maps.apple.com/?ll=${spot.point[1]},${spot.point[0]}&q=${encodeURIComponent(kind)}`}
          className="text-info"
          target="_blank"
          rel="noreferrer"
        >
          Open in Maps
        </a>
      </div>
      {onShow && (
        <button type="button" onClick={onShow} className="mt-3 min-h-11 w-full rounded-xl bg-surface-2 text-sm font-medium ring-1 ring-line">
          Close-up on map
        </button>
      )}
    </div>
  );
}

const LIDAR_TEXT: Record<string, { label: string; cls: string }> = {
  confirmed: { label: "Checked at 1 m LiDAR", cls: "text-ok" },
  moved: { label: "Adjusted with 1 m LiDAR", cls: "text-ok" },
  not_confirmed: { label: "Not confirmed by 1 m LiDAR", cls: "text-warn" },
  not_checked: { label: "Not checked at 1 m", cls: "text-faint" },
};

/** What the 1 m lidar re-check found, in one line. */
export function LidarLine({ spot }: { spot: Spot }) {
  const l = spot.lidar;
  if (!l) return null;
  const t = LIDAR_TEXT[l.verdict] ?? LIDAR_TEXT.not_checked;
  return (
    <p className="mt-2 text-sm">
      <span className={`font-medium ${t.cls}`}>{t.label}:</span> <span className="text-muted">{l.detail}</span>
    </p>
  );
}

const SECTOR_ANGLES = [0, 45, 90, 135, 180, 225, 270, 315];

/** Eight-petal wind rose: petal length = share of hours the wind blew FROM that direction. */
export function WindRose({ cell, size = 150 }: { cell: WindRoseCell; size?: number }) {
  const max = Math.max(0.01, ...cell.sector_share);
  const c = size / 2;
  const R = c - 18;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-label="Wind rose" role="img">
      <circle cx={c} cy={c} r={R} fill="none" stroke="currentColor" strokeOpacity="0.15" />
      <circle cx={c} cy={c} r={R / 2} fill="none" stroke="currentColor" strokeOpacity="0.1" />
      {cell.sector_share.map((v, i) => {
        const len = (v / max) * R;
        const a1 = ((SECTOR_ANGLES[i] - 20) * Math.PI) / 180;
        const a2 = ((SECTOR_ANGLES[i] + 20) * Math.PI) / 180;
        const p = (a: number, r: number) => `${c + r * Math.sin(a)},${c - r * Math.cos(a)}`;
        return <polygon key={i} points={`${c},${c} ${p(a1, len)} ${p(a2, len)}`} fill="var(--blaze)" fillOpacity={0.35 + 0.6 * (v / max)} />;
      })}
      {["N", "E", "S", "W"].map((t, i) => {
        const a = (i * 90 * Math.PI) / 180;
        return (
          <text key={t} x={c + (R + 10) * Math.sin(a)} y={c - (R + 10) * Math.cos(a) + 4} textAnchor="middle" fontSize="11" fill="currentColor" opacity="0.7">
            {t}
          </text>
        );
      })}
    </svg>
  );
}
