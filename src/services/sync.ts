// Turns two workspace states into ordered REST operations for the backend.
// Keeps pages unaware of HTTP: they mutate state, this module works out what changed.
import type { LifespanDB } from "@/types/lifespan";

export type SyncOp =
  | { kind: "put"; path: string; body: unknown }
  | { kind: "post"; path: string; body: unknown }
  | { kind: "delete"; path: string };

const SCOPED = [
  ["tasks", "research-tasks"],
  ["facts", "facts"],
  ["timeline", "timeline"],
  ["economics", "economic-years"],
  ["simulations", "simulations"],
  ["chapters", "story"],
] as const;

type WithId = { id: string };
const byId = <T extends WithId>(xs: T[]) => new Map(xs.map((x) => [x.id, x]));
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
const enc = encodeURIComponent;

function changed<T extends WithId>(prev: T[], next: T[]) {
  const p = byId(prev);
  const n = byId(next);
  return {
    upserts: next.filter((x) => !same(p.get(x.id), x)),
    deletes: prev.filter((x) => !n.has(x.id)),
  };
}

export function diffWorkspace(prev: LifespanDB, next: LifespanDB): SyncOp[] {
  const ops: SyncOp[] = [];
  if (prev === next) return ops;

  const src = changed(prev.sources, next.sources);
  src.upserts.forEach((s) => ops.push({ kind: "put", path: `/sources/${enc(s.id)}`, body: s }));

  const eps = changed(prev.episodes, next.episodes);
  eps.upserts.forEach((e) => ops.push({ kind: "put", path: `/episodes/${enc(e.id)}`, body: e }));
  const deletedEps = new Set(eps.deletes.map((e) => e.id));

  for (const [key, path] of SCOPED) {
    const d = changed<WithId & { episodeId: string }>(prev[key], next[key]);
    d.upserts.forEach((r) => ops.push({ kind: "put", path: `/episodes/${enc(r.episodeId)}/${path}/${enc(r.id)}`, body: r }));
    d.deletes
      .filter((r) => !deletedEps.has(r.episodeId)) // cascade handles these
      .forEach((r) => ops.push({ kind: "delete", path: `/episodes/${enc(r.episodeId)}/${path}/${enc(r.id)}` }));
  }

  src.deletes.forEach((s) => ops.push({ kind: "delete", path: `/sources/${enc(s.id)}` }));
  eps.deletes.forEach((e) => ops.push({ kind: "delete", path: `/episodes/${enc(e.id)}` }));

  const known = new Set(prev.activity.map((a) => a.id));
  next.activity.filter((a) => !known.has(a.id)).reverse().forEach((a) => ops.push({ kind: "post", path: "/activity", body: a }));

  if (!same(prev.settings, next.settings)) ops.push({ kind: "put", path: "/settings", body: next.settings });
  return ops;
}
