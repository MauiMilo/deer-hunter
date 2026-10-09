"use client";

import { useCallback, useState } from "react";

export type LocState =
  | { kind: "idle" }
  | { kind: "locating" }
  | { kind: "ok"; lon: number; lat: number; accuracyM: number; at: number }
  | { kind: "error"; message: string };

/** Phone GPS, only when asked for. The position is never saved or sent anywhere. */
export function useLocation() {
  const [loc, setLoc] = useState<LocState>({ kind: "idle" });

  const locate = useCallback(() => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setLoc({ kind: "error", message: "This browser can't share your location." });
      return;
    }
    setLoc({ kind: "locating" });
    navigator.geolocation.getCurrentPosition(
      (p) => setLoc({ kind: "ok", lon: p.coords.longitude, lat: p.coords.latitude, accuracyM: p.coords.accuracy, at: Date.now() }),
      (e) =>
        setLoc({
          kind: "error",
          message: e.code === e.PERMISSION_DENIED ? "Location permission was denied. You can allow it in Settings > Safari > Location." : "Couldn't get a GPS fix.",
        }),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 120000 },
    );
  }, []);

  return { loc, locate };
}
