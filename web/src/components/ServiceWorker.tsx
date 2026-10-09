"use client";

import { useEffect } from "react";

/** Registers /sw.js so the app shell and last-loaded data open without signal. */
export function ServiceWorker() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") return;
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js", { scope: "/", updateViaCache: "none" }).catch(() => {
      /* offline support is a bonus; the app works without it */
    });
  }, []);
  return null;
}
