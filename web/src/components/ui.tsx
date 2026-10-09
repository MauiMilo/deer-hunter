"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import type { AccessStatus, Factor, SourceRef } from "@/lib/types";
import { compass } from "@/lib/wind";

export const STATUS_TEXT: Record<AccessStatus, string> = {
  verified: "Hunting allowed",
  unknown: "Permission not verified",
  prohibited: "No public access",
};

const STATUS_CLASS: Record<AccessStatus, string> = {
  verified: "bg-ok/15 text-ok ring-ok/40",
  unknown: "bg-warn/15 text-warn ring-warn/40",
  prohibited: "bg-bad/15 text-bad ring-bad/40",
};

export function StatusBadge({ status, small }: { status: AccessStatus; small?: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full ring-1 font-medium ${STATUS_CLASS[status]} ${
        small ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-sm"
      }`}
    >
      <span aria-hidden className="text-[0.7em]">{status === "verified" ? "●" : status === "unknown" ? "◐" : "○"}</span>
      {STATUS_TEXT[status]}
    </span>
  );
}

export function Chip({ active, onClick, children, label }: { active?: boolean; onClick?: () => void; children: ReactNode; label?: string }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      aria-label={label}
      onClick={onClick}
      className={`min-h-11 shrink-0 rounded-xl px-3.5 text-[15px] font-medium transition-colors ${
        active ? "bg-blaze text-blaze-ink" : "bg-surface-2 text-text ring-1 ring-line"
      }`}
    >
      {children}
    </button>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-2xl bg-surface ring-1 ring-line ${className}`}>{children}</div>;
}

export function SectionTitle({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-2 mt-6 flex items-end justify-between px-1">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-muted">{children}</h2>
      {right}
    </div>
  );
}

/** Arrow pointing the way the wind blows (where your scent goes), labeled with where it comes from. */
export function WindArrow({ fromDeg, mph, size = 28 }: { fromDeg: number | null; mph?: number; size?: number }) {
  if (fromDeg === null) {
    return <span className="text-sm text-muted">Variable</span>;
  }
  const to = (fromDeg + 180) % 360;
  return (
    <span className="inline-flex items-center gap-1.5">
      <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden style={{ transform: `rotate(${to}deg)` }}>
        <circle cx="12" cy="12" r="11" fill="none" stroke="currentColor" strokeOpacity="0.25" />
        <path d="M12 3 L17 13 L13 11.5 L13 21 L11 21 L11 11.5 L7 13 Z" fill="currentColor" />
      </svg>
      <span className="tabular text-sm">
        {compass(fromDeg)}
        {mph !== undefined && <span className="text-muted"> {Math.round(mph)} mph</span>}
      </span>
    </span>
  );
}

export function ScorePill({ value, provisional, label }: { value: number | null; provisional?: boolean; label?: string }) {
  if (value === null) return <span className="text-sm text-muted">No score</span>;
  const tone = value >= 70 ? "text-ok" : value >= 45 ? "text-text" : "text-muted";
  return (
    <span className="inline-flex flex-col items-end leading-none" title={provisional ? "Provisional: built on incomplete data" : undefined}>
      <span className={`tabular text-2xl font-semibold ${tone}`}>
        {Math.round(value)}
        {provisional && <span className="align-super text-xs text-warn">*</span>}
      </span>
      {label && <span className="mt-1 text-[11px] uppercase tracking-wide text-faint">{label}</span>}
    </span>
  );
}

export function Bar({ value, tone = "bg-blaze" }: { value: number | null; tone?: string }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-surface-2">
      {value !== null && <div className={`h-full rounded-full ${tone}`} style={{ width: `${Math.max(2, Math.min(100, value))}%` }} />}
    </div>
  );
}

export function FactorList({ factors }: { factors: Factor[] }) {
  return (
    <ul className="divide-y divide-line">
      {factors.map((f) => (
        <li key={f.key} className="py-3">
          <div className="flex items-baseline justify-between gap-3">
            <span className="font-medium">{f.label}</span>
            <span className="tabular text-sm text-muted">
              {f.value === null ? "not yet" : Math.round(f.value)} · weight {Math.round(f.weight * 100)}%
            </span>
          </div>
          <div className="mt-2">
            <Bar value={f.value} tone={f.value === null ? "bg-surface-2" : "bg-blaze"} />
          </div>
          <div className="mt-1.5 flex flex-wrap gap-x-3 text-xs text-faint">
            <span>{f.basis_label}</span>
            {f.value !== null && <span>Confidence: {f.confidence}</span>}
          </div>
          <ul className="mt-1 space-y-0.5 text-sm text-muted">
            {f.evidence.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </li>
      ))}
    </ul>
  );
}

export function Sources({ sources }: { sources: SourceRef[] }) {
  return (
    <ul className="space-y-1.5 text-sm">
      {sources.map((s) => (
        <li key={`${s.id}-${s.url}`}>
          {s.url ? (
            <a href={s.url} target="_blank" rel="noreferrer" className="text-info underline decoration-info/40 underline-offset-2">
              {s.title}
            </a>
          ) : (
            <span>{s.title}</span>
          )}
          <span className="text-faint">
            {s.publisher ? ` · ${s.publisher}` : ""}
            {s.source_date ? ` · dated ${s.source_date}` : ""}
            {s.retrieved ? ` · checked ${s.retrieved}` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}

const TABS = [
  { href: "/", label: "Hunt", icon: "M12 2 L15 9 L22 9 L16.5 13.5 L18.5 21 L12 16.5 L5.5 21 L7.5 13.5 L2 9 L9 9 Z" },
  { href: "/map/", label: "Map", icon: "M3 6 L9 3 L15 6 L21 3 L21 18 L15 21 L9 18 L3 21 Z M9 3 L9 18 M15 6 L15 21" },
  { href: "/saved/", label: "Saved", icon: "M6 3 H18 V21 L12 16 L6 21 Z" },
  { href: "/settings/", label: "Settings", icon: "M12 8 A4 4 0 1 0 12 16 A4 4 0 1 0 12 8 M12 2 V5 M12 19 V22 M2 12 H5 M19 12 H22 M4.9 4.9 L7 7 M17 17 L19.1 19.1 M4.9 19.1 L7 17 M17 7 L19.1 4.9" },
];

export function TabBar() {
  const path = usePathname() || "/";
  const norm = path.endsWith("/") ? path : `${path}/`;
  return (
    <nav className="pb-safe fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface/95 backdrop-blur">
      <ul className="mx-auto grid max-w-xl grid-cols-4">
        {TABS.map((t) => {
          const active = t.href === "/" ? norm === "/" || norm.startsWith("/property") : norm.startsWith(t.href);
          return (
            <li key={t.href}>
              <Link
                href={t.href}
                className={`flex min-h-14 flex-col items-center justify-center gap-0.5 text-[11px] font-medium ${active ? "text-blaze" : "text-muted"}`}
              >
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" aria-hidden>
                  <path d={t.icon} />
                </svg>
                {t.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

export function PageHeader({ title, sub, right }: { title: string; sub?: ReactNode; right?: ReactNode }) {
  return (
    <header className="pt-safe px-4 pb-2">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-[26px] font-bold leading-tight tracking-tight">{title}</h1>
          {sub && <p className="mt-0.5 text-sm text-muted">{sub}</p>}
        </div>
        {right}
      </div>
    </header>
  );
}

export function Notice({ tone = "warn", children }: { tone?: "warn" | "bad" | "info"; children: ReactNode }) {
  const cls = tone === "bad" ? "bg-bad/10 ring-bad/30" : tone === "info" ? "bg-info/10 ring-info/30" : "bg-warn/10 ring-warn/30";
  return <div className={`rounded-xl px-3.5 py-3 text-sm ring-1 ${cls}`}>{children}</div>;
}
