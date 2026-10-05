// Derives the Life Receipt deterministically from timeline + economic ledger.
import type { LifeReceipt, LifespanDB } from "@/types/lifespan";
import { householdIncome, netWorth, toReal } from "@/features/economics/calc";

export function deriveReceipt(db: LifespanDB, episodeId: string): LifeReceipt | null {
  const ep = db.episodes.find((e) => e.id === episodeId);
  if (!ep) return null;
  const events = db.timeline.filter((e) => e.episodeId === episodeId).sort((a, b) => a.year - b.year);
  const econ = db.economics.filter((e) => e.episodeId === episodeId);
  const death = events.find((e) => e.title.toLowerCase() === "death");
  const retire = events.find((e) => /retire/i.test(e.title));
  const baseIdx = econ[0]?.priceIndex ?? 100;
  const sum = (fn: (y: (typeof econ)[number]) => number) => econ.reduce((a, y) => a + fn(y), 0);
  const nw = econ.map(netWorth);
  const countries = Array.from(new Set(events.map((e) => e.location.split(",").pop()!.trim())));
  const end = nw[nw.length - 1] ?? 0;
  const endingClass = end > 8e6 ? "upper-middle" : end > 3e6 ? "middle" : ep.character.startingClass;
  const firstJob = events.find((e) => e.category === "Career");
  return {
    episodeId,
    born: ep.character.birthYear,
    died: death?.year ?? 0,
    age: death ? death.year - ep.character.birthYear : 0,
    countries,
    education: events.filter((e) => e.category === "Education").map((e) => e.title).pop() ?? "—",
    career: events.filter((e) => e.category === "Career").map((e) => e.title).join(" → "),
    lifetimeNominal: sum(householdIncome),
    lifetimeReal: sum((y) => toReal(householdIncome(y), y.priceIndex, baseIdx)),
    housingSpent: sum((y) => y.housing),
    educationSpent: sum((y) => y.education),
    healthcareSpent: sum((y) => y.healthcare),
    children: events.filter((e) => /child born/i.test(e.title)).length + " (simulated)",
    peakNetWorth: Math.max(0, ...nw),
    netWorthAtDeath: end,
    turningPoints: events.filter((e) => ["Migration", "External"].includes(e.category)).map((e) => `${e.year} — ${e.title}`),
    losses: events.filter((e) => e.category === "Negative outlier" || e.emotions.includes("grief")).map((e) => `${e.year} — ${e.title}`),
    achievements: events.filter((e) => e.emotions.includes("pride") || e.emotions.includes("accomplishment")).map((e) => `${e.year} — ${e.title}`),
    yearsWorking: (retire?.year ?? death?.year ?? 0) - (firstJob?.year ?? 0),
    yearsRetired: retire && death ? death.year - retire.year : 0,
    startingClass: ep.character.startingClass,
    endingClass,
    currency: econ[0]?.currency ?? "INR",
  };
}
