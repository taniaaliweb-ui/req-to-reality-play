"""Pydantic API schemas mirroring src/types/lifespan.ts (camelCase over the wire)."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

Id = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:\-]{1,80}$")]
Year = Annotated[int, Field(ge=1800, le=2200)]
Score = Annotated[int, Field(ge=0, le=100)]
Level = Literal["low", "medium", "high"]
SocioClass = Literal["poverty", "working", "lower-middle", "middle", "upper-middle", "wealthy"]
Stage = Literal["idea", "dna", "research", "sources", "facts", "timeline", "simulation", "story", "audit", "production", "receipt"]
ResearchCategory = Literal["Demographics", "Economy", "Employment", "Housing", "Education", "Migration", "Social environment", "Historical context"]
FactType = Literal["FACT", "ESTIMATE", "ASSUMPTION", "DERIVED"]
EventCategory = Literal["Career", "Relationships", "Finance", "Migration", "Health", "External", "Education", "Family", "Positive outlier", "Negative outlier"]
Emotion = Literal["joy", "grief", "loneliness", "anxiety", "pride", "regret", "family responsibility", "migration isolation", "relationship stress", "financial pressure", "loss of status", "accomplishment"]


class Schema(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True, extra="ignore")

    def out(self) -> dict:
        return self.model_dump(by_alias=True)


class Stamped(Schema):
    id: Id
    created_at: str = ""
    updated_at: str = ""


class Traits(Schema):
    ambition: Score; aptitude: Score; risk_tolerance: Score; discipline: Score; social_skills: Score
    financial_discipline: Score; resilience: Score; family_attachment: Score; migration_willingness: Score


class Controls(Schema):
    realism: Score; randomness: Score; adversity: Score; upward_mobility: Score; downward_risk: Score


class Family(Schema):
    guardians: Annotated[int, Field(ge=0, le=10)]
    siblings: Annotated[int, Field(ge=0, le=30)]
    parental_income_class: SocioClass
    parental_education: str = ""
    housing: str = ""


class CharacterIn(Stamped):
    name: str
    country: str
    region: str = ""
    birth_year: Year
    gender: Literal["male", "female", "non-binary", "unspecified"]
    settlement: Literal["urban", "suburban", "rural"]
    starting_class: SocioClass
    family: Family
    traits: Traits
    controls: Controls


class EpisodeIn(Stamped):
    title: Annotated[str, Field(min_length=1, max_length=300)]
    stage: Stage
    is_mock: bool = False
    character: CharacterIn


class ResearchTaskIn(Stamped):
    episode_id: Id
    category: ResearchCategory
    question: str
    period: str = ""
    status: Literal["pending", "in-progress", "complete", "blocked"]
    assigned_to: str = ""
    fact_ids: list[Id] = []


class SourceIn(Stamped):
    title: str
    organization: str = ""
    url: str = ""
    publication_date: str = ""
    accessed_date: str = ""
    geo_coverage: str = ""
    time_coverage: str = ""
    type: Literal["government", "World Bank", "UN", "OECD", "academic", "statistical agency", "newspaper", "historical archive", "industry", "other"]
    reliability: Literal["Primary", "Strong", "Moderate", "Weak"]
    notes: str = ""


class FactIn(Stamped):
    episode_id: Id
    category: ResearchCategory
    metric: str
    value: str
    unit: str = ""
    country: str = ""
    region: str = ""
    year_start: Year
    year_end: Year
    source_id: Id | None = None
    confidence: Level
    fact_type: FactType
    derived_from: str | None = None
    notes: str = ""
    status: Literal["verified", "unverified", "unresolved", "disputed"]
    # Phase 3 provenance (all optional so Phase 1/2 data stays valid)
    currency: str | None = None
    external_observation_id: Annotated[str, Field(max_length=160)] | None = None
    provider: str | None = None
    dataset: str | None = None
    indicator_code: str | None = None
    is_prototype: bool = False

    @model_validator(mode="after")
    def _years(self):
        if self.year_end < self.year_start:
            raise ValueError("yearEnd must be >= yearStart")
        return self


class TimelineEventIn(Stamped):
    episode_id: Id
    year: Year
    age: Annotated[int, Field(ge=-1, le=150)]
    location: str = ""
    category: EventCategory
    title: str
    description: str = ""
    financial_effect: str = ""
    emotions: list[Emotion] = []
    confidence: Level
    fact_ids: list[Id] = []
    simulation_reason: str = ""
    locked: bool = False
    simulation_run_id: str | None = None


class EconomicYearIn(Schema):
    id: Id
    episode_id: Id
    year: Year
    age: int
    income: float; spouse_income: float; housing: float; food: float; education: float
    healthcare: float; transport: float; family_support: float; debt: float; savings: float
    investments: float; assets: float; liabilities: float
    currency: str
    price_index: float


class Branch(Schema):
    id: str
    label: str
    probability: Annotated[float, Field(ge=0, le=1)]
    rationale: str = ""
    chosen: bool = False


class DecisionPoint(Schema):
    id: str
    age: int
    year: Year
    question: str
    branches: list[Branch]


class SimControls(Controls):
    career_volatility: Score; relationship_volatility: Score; health_intensity: Score


class SimulationRunIn(Stamped):
    episode_id: Id
    seed: int
    controls: SimControls
    decision_points: list[DecisionPoint]
    is_prototype: Literal[True] = True


class Engagement(Schema):
    open_question: str = ""; tension: str = ""; decision: str = ""; payoff: str = ""; transition: str = ""


class StoryChapterIn(Stamped):
    episode_id: Id
    number: Annotated[int, Field(ge=1, le=100)]
    title: str
    timeline_event_ids: list[Id] = []
    fact_ids: list[Id] = []
    assumption_ids: list[Id] = []
    text: str = ""
    emotional_arc: str = ""
    unresolved: str = ""
    engagement: Engagement


class ActivityIn(Schema):
    id: Id
    at: str
    episode_id: str
    kind: Literal["research", "fact", "timeline", "assumption", "story", "audit", "episode"]
    text: str


class SettingsIn(Schema):
    backend_url: str = "http://127.0.0.1:8000"
    hermes_url: str = "http://127.0.0.1:8642"
    show_mock_banners: bool = True
    default_realism: Score = 75
    currency_display: Literal["local", "USD"] = "local"
    external_data_enabled: bool = True
    world_bank_enabled: bool = True
    ilostat_enabled: bool = True
    uae_stat_enabled: bool = True
    un_wpp_enabled: bool = True
    # Readiness groups a full-life simulation must have evidence for (user may override with explicit assumptions later)
    simulation_required_domains: list[str] = ["demographic", "education", "career", "household", "family", "migration", "housing", "retirement"]


class AuditOut(Schema):
    id: str
    category: Literal["Fact", "Timeline", "Economic", "Geographic", "Historical", "Story", "Assumption", "Bias"]
    outcome: Literal["PASS", "WARNING", "FAIL"]
    title: str
    explanation: str
    refs: list[str]
    automated: bool


class Snapshot(Schema):
    """Full workspace in the same shape as the frontend LifespanDB (version 1)."""
    version: Literal[1] = 1
    episodes: list[EpisodeIn] = []
    tasks: list[ResearchTaskIn] = []
    sources: list[SourceIn] = []
    facts: list[FactIn] = []
    timeline: list[TimelineEventIn] = []
    economics: list[EconomicYearIn] = []
    simulations: list[SimulationRunIn] = []
    chapters: list[StoryChapterIn] = []
    activity: list[ActivityIn] = []
    settings: SettingsIn = SettingsIn()


class ImportRequest(Schema):
    data: Snapshot
    overwrite: bool = False
