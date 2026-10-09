"use client";

import Link from "next/link";
import { useData } from "@/components/DataProvider";
import { useSaved } from "@/components/useSaved";
import { Card, Notice, PageHeader, StatusBadge } from "@/components/ui";

export default function SavedPage() {
  const { items, toggle } = useSaved();
  const { propertyById } = useData();

  return (
    <div>
      <PageHeader title="Saved" sub="Places and notes are stored only on this phone." />
      <div className="space-y-3 px-4">
        {items.length === 0 && (
          <Card className="p-4 text-sm text-muted">Nothing saved yet. Open a property and tap Save to keep it here with your notes.</Card>
        )}
        {items.map((i) => {
          const p = propertyById.get(i.id);
          return (
            <Card key={i.id} className="p-4">
              <div className="flex items-start justify-between gap-3">
                <Link href={`/property/?id=${encodeURIComponent(i.id)}`} className="min-w-0">
                  <div className="font-semibold">{i.name}</div>
                  {p && (
                    <div className="mt-1">
                      <StatusBadge status={p.access.status} small />
                    </div>
                  )}
                  {!p && <div className="mt-1 text-xs text-warn">No longer in the current data.</div>}
                </Link>
                <button type="button" onClick={() => toggle(i.id, i.name)} className="min-h-11 shrink-0 px-2 text-sm text-muted">
                  Remove
                </button>
              </div>
              {i.note && <p className="mt-2 whitespace-pre-wrap text-sm text-muted">{i.note}</p>}
            </Card>
          );
        })}
        <Notice tone="info">GPS waypoints, field observations and offline maps come in a later phase.</Notice>
      </div>
    </div>
  );
}
