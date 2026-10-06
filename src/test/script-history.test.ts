import { describe, expect, it } from "vitest";
import { init, push, redo, undo } from "@/features/production/history";

describe("script undo/redo history", () => {
  it("undoes and redoes edits, and a new edit clears redo", () => {
    let h = init("a");
    h = push(h, "ab"); h = push(h, "abc");
    h = undo(h); expect(h.present).toBe("ab");
    h = undo(h); expect(h.present).toBe("a");
    expect(undo(h)).toBe(h);
    h = redo(h); expect(h.present).toBe("ab");
    h = push(h, "abX"); expect(h.future).toEqual([]);
    expect(undo(h).present).toBe("ab");
  });
  it("merges grouped typing into one step", () => {
    let h = push(init(""), "h");
    h = push(h, "he", true); h = push(h, "hel", true);
    expect(undo(h).present).toBe("");
  });
});
