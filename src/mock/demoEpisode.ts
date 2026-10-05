// PROTOTYPE / MOCK DATA. Every number in this file is illustrative and unverified.
// Nothing here is research. It exists so the workflow can be demonstrated.
import type {
  Character,
  EconomicYear,
  Episode,
  Fact,
  LifespanDB,
  ResearchTask,
  SimulationRun,
  Source,
  StoryChapter,
  TimelineEvent,
} from "@/types/lifespan";
import { defaultControls, defaultTraits } from "@/lib/defaults";

const T = "2026-09-28T10:00:00.000Z";
const EP = "ep-demo-delhi-dubai";
const base = (id: string) => ({ id, createdAt: T, updatedAt: T });

export function buildDemoDB(): LifespanDB {
  const character: Character = {
    ...base("ch-demo"),
    name: "Character LS-0001 (\"Rajesh\")",
    country: "India",
    region: "Delhi (East)",
    birthYear: 1970,
    gender: "male",
    settlement: "urban",
    startingClass: "lower-middle",
    family: {
      guardians: 2,
      siblings: 2,
      parentalIncomeClass: "lower-middle",
      parentalEducation: "Father: secondary; Mother: primary",
      housing: "Rented two-room flat",
    },
    traits: { ...defaultTraits(), ambition: 78, resilience: 74, riskTolerance: 52, migrationWillingness: 66 },
    controls: { ...defaultControls(), realism: 80, randomness: 45 },
  };

  const episode: Episode = {
    ...base(EP),
    title: "From Delhi to Dubai — A Life Across Two Economies",
    stage: "audit",
    character,
    isMock: true,
  };

  const sources: Source[] = [
    { ...base("SRC-001"), title: "[MOCK] Household consumption survey, round (placeholder)", organization: "National statistical agency (placeholder)", url: "https://example.org/mock/consumption", publicationDate: "1996", accessedDate: "2026-09-20", geoCoverage: "India", timeCoverage: "1987–1994", type: "statistical agency", reliability: "Primary", notes: "Placeholder record. Replace with real citation during research." },
    { ...base("SRC-002"), title: "[MOCK] World Development Indicators extract", organization: "World Bank", url: "https://example.org/mock/wdi", publicationDate: "2024", accessedDate: "2026-09-20", geoCoverage: "India, UAE", timeCoverage: "1970–2023", type: "World Bank", reliability: "Strong", notes: "Placeholder. Inflation & GDP series to be pulled by deterministic loader." },
    { ...base("SRC-003"), title: "[MOCK] Gulf labour migration overview", organization: "UN agency (placeholder)", url: "https://example.org/mock/migration", publicationDate: "2008", accessedDate: "2026-09-21", geoCoverage: "GCC", timeCoverage: "1995–2007", type: "UN", reliability: "Strong", notes: "Placeholder." },
    { ...base("SRC-004"), title: "[MOCK] Delhi rental market reporting", organization: "Newspaper archive (placeholder)", url: "https://example.org/mock/rent", publicationDate: "1998", accessedDate: "2026-09-21", geoCoverage: "Delhi", timeCoverage: "1990–1998", type: "newspaper", reliability: "Moderate", notes: "Anecdotal. Use only for color, not core values." },
    { ...base("SRC-005"), title: "[MOCK] Academic study of engineering graduates' wages", organization: "University (placeholder)", url: "https://example.org/mock/wages", publicationDate: "2002", accessedDate: "2026-09-22", geoCoverage: "India (urban)", timeCoverage: "1988–2000", type: "academic", reliability: "Strong", notes: "Placeholder." },
    { ...base("SRC-006"), title: "[MOCK] Dubai property price index", organization: "Industry body (placeholder)", url: "https://example.org/mock/dxb-property", publicationDate: "2012", accessedDate: "2026-09-22", geoCoverage: "Dubai", timeCoverage: "2003–2012", type: "industry", reliability: "Weak", notes: "Industry-published; potential bias." },
  ];

  const f = (id: string, p: Partial<Fact> & Pick<Fact, "metric" | "value" | "unit" | "factType" | "category">): Fact => ({
    ...base(id), episodeId: EP, country: "India", region: "Delhi", yearStart: 1990, yearEnd: 1990, sourceId: null, confidence: "medium", notes: "Mock value — not verified.", status: "unverified", ...p,
  });

  const facts: Fact[] = [
    f("F-001", { category: "Economy", metric: "Consumer price inflation (annual)", value: "~10", unit: "%", yearStart: 1991, yearEnd: 1991, sourceId: "SRC-002", factType: "FACT", confidence: "high", status: "verified", region: "National" }),
    f("F-002", { category: "Employment", metric: "Average urban monthly wage, clerical", value: "1,800", unit: "INR/month", yearStart: 1990, yearEnd: 1990, sourceId: "SRC-001", factType: "FACT", confidence: "medium" }),
    f("F-003", { category: "Employment", metric: "Character starting salary", value: "2,400", unit: "INR/month", factType: "DERIVED", derivedFrom: "Diploma + junior technician + F-005 wage distribution", confidence: "medium" }),
    f("F-004", { category: "Housing", metric: "Two-room rent, East Delhi", value: "900", unit: "INR/month", yearStart: 1992, yearEnd: 1992, sourceId: "SRC-004", factType: "ESTIMATE", confidence: "low" }),
    f("F-005", { category: "Employment", metric: "Engineering diploma wage premium", value: "+30", unit: "%", yearStart: 1988, yearEnd: 1995, sourceId: "SRC-005", factType: "FACT", confidence: "medium" }),
    f("F-006", { category: "Demographics", metric: "Median male age at first marriage (urban)", value: "26", unit: "years", yearStart: 1991, yearEnd: 1991, sourceId: "SRC-002", factType: "FACT", confidence: "medium", region: "National" }),
    f("F-007", { category: "Social environment", metric: "Family expects eldest son to support parents", value: "Yes", unit: "—", factType: "ASSUMPTION", confidence: "low", notes: "Cultural assumption. Requires sourcing; potential stereotype — see Bias Audit.", status: "unresolved" }),
    f("F-008", { category: "Migration", metric: "Technician salary in Dubai (expat)", value: "4,500", unit: "AED/month", country: "UAE", region: "Dubai", yearStart: 2004, yearEnd: 2004, sourceId: "SRC-003", factType: "ESTIMATE", confidence: "low" }),
    f("F-009", { category: "Migration", metric: "Share of migrants from North India to Gulf", value: "unknown", unit: "%", yearStart: 2000, yearEnd: 2005, factType: "ASSUMPTION", confidence: "low", status: "unresolved", notes: "No source yet." }),
    f("F-010", { category: "Housing", metric: "Dubai apartment price (1BR, outskirts)", value: "550,000", unit: "AED", country: "UAE", region: "Dubai", yearStart: 2010, yearEnd: 2010, sourceId: "SRC-006", factType: "ESTIMATE", confidence: "low" }),
    f("F-011", { category: "Historical context", metric: "Economic liberalisation reforms begin", value: "1991", unit: "year", yearStart: 1991, yearEnd: 1991, sourceId: "SRC-002", factType: "FACT", confidence: "high", status: "verified", region: "National" }),
    f("F-012", { category: "Historical context", metric: "Global financial crisis hits Dubai property", value: "2008–2009", unit: "period", country: "UAE", region: "Dubai", yearStart: 2008, yearEnd: 2009, sourceId: "SRC-006", factType: "FACT", confidence: "medium" }),
    f("F-013", { category: "Education", metric: "Polytechnic annual fees (government)", value: "1,200", unit: "INR/year", yearStart: 1987, yearEnd: 1987, factType: "ESTIMATE", confidence: "low", notes: "No source attached yet.", status: "unresolved" }),
    f("F-014", { category: "Demographics", metric: "Male life expectancy at 60 (projection)", value: "+18", unit: "years", yearStart: 2030, yearEnd: 2030, sourceId: "SRC-002", factType: "ESTIMATE", confidence: "low", region: "National" }),
  ];

  const ev = (id: string, year: number, p: Partial<TimelineEvent> & Pick<TimelineEvent, "title" | "category">): TimelineEvent => ({
    ...base(id), episodeId: EP, year, age: year - 1970, location: "Delhi, India", description: "", financialEffect: "—", emotions: [], confidence: "medium", factIds: [], simulationReason: "Prototype placeholder — no engine yet.", locked: false, ...p,
  });

  const timeline: TimelineEvent[] = [
    ev("E-01", 1970, { category: "Family", title: "Birth", description: "Born second of three children in a rented flat in East Delhi.", emotions: ["joy", "family responsibility"], confidence: "high", locked: true, simulationReason: "Fixed by Character DNA." }),
    ev("E-02", 1976, { category: "Education", title: "Starts government school", description: "Enrolled at local government school.", confidence: "medium" }),
    ev("E-03", 1987, { category: "Education", title: "Completes secondary education", description: "Passes Class 12 with above-average marks.", emotions: ["pride"], factIds: ["F-013"] }),
    ev("E-04", 1987, { category: "Education", title: "Enters polytechnic (electrical diploma)", description: "Chooses a diploma for faster employment.", financialEffect: "-₹1,200/yr fees (mock)", factIds: ["F-013"], simulationReason: "High ambition + medium financial pressure → shorter vocational route." }),
    ev("E-05", 1990, { category: "Career", title: "First job — junior technician", description: "Joins a state electricity contractor.", financialEffect: "+₹2,400/mo (mock)", emotions: ["accomplishment"], factIds: ["F-003", "F-005"] }),
    ev("E-06", 1991, { category: "External", title: "Liberalisation reforms", description: "Economic reforms reshape private-sector hiring.", emotions: ["anxiety"], factIds: ["F-011", "F-001"], confidence: "high", locked: true, simulationReason: "Historical fact." }),
    ev("E-07", 1994, { category: "Career", title: "Promotion to site supervisor", description: "Moves to private firm after reforms.", financialEffect: "+40% salary (mock)", emotions: ["pride"] }),
    ev("E-08", 1996, { category: "Relationships", title: "Marriage", description: "Arranged marriage, age 26.", emotions: ["joy", "family responsibility"], factIds: ["F-006"] }),
    ev("E-09", 1998, { category: "Family", title: "First child born", description: "Daughter born.", financialEffect: "+household costs", emotions: ["joy", "financial pressure"] }),
    ev("E-10", 2001, { category: "Negative outlier", title: "Employer contract collapses", description: "Firm loses state contract; 7 months unemployed.", financialEffect: "-₹60,000 savings (mock)", emotions: ["anxiety", "loss of status"], confidence: "low" }),
    ev("E-11", 2003, { category: "Migration", title: "Migration opportunity", description: "Recruiter offers Dubai maintenance contract.", factIds: ["F-008", "F-009"], simulationReason: "Prototype branch: 30% move to Dubai (mock)." }),
    ev("E-12", 2004, { category: "Migration", title: "Moves to Dubai", description: "Leaves family in Delhi; sends remittances.", location: "Dubai, UAE", financialEffect: "+AED 4,500/mo (mock)", emotions: ["migration isolation", "family responsibility"], factIds: ["F-008"] }),
    ev("E-13", 2008, { category: "External", title: "Financial crisis in Dubai", description: "Projects frozen; salary cut 20%.", location: "Dubai, UAE", emotions: ["anxiety"], factIds: ["F-012"] }),
    ev("E-14", 2010, { category: "Finance", title: "Purchases apartment", description: "Buys 1BR on outskirts with mortgage.", location: "Dubai, UAE", financialEffect: "-AED 110,000 down payment (mock)", emotions: ["pride", "financial pressure"], factIds: ["F-010"] }),
    ev("E-15", 2018, { category: "Migration", title: "Return migration", description: "Returns to Delhi; daughter starts university.", financialEffect: "Sells apartment", emotions: ["joy", "regret"] }),
    ev("E-16", 2035, { category: "Career", title: "Retirement", description: "Retires from small electrical contracting business.", emotions: ["accomplishment"], confidence: "low" }),
    ev("E-17", 2047, { category: "Health", title: "Death", description: "Dies age 77 after cardiovascular illness.", emotions: ["grief"], factIds: ["F-014"], confidence: "low" }),
  ];

  const tasks: ResearchTask[] = (
    [
      ["Demographics", "Urban male life expectancy, India 1970–2047", "1970–2047", "complete", ["F-014"]],
      ["Demographics", "Median age at first marriage, urban North India", "1990–2000", "complete", ["F-006"]],
      ["Economy", "Annual CPI inflation India", "1970–2023", "complete", ["F-001"]],
      ["Economy", "INR/AED exchange rates", "2000–2020", "pending", []],
      ["Employment", "Technician & clerical wages, Delhi", "1988–2000", "in-progress", ["F-002", "F-005"]],
      ["Housing", "Rent levels East Delhi", "1985–2000", "in-progress", ["F-004"]],
      ["Housing", "Dubai residential prices", "2003–2018", "in-progress", ["F-010"]],
      ["Education", "Polytechnic fees & admissions", "1985–1990", "blocked", ["F-013"]],
      ["Migration", "Indian labour migration to UAE", "1995–2010", "in-progress", ["F-008", "F-009"]],
      ["Social environment", "Family support obligations (avoid stereotype)", "1970–2020", "pending", ["F-007"]],
      ["Historical context", "1991 reforms timeline", "1991", "complete", ["F-011"]],
      ["Historical context", "2008 crisis in Gulf construction", "2008–2010", "complete", ["F-012"]],
    ] as const
  ).map(([category, question, period, status, factIds], i) => ({
    ...base(`RT-${String(i + 1).padStart(3, "0")}`), episodeId: EP, category, question, period, status, assignedTo: "Research Worker (not configured)", factIds: [...factIds],
  }));

  const economics: EconomicYear[] = buildEconomics();

  const chapterTitles = ["Birth and Family", "Childhood", "Education", "Entering Adulthood", "Career", "Marriage and Family", "Crisis / Opportunity", "Migration", "Middle Age", "Later Life", "Death", "Life Receipt"];
  const chapterEvents = [["E-01"], ["E-02"], ["E-03", "E-04"], ["E-05", "E-06"], ["E-07"], ["E-08", "E-09"], ["E-10", "E-11"], ["E-12", "E-13", "E-14"], ["E-15"], ["E-16"], ["E-17"], []];
  const chapters: StoryChapter[] = chapterTitles.map((title, i) => ({
    ...base(`CH-${i + 1}`), episodeId: EP, number: i + 1, title,
    timelineEventIds: chapterEvents[i],
    factIds: timeline.filter((e) => chapterEvents[i].includes(e.id)).flatMap((e) => e.factIds),
    assumptionIds: i === 0 ? ["F-007"] : i === 7 ? ["F-009"] : [],
    text: i === 0
      ? "[DRAFT — human-written placeholder]\n\nThe flat had two rooms and a balcony that his mother used as a kitchen. He was the middle child of three, born in the winter of 1970 to a father who checked meters for the electricity board.\n\nWhat the family could afford — and what it could not — would shape most of what followed."
      : i === 7
        ? "[DRAFT — placeholder]\n\nThe recruiter's office in Lajpat Nagar smelled of photocopier toner. The offer was simple: a two-year contract, a shared room in Al Quoz, and a salary several times what he earned at home."
        : "",
    emotionalArc: i === 7 ? "Hope → isolation → hard-won stability" : "",
    unresolved: i === 7 ? "Migration share assumption (F-009) has no source." : "",
    engagement: i === 7
      ? { openQuestion: "Will migration improve his family's life?", tension: "Distance from a young daughter vs. income", decision: "Accept the Dubai contract", payoff: "Remittances fund daughter's education (Ch. 9)", transition: "The 2008 freeze arrives four years later." }
      : { openQuestion: "", tension: "", decision: "", payoff: "", transition: "" },
  }));

  const simulation: SimulationRun = {
    ...base("SIM-001"), episodeId: EP, seed: 19700117, isPrototype: true,
    controls: { ...character.controls, careerVolatility: 50, relationshipVolatility: 30, healthIntensity: 40 },
    decisionPoints: [
      { id: "DP-1", age: 17, year: 1987, question: "Post-secondary path", branches: [
        { id: "b1", label: "Polytechnic diploma", probability: 0.45, rationale: "Mock: shorter, cheaper route", chosen: true },
        { id: "b2", label: "University degree", probability: 0.25, rationale: "Mock", chosen: false },
        { id: "b3", label: "Enter workforce directly", probability: 0.3, rationale: "Mock", chosen: false },
      ] },
      { id: "DP-2", age: 33, year: 2003, question: "Respond to migration offer", branches: [
        { id: "b1", label: "Remain in India", probability: 0.55, rationale: "Mock", chosen: false },
        { id: "b2", label: "Move to Dubai", probability: 0.3, rationale: "Mock", chosen: true },
        { id: "b3", label: "Move elsewhere", probability: 0.1, rationale: "Mock", chosen: false },
        { id: "b4", label: "Other", probability: 0.05, rationale: "Mock", chosen: false },
      ] },
      { id: "DP-3", age: 48, year: 2018, question: "After daughter's schooling", branches: [
        { id: "b1", label: "Return to Delhi", probability: 0.5, rationale: "Mock", chosen: true },
        { id: "b2", label: "Stay in UAE", probability: 0.35, rationale: "Mock", chosen: false },
        { id: "b3", label: "Onward migration", probability: 0.15, rationale: "Mock", chosen: false },
      ] },
    ],
  };

  return {
    version: 1,
    episodes: [episode],
    tasks, sources, facts, timeline, economics, chapters,
    simulations: [simulation],
    activity: [
      { id: "A1", at: "2026-10-04T16:20:00Z", episodeId: EP, kind: "audit", text: "Audit run: 2 failures, 5 warnings" },
      { id: "A2", at: "2026-10-04T14:02:00Z", episodeId: EP, kind: "story", text: "Chapter 8 'Migration' revised" },
      { id: "A3", at: "2026-10-03T11:40:00Z", episodeId: EP, kind: "assumption", text: "F-009 flagged: no source" },
      { id: "A4", at: "2026-10-02T09:15:00Z", episodeId: EP, kind: "timeline", text: "Timeline generated (placeholder)" },
      { id: "A5", at: "2026-10-01T17:30:00Z", episodeId: EP, kind: "fact", text: "F-001 inflation marked verified" },
      { id: "A6", at: "2026-09-30T10:00:00Z", episodeId: EP, kind: "research", text: "Research: 1991 reforms completed" },
    ],
    settings: { backendUrl: "http://localhost:8000", hermesUrl: "http://127.0.0.1:8642", showMockBanners: true, defaultRealism: 75, currencyDisplay: "local" },
  };
}

// Deterministic mock economics (no randomness). Shape only — not research.
function buildEconomics(): EconomicYear[] {
  const rows: EconomicYear[] = [];
  let savings = 0;
  let index = 100;
  for (let year = 1990; year <= 2047; year += 1) {
    const age = year - 1970;
    const inDubai = year >= 2004 && year < 2018;
    const retired = year >= 2035;
    index *= year < 2000 ? 1.09 : year < 2015 ? 1.06 : 1.045;
    let income = retired ? 0 : Math.round(28800 * Math.pow(1.11, Math.min(year, 2034) - 1990));
    if (year === 2001) income = Math.round(income * 0.4);
    if (inDubai) income = Math.round(income * 2.6);
    if (year === 2009) income = Math.round(income * 0.8);
    const spouseIncome = year >= 2006 && !retired ? Math.round(income * 0.18) : 0;
    const hh = income + spouseIncome + (retired ? 180000 : 0);
    const housing = Math.round(hh * (inDubai ? 0.28 : 0.22));
    const food = Math.round(hh * 0.24);
    const education = year >= 2003 && year <= 2022 ? Math.round(hh * 0.1) : 0;
    const healthcare = Math.round(hh * (age > 60 ? 0.12 : 0.04));
    const transport = Math.round(hh * 0.06);
    const familySupport = !retired ? Math.round(hh * 0.08) : 0;
    const spend = housing + food + education + healthcare + transport + familySupport;
    savings = Math.max(0, savings + hh - spend);
    const property = year >= 2010 && year < 2018 ? 3_000_000 : year >= 2019 ? 4_500_000 + (year - 2019) * 200_000 : 0;
    const debt = year >= 2010 && year < 2018 ? Math.max(0, 2_400_000 - (year - 2010) * 300_000) : 0;
    rows.push({
      id: `EY-${year}`, episodeId: "ep-demo-delhi-dubai", year, age, income, spouseIncome,
      housing, food, education, healthcare, transport, familySupport, debt,
      savings: Math.round(savings * 0.6), investments: Math.round(savings * 0.4),
      assets: property + savings, liabilities: debt, currency: "INR", priceIndex: Math.round(index),
    });
  }
  return rows;
}
