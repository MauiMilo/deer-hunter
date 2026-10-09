"use client";

import { useCallback, useEffect, useState } from "react";
import { loadList, save } from "@/lib/storage";

export interface SavedPlace {
  id: string; // property or block id
  name: string;
  savedAt: string;
  note: string;
}

const KEY = "ds.saved.v1";
const EVENT = "ds-saved";

/** Favorites and notes, kept only on this phone. */
export function useSaved() {
  const [items, setItems] = useState<SavedPlace[]>([]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setItems(loadList<SavedPlace>(KEY));
    const onChange = () => setItems(loadList<SavedPlace>(KEY));
    window.addEventListener(EVENT, onChange);
    return () => window.removeEventListener(EVENT, onChange);
  }, []);

  const write = useCallback((next: SavedPlace[]) => {
    save(KEY, next);
    setItems(next);
    window.dispatchEvent(new Event(EVENT));
  }, []);

  const isSaved = useCallback((id: string) => items.some((i) => i.id === id), [items]);

  const toggle = useCallback(
    (id: string, name: string) => {
      const cur = loadList<SavedPlace>(KEY);
      write(cur.some((i) => i.id === id) ? cur.filter((i) => i.id !== id) : [...cur, { id, name, savedAt: new Date().toISOString(), note: "" }]);
    },
    [write],
  );

  const setNote = useCallback(
    (id: string, note: string) => {
      write(loadList<SavedPlace>(KEY).map((i) => (i.id === id ? { ...i, note } : i)));
    },
    [write],
  );

  return { items, isSaved, toggle, setNote };
}
