"""Probability objects with a complete trace: base (with its class and sources) → modifiers → final → draw.

Classification (weakest component wins for the BASE; modifiers never upgrade a class):
  EMPIRICAL                — an observed statistic used directly (e.g. infant mortality rate at age 0)
  DERIVED_FROM_EMPIRICAL   — an observed statistic transformed by a documented method (method parameters
                             may be provisional priors; they are listed in prior_ids)
  ASSUMPTION_BASED         — an explicit user assumption from the snapshot
  PROVISIONAL_SYSTEM_PRIOR — a registry prior (not externally validated)
  DETERMINISTIC            — no randomness (locked events, scenario overrides, accounting rules)
"""
from __future__ import annotations

from dataclasses import dataclass, field

CLASSES = ["DETERMINISTIC", "EMPIRICAL", "DERIVED_FROM_EMPIRICAL", "ASSUMPTION_BASED", "PROVISIONAL_SYSTEM_PRIOR"]
_RANK = {c: i for i, c in enumerate(CLASSES)}


def weakest(*classes: str) -> str:
    return max(classes, key=lambda c: _RANK[c])


@dataclass
class Prob:
    base: float
    base_class: str
    base_label: str
    prior_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    assumption_ids: list[str] = field(default_factory=list)
    fact_ids: list[str] = field(default_factory=list)
    modifiers: list[dict] = field(default_factory=list)
    cap: float = 0.995  # rule:R-PROB-CAP
    lineage: dict | None = None  # full source → transformation → result chain (mortality, wages)

    def add(self, label: str, value: float, source: str = "trait") -> "Prob":
        if abs(value) > 1e-9:
            self.modifiers.append({"label": label, "kind": "add", "value": round(value, 6), "source": source})
        return self

    def mult(self, label: str, value: float, source: str = "control") -> "Prob":
        if abs(value - 1.0) > 1e-9:
            self.modifiers.append({"label": label, "kind": "mult", "value": round(value, 6), "source": source})
        return self

    def final(self) -> float:
        p = self.base + sum(x["value"] for x in self.modifiers if x["kind"] == "add")
        for x in self.modifiers:
            if x["kind"] == "mult":
                p *= x["value"]
        return max(0.0, min(self.cap, p))

    def sources(self) -> list[str]:
        return self.evidence_ids + self.assumption_ids + self.prior_ids + self.fact_ids


def fmt_pct(p: float) -> str:
    return f"{p * 100:.2f}%" if p < 0.1 else f"{p * 100:.1f}%"


def trace_text(pr: Prob, draw: float | None, occurred: bool, what: str) -> str:
    lines = [what, f"Base: {fmt_pct(pr.base)} — {pr.base_label} [{pr.base_class}]"]
    for x in pr.modifiers:
        lines.append(f"  {'+' if x['value'] >= 0 else ''}{fmt_pct(x['value'])} {x['label']}" if x["kind"] == "add" else f"  × {x['value']:.2f} {x['label']}")
    lines.append(f"Final probability: {fmt_pct(pr.final())}")
    if draw is not None:
        lines.append(f"Random draw: {draw:.6f} → {'occurs' if occurred else 'does not occur'} (occurs when draw < probability)")
    return "\n".join(lines)
