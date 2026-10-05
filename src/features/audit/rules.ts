// Deterministic audit rules. These actually run in Phase 1.
// Semantic audits (story/historical/bias) are placeholders for the future Audit Worker.
import type { AuditResult, LifespanDB } from "@/types/lifespan";
import { netWorth } from "@/features/economics/calc";

export function runAudits(db: LifespanDB, episodeId: string): AuditResult[] {
  const out: AuditResult[] = [];
  const facts = db.facts.filter((f) => f.episodeId === episodeId);
  const events = db.timeline.filter((e) => e.episodeId === episodeId).sort((a, b) => a.year - b.year);
  const econ = db.economics.filter((e) => e.episodeId === episodeId);
  const ep = db.episodes.find((e) => e.id === episodeId);
  const chapters = db.chapters.filter((c) => c.episodeId === episodeId);
  let n = 0;
  const push = (r: Omit<AuditResult, "id">) => out.push({ ...r, id: `AU-${++n}` });

  // Fact audit
  const unsourced = facts.filter((f) => (f.factType === "FACT" || f.factType === "ESTIMATE") && !f.sourceId);
  push(unsourced.length
    ? { category: "Fact", outcome: "FAIL", title: `${unsourced.length} fact/estimate record(s) have no source`, explanation: "Every FACT or ESTIMATE must reference a Source Registry entry.", refs: unsourced.map((f) => f.id), automated: true }
    : { category: "Fact", outcome: "PASS", title: "All facts and estimates have sources", explanation: "Checked source_id on every FACT/ESTIMATE.", refs: [], automated: true });
  const weak = facts.filter((f) => f.sourceId && db.sources.find((s) => s.id === f.sourceId)?.reliability === "Weak");
  if (weak.length) push({ category: "Fact", outcome: "WARNING", title: `${weak.length} record(s) rely on a Weak source`, explanation: "Corroborate with a stronger source.", refs: weak.map((f) => f.id), automated: true });

  // Timeline audit
  const born = ep?.character.birthYear ?? 0;
  const badAge = events.filter((e) => e.age !== e.year - born);
  push(badAge.length
    ? { category: "Timeline", outcome: "FAIL", title: "Age does not match birth year", explanation: "age must equal year − birth year.", refs: badAge.map((e) => e.id), automated: true }
    : { category: "Timeline", outcome: "PASS", title: "Ages consistent with birth year", explanation: "Checked all events.", refs: [], automated: true });
  const death = events.find((e) => e.title.toLowerCase() === "death");
  const afterDeath = death ? events.filter((e) => e.year > death.year) : [];
  if (afterDeath.length) push({ category: "Timeline", outcome: "FAIL", title: "Events occur after death", explanation: "No life events may follow death.", refs: afterDeath.map((e) => e.id), automated: true });
  const firstJob = events.find((e) => e.category === "Career");
  const school = events.find((e) => e.title.toLowerCase().includes("secondary"));
  if (firstJob && school && firstJob.year < school.year - 2)
    push({ category: "Timeline", outcome: "WARNING", title: "Career starts well before schooling ends", explanation: "Possible but should be justified.", refs: [firstJob.id, school.id], automated: true });

  // Economic audit
  const neg = econ.filter((y) => y.savings < 0);
  const purchase = events.find((e) => e.category === "Finance" && /purchase/i.test(e.title));
  if (purchase) {
    const prior = econ.find((y) => y.year === purchase.year - 1);
    const ok = prior ? prior.savings + prior.investments > 0 : false;
    push(ok
      ? { category: "Economic", outcome: "WARNING", title: "Property purchase: verify down payment covered", explanation: `Prior-year liquid assets exist; confirm ratio vs. price (${purchase.financialEffect}).`, refs: [purchase.id], automated: true }
      : { category: "Economic", outcome: "FAIL", title: "Property purchased with no prior savings", explanation: "House purchased despite insufficient assets.", refs: [purchase.id], automated: true });
  }
  push(neg.length
    ? { category: "Economic", outcome: "FAIL", title: "Negative savings detected", explanation: "Savings below zero without debt.", refs: neg.map((y) => y.id), automated: true }
    : { category: "Economic", outcome: "PASS", title: "No negative savings", explanation: `Checked ${econ.length} years. Peak net worth computed deterministically.`, refs: [], automated: true });
  if (econ.length && netWorth(econ[econ.length - 1]) < 0)
    push({ category: "Economic", outcome: "WARNING", title: "Dies with negative net worth", explanation: "Plausible but should be narratively addressed.", refs: [], automated: true });

  // Geographic
  const mismatch = events.filter((e) => e.category === "Migration" && /moves to (\w+)/i.test(e.title) && !e.location.toLowerCase().includes(e.title.match(/moves to (\w+)/i)![1].toLowerCase()));
  push(mismatch.length
    ? { category: "Geographic", outcome: "FAIL", title: "Migration destination ≠ event location", explanation: "Location field contradicts the title.", refs: mismatch.map((e) => e.id), automated: true }
    : { category: "Geographic", outcome: "PASS", title: "Migration locations consistent", explanation: "Checked relocation events.", refs: [], automated: true });

  // Assumptions
  const unresolved = facts.filter((f) => f.factType === "ASSUMPTION" && f.status !== "verified");
  if (unresolved.length) push({ category: "Assumption", outcome: "WARNING", title: `${unresolved.length} unsupported assumption(s)`, explanation: "Assumptions must be sourced, justified or removed.", refs: unresolved.map((f) => f.id), automated: true });

  // Story: chapters referencing missing events
  const ids = new Set(events.map((e) => e.id));
  const dangling = chapters.filter((c) => c.timelineEventIds.some((id) => !ids.has(id)));
  push(dangling.length
    ? { category: "Story", outcome: "FAIL", title: "Chapters reference deleted timeline events", explanation: "Story contradicts the timeline.", refs: dangling.map((c) => c.id), automated: true }
    : { category: "Story", outcome: "PASS", title: "Chapter references resolve", explanation: "Semantic narrative-vs-timeline check requires the Audit Worker.", refs: [], automated: true });

  // Not-yet-automated
  push({ category: "Historical", outcome: "WARNING", title: "Historical consistency not yet verified", explanation: "Requires Audit Worker + dated event datasets (Phase 2+).", refs: [], automated: false });
  const cultural = facts.filter((f) => f.category === "Social environment" && f.factType === "ASSUMPTION");
  push({ category: "Bias", outcome: cultural.length ? "WARNING" : "PASS", title: cultural.length ? "Cultural assumptions may encode stereotypes" : "No flagged cultural assumptions", explanation: "Social-environment assumptions require sourced justification. Full bias review needs human + Audit Worker.", refs: cultural.map((f) => f.id), automated: true });

  return out;
}
