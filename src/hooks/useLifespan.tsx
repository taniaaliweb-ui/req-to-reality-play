import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { ActivityItem, Episode, LifespanDB } from "@/types/lifespan";
import { ApiError, BackendUnavailableError, lifespanApi, newId, type DataMode } from "@/services/lifespanApi";
import { buildDemoDB } from "@/mock/demoEpisode";

type SaveState = "loading" | "saved" | "saving" | "error";
type LoadState = "loading" | "ready" | "offline" | "error";

interface Ctx {
  db: LifespanDB;
  ready: boolean;
  mode: DataMode;
  loadState: LoadState;
  saveState: SaveState;
  saveError: string | null;
  activeId: string;
  active: Episode | undefined;
  setActiveId: (id: string) => void;
  mutate: (fn: (db: LifespanDB) => LifespanDB, activity?: Pick<ActivityItem, "kind" | "text">) => void;
  /** Wait until all pending edits have reached the data store. */
  syncNow: () => Promise<void>;
  reload: () => Promise<void>;
  reset: () => Promise<void>;
}

const LifespanContext = createContext<Ctx | null>(null);
const ACTIVE_KEY = "lifespan.active";
const EMPTY: LifespanDB = { version: 1, episodes: [], tasks: [], sources: [], facts: [], timeline: [], economics: [], simulations: [], chapters: [], activity: [], settings: { backendUrl: "", hermesUrl: "", showMockBanners: true, defaultRealism: 75, currencyDisplay: "local" } };

export function LifespanProvider({ children }: { children: ReactNode }) {
  const mode = lifespanApi.mode;
  // Local mode renders the demo immediately; backend mode renders nothing until the backend answers.
  const [db, setDb] = useState<LifespanDB>(() => (mode === "local" ? buildDemoDB() : EMPTY));
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [saveState, setSaveState] = useState<SaveState>("loading");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [activeId, setActiveIdState] = useState("ep-demo-delhi-dubai");

  const latest = useRef(db);
  const synced = useRef<LifespanDB | null>(null); // last state known to be persisted
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const chain = useRef<Promise<void>>(Promise.resolve());

  const loadedOnce = useRef(false);
  const load = useCallback(async () => {
    // A refresh after first load keeps pages mounted (no full-screen loading state).
    if (!loadedOnce.current) setLoadState("loading");
    try {
      const loaded = await lifespanApi.load();
      latest.current = loaded;
      synced.current = loaded;
      setDb(loaded);
      const stored = window.localStorage.getItem(ACTIVE_KEY);
      if (stored && loaded.episodes.some((e) => e.id === stored)) setActiveIdState(stored);
      else if (loaded.episodes[0]) setActiveIdState(loaded.episodes[0].id);
      loadedOnce.current = true;
      setLoadState("ready");
      setSaveState("saved");
    } catch (e) {
      console.error("[LifeSpan] load failed", e);
      setLoadState(e instanceof BackendUnavailableError ? "offline" : "error");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const flush = useCallback((): Promise<void> => {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
    chain.current = chain.current.then(async () => {
      const base = synced.current;
      const target = latest.current;
      if (!base || base === target) return;
      setSaveState("saving");
      try {
        await lifespanApi.sync(base, target);
        synced.current = target;
        setSaveError(null);
        setSaveState(latest.current === target ? "saved" : "saving");
      } catch (e) {
        console.error("[LifeSpan] save failed", e);
        setSaveState("error");
        setSaveError(e instanceof BackendUnavailableError ? "LifeSpan backend unavailable — changes not saved." : e instanceof ApiError ? e.message : "Save failed.");
      }
    });
    return chain.current;
  }, []);

  const mutate = useCallback<Ctx["mutate"]>(
    (fn, activity) => {
      let next = fn(latest.current);
      if (activity) {
        next = { ...next, activity: [{ id: newId("A"), at: new Date().toISOString(), episodeId: activeId, ...activity }, ...next.activity].slice(0, 50) };
      }
      latest.current = next;
      setDb(next);
      setSaveState("saving");
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => void flush(), 400);
    },
    [activeId, flush],
  );

  const setActiveId = useCallback((id: string) => {
    setActiveIdState(id);
    window.localStorage.setItem(ACTIVE_KEY, id);
  }, []);

  const reset = useCallback(async () => {
    const fresh = await lifespanApi.reset();
    latest.current = fresh;
    synced.current = fresh;
    setDb(fresh);
    setActiveId(fresh.episodes[0]?.id ?? "");
  }, [setActiveId]);

  // Push pending edits first so a refresh never discards unsaved changes.
  const refresh = useCallback(async () => {
    if (loadedOnce.current) await flush();
    await load();
  }, [flush, load]);

  const value = useMemo<Ctx>(
    () => ({ db, ready: loadState === "ready", mode, loadState, saveState, saveError, activeId, active: db.episodes.find((e) => e.id === activeId), setActiveId, mutate, syncNow: flush, reload: refresh, reset }),
    [db, mode, loadState, saveState, saveError, activeId, setActiveId, mutate, flush, refresh, reset],
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
