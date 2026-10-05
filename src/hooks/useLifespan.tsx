import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { ActivityItem, Episode, LifespanDB } from "@/types/lifespan";
import { lifespanApi, newId } from "@/services/lifespanApi";
import { buildDemoDB } from "@/mock/demoEpisode";

type SaveState = "loading" | "saved" | "saving" | "error";

interface Ctx {
  db: LifespanDB;
  ready: boolean;
  saveState: SaveState;
  activeId: string;
  active: Episode | undefined;
  setActiveId: (id: string) => void;
  mutate: (fn: (db: LifespanDB) => LifespanDB, activity?: Pick<ActivityItem, "kind" | "text">) => void;
  reset: () => Promise<void>;
}

const LifespanContext = createContext<Ctx | null>(null);
const ACTIVE_KEY = "lifespan.active";

export function LifespanProvider({ children }: { children: ReactNode }) {
  const [db, setDb] = useState<LifespanDB>(() => buildDemoDB());
  const [ready, setReady] = useState(false);
  const [saveState, setSaveState] = useState<SaveState>("loading");
  const [activeId, setActiveIdState] = useState("ep-demo-delhi-dubai");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    lifespanApi.load().then((loaded) => {
      setDb(loaded);
      const stored = window.localStorage.getItem(ACTIVE_KEY);
      if (stored && loaded.episodes.some((e) => e.id === stored)) setActiveIdState(stored);
      else if (loaded.episodes[0]) setActiveIdState(loaded.episodes[0].id);
      setReady(true);
      setSaveState("saved");
    });
  }, []);

  const persist = useCallback((next: LifespanDB) => {
    setSaveState("saving");
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      lifespanApi.save(next).then(() => setSaveState("saved")).catch(() => setSaveState("error"));
    }, 400);
  }, []);

  const mutate = useCallback<Ctx["mutate"]>(
    (fn, activity) => {
      setDb((prev) => {
        let next = fn(prev);
        if (activity) {
          next = {
            ...next,
            activity: [{ id: newId("A"), at: new Date().toISOString(), episodeId: activeId, ...activity }, ...next.activity].slice(0, 50),
          };
        }
        persist(next);
        return next;
      });
    },
    [persist, activeId],
  );

  const setActiveId = useCallback((id: string) => {
    setActiveIdState(id);
    window.localStorage.setItem(ACTIVE_KEY, id);
  }, []);

  const reset = useCallback(async () => {
    const fresh = await lifespanApi.reset();
    setDb(fresh);
    setActiveId(fresh.episodes[0].id);
  }, [setActiveId]);

  const value = useMemo<Ctx>(
    () => ({ db, ready, saveState, activeId, active: db.episodes.find((e) => e.id === activeId), setActiveId, mutate, reset }),
    [db, ready, saveState, activeId, setActiveId, mutate, reset],
  );
  return <LifespanContext.Provider value={value}>{children}</LifespanContext.Provider>;
}

export function useLifespan() {
  const ctx = useContext(LifespanContext);
  if (!ctx) throw new Error("useLifespan must be used inside LifespanProvider");
  return ctx;
}

/** Convenience: records for the active episode. */
export function useActiveRecords() {
  const { db, activeId } = useLifespan();
  return useMemo(
    () => ({
      tasks: db.tasks.filter((x) => x.episodeId === activeId),
      facts: db.facts.filter((x) => x.episodeId === activeId),
      timeline: db.timeline.filter((x) => x.episodeId === activeId).sort((a, b) => a.year - b.year || a.id.localeCompare(b.id)),
      economics: db.economics.filter((x) => x.episodeId === activeId).sort((a, b) => a.year - b.year),
      chapters: db.chapters.filter((x) => x.episodeId === activeId).sort((a, b) => a.number - b.number),
      simulation: db.simulations.find((x) => x.episodeId === activeId),
    }),
    [db, activeId],
  );
}

export const touch = <T extends { updatedAt: string }>(r: T): T => ({ ...r, updatedAt: new Date().toISOString() });
