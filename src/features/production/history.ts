// Local undo/redo history for text editing (no cloud). Pure state helpers + a React hook.
// Typing is grouped: consecutive edits within GROUP_MS form one undo step. History is kept per key in sessionStorage.
import { useCallback, useEffect, useRef, useState } from "react";

export interface History { past: string[]; present: string; future: string[] }
export const MAX_STEPS = 200;
const GROUP_MS = 800;

export const init = (v: string): History => ({ past: [], present: v, future: [] });
export function push(h: History, v: string, merge = false): History {
  if (v === h.present) return h;
  const past = merge ? h.past : [...h.past, h.present].slice(-MAX_STEPS);
  return { past, present: v, future: [] };
}
export function undo(h: History): History {
  if (!h.past.length) return h;
  return { past: h.past.slice(0, -1), present: h.past[h.past.length - 1]!, future: [h.present, ...h.future] };
}
export function redo(h: History): History {
  if (!h.future.length) return h;
  return { past: [...h.past, h.present], present: h.future[0]!, future: h.future.slice(1) };
}

export function useTextHistory(key: string, source: string | undefined) {
  const [h, setH] = useState<History>(init(""));
  const last = useRef(0);
  const sk = `lifespan:script-history:${key}`;
  useEffect(() => {
    if (source === undefined) return;
    try {
      const saved = sessionStorage.getItem(sk);
      const parsed = saved ? (JSON.parse(saved) as History & { base: string }) : null;
      setH(parsed && parsed.base === source ? parsed : init(source));
    } catch {
      setH(init(source));
    }
  }, [sk, source]);
  useEffect(() => {
    try { if (source !== undefined) sessionStorage.setItem(sk, JSON.stringify({ ...h, base: source })); } catch { /* storage full: history stays in memory */ }
  }, [h, sk, source]);
  const set = useCallback((v: string) => {
    const now = Date.now();
    setH((x) => push(x, v, now - last.current < GROUP_MS && x.past.length > 0));
    last.current = now;
  }, []);
  const reset = useCallback((v: string) => setH((x) => push(x, v)), []);
  return { value: h.present, set, reset, undo: () => { last.current = 0; setH(undo); }, redo: () => { last.current = 0; setH(redo); },
    canUndo: h.past.length > 0, canRedo: h.future.length > 0, steps: h.past.length };
}
