"use client";

import { useEffect, useRef, useState } from "react";
import { deleteArea, estimate, listAreas, MAX_TILES, offlineSupported, saveArea, type BBox, type SavedArea } from "@/lib/offline";

/** Pick the most detail that fits under the tile limit: start at zoom 10, drop the wide views if needed. */
function plan(bbox: BBox): { minZoom: number; tiles: number; mb: number } | null {
  for (const minZoom of [10, 12, 13]) {
    const e = estimate(bbox, minZoom);
    if (e.tiles <= MAX_TILES) return { minZoom, ...e };
  }
  return null;
}

export function OfflineSave({ name, bbox, className = "" }: { name: string; bbox: BBox; className?: string }) {
  const [areas, setAreas] = useState<SavedArea[]>([]);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [supported, setSupported] = useState(true);
  const abort = useRef<AbortController | null>(null);
  useEffect(() => {
    // Browser storage only exists on the phone, so read it after the page loads.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setAreas(listAreas());
    setSupported(offlineSupported());
  }, []);

  const existing = areas.find((a) => a.name === name);
  const p = plan(bbox);

  const start = async () => {
    if (!p) return;
    setMsg(null);
    abort.current = new AbortController();
    setProgress({ done: 0, total: p.tiles });
    try {
      const a = await saveArea(name, bbox, { minZoom: p.minZoom, signal: abort.current.signal, onProgress: (done, total) => setProgress({ done, total }) });
      setMsg(a.failed ? `Saved, but ${a.failed} of ${a.tiles + a.failed} tiles didn't download. Try again with better signal.` : "Saved. This map now works with no signal.");
    } catch (e) {
      setMsg((e as Error).name === "AbortError" ? "Stopped. Tiles saved so far are kept." : (e as Error).message);
    } finally {
      setProgress(null);
      setAreas(listAreas());
    }
  };

  if (!supported) return null;
  return (
    <div className={`rounded-xl bg-surface-2 p-3 text-sm ring-1 ring-line ${className}`}>
      {progress ? (
        <div>
          <div className="flex items-center justify-between">
            <span>
              Saving map… {progress.done.toLocaleString()} of {progress.total.toLocaleString()}
            </span>
            <button type="button" className="text-info" onClick={() => abort.current?.abort()}>
              Stop
            </button>
          </div>
          <div className="mt-2 h-2 overflow-hidden rounded bg-line">
            <div className="h-full bg-blaze" style={{ width: `${(100 * progress.done) / Math.max(1, progress.total)}%` }} />
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="font-medium">{existing ? "Saved for offline" : "Use this map with no signal"}</div>
            <div className="text-xs text-muted">
              {existing
                ? `Saved ${new Date(existing.savedAt).toLocaleDateString()} · topo, satellite and LiDAR relief`
                : p
                  ? `Topo, satellite and LiDAR relief · about ${Math.max(1, Math.round(p.mb))} MB`
                  : "This area is too big to save at once. Zoom in or open one block."}
            </div>
          </div>
          {p && (
            <div className="flex shrink-0 gap-2">
              {existing && (
                <button
                  type="button"
                  className="min-h-10 rounded-lg px-2 text-muted"
                  onClick={async () => {
                    await deleteArea(existing.id);
                    setAreas(listAreas());
                    setMsg("Removed from the phone.");
                  }}
                >
                  Remove
                </button>
              )}
              <button type="button" onClick={start} className="min-h-10 rounded-lg bg-blaze px-3 font-semibold text-blaze-ink">
                {existing ? "Update map" : "Save map"}
              </button>
            </div>
          )}
        </div>
      )}
      {msg && <p className="mt-2 text-xs text-muted">{msg}</p>}
    </div>
  );
}

export function OfflineAreas() {
  const [areas, setAreas] = useState<SavedArea[]>([]);
  const [use, setUse] = useState<{ usedMb: number; quotaMb: number } | null>(null);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setAreas(listAreas());
    import("@/lib/offline").then((m) => m.storageUse()).then(setUse);
  }, []);
  return (
    <div className="space-y-3 text-sm">
      {areas.length === 0 ? (
        <p className="text-muted">
          No maps saved yet. Open a property or block and tap <strong>Save map</strong> under its map, or save the view on the Map tab, before you lose
          signal.
        </p>
      ) : (
        <ul className="space-y-2">
          {areas.map((a) => (
            <li key={a.id} className="flex items-center justify-between gap-3">
              <span className="min-w-0">
                <span className="block truncate">{a.name}</span>
                <span className="block text-xs text-faint">
                  {new Date(a.savedAt).toLocaleDateString()} · {a.tiles.toLocaleString()} tiles
                  {a.failed ? ` · ${a.failed} missing` : ""}
                </span>
              </span>
              <button
                type="button"
                className="min-h-10 shrink-0 rounded-lg px-2 text-bad"
                onClick={async () => {
                  await deleteArea(a.id);
                  setAreas(listAreas());
                }}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      {use && (
        <p className="text-xs text-faint">
          This app is using about {use.usedMb.toLocaleString()} MB on the phone{use.quotaMb ? ` (room for about ${use.quotaMb.toLocaleString()} MB)` : ""}. Maps you
          just look at are also kept for a while, up to a few thousand tiles.
        </p>
      )}
      <p className="text-xs text-faint">
        On iPhone, add the app to your Home Screen and save maps from there. Safari may clear saved data for websites you haven&apos;t opened in about a week.
      </p>
    </div>
  );
}
