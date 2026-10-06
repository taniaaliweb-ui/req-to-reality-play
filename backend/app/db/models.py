"""SQLAlchemy models. Nested value objects (traits, emotions, id lists) are JSON columns;
every record that belongs to an episode has a real foreign key with cascade delete."""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

EP_FK = lambda: ForeignKey("episodes.id", ondelete="CASCADE")  # noqa: E731


class Stamped:
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class Episode(Stamped, Base):
    __tablename__ = "episodes"
    title: Mapped[str] = mapped_column(String(300))
    stage: Mapped[str] = mapped_column(String(20))
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)
    character: Mapped["Character"] = relationship(back_populates="episode", cascade="all, delete-orphan", uselist=False, lazy="joined")


class Character(Stamped, Base):
    __tablename__ = "characters"
    episode_id: Mapped[str] = mapped_column(EP_FK(), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    country: Mapped[str] = mapped_column(String(120))
    region: Mapped[str] = mapped_column(String(200))
    birth_year: Mapped[int] = mapped_column(Integer)
    gender: Mapped[str] = mapped_column(String(20))
    settlement: Mapped[str] = mapped_column(String(20))
    starting_class: Mapped[str] = mapped_column(String(20))
    family: Mapped[dict] = mapped_column(JSON)
    traits: Mapped[dict] = mapped_column(JSON)
    controls: Mapped[dict] = mapped_column(JSON)
    episode: Mapped[Episode] = relationship(back_populates="character")


class ResearchTask(Stamped, Base):
    __tablename__ = "research_tasks"
    episode_id: Mapped[str] = mapped_column(EP_FK(), index=True)
    category: Mapped[str] = mapped_column(String(40))
    question: Mapped[str] = mapped_column(Text)
    period: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20))
    assigned_to: Mapped[str] = mapped_column(String(120))
    fact_ids: Mapped[list] = mapped_column(JSON, default=list)


class Source(Stamped, Base):
    __tablename__ = "sources"
    title: Mapped[str] = mapped_column(Text)
    organization: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(Text)
    publication_date: Mapped[str] = mapped_column(String(40))
    accessed_date: Mapped[str] = mapped_column(String(40))
    geo_coverage: Mapped[str] = mapped_column(String(200))
    time_coverage: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(40))
    reliability: Mapped[str] = mapped_column(String(20))
    notes: Mapped[str] = mapped_column(Text, default="")


class Fact(Stamped, Base):
    __tablename__ = "facts"
    episode_id: Mapped[str] = mapped_column(EP_FK(), index=True)
    category: Mapped[str] = mapped_column(String(40))
    metric: Mapped[str] = mapped_column(Text)
    value: Mapped[str] = mapped_column(String(200))
    unit: Mapped[str] = mapped_column(String(60))
    country: Mapped[str] = mapped_column(String(120))
    region: Mapped[str] = mapped_column(String(200))
    year_start: Mapped[int] = mapped_column(Integer)
    year_end: Mapped[int] = mapped_column(Integer)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    confidence: Mapped[str] = mapped_column(String(10))
    fact_type: Mapped[str] = mapped_column(String(12))
    derived_from: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20))
    # Phase 3 provenance
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    external_observation_id: Mapped[str | None] = mapped_column(ForeignKey("external_observations.id", ondelete="SET NULL"), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    dataset: Mapped[str | None] = mapped_column(String(200), nullable=True)
    indicator_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_prototype: Mapped[bool] = mapped_column(Boolean, default=False)


class TimelineEvent(Stamped, Base):
    __tablename__ = "timeline_events"
    episode_id: Mapped[str] = mapped_column(EP_FK(), index=True)
    year: Mapped[int] = mapped_column(Integer)
    age: Mapped[int] = mapped_column(Integer)
    location: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    financial_effect: Mapped[str] = mapped_column(String(300), default="")
    emotions: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[str] = mapped_column(String(10))
    fact_ids: Mapped[list] = mapped_column(JSON, default=list)
    simulation_reason: Mapped[str] = mapped_column(Text, default="")
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    simulation_run_id: Mapped[str | None] = mapped_column(String(80), nullable=True)  # set = written from a canonical simulated life


class EconomicYear(Base):
    __tablename__ = "economic_years"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    episode_id: Mapped[str] = mapped_column(EP_FK(), index=True)
    year: Mapped[int] = mapped_column(Integer)
    age: Mapped[int] = mapped_column(Integer)
    income: Mapped[float] = mapped_column(Float)
    spouse_income: Mapped[float] = mapped_column(Float)
    housing: Mapped[float] = mapped_column(Float)
    food: Mapped[float] = mapped_column(Float)
    education: Mapped[float] = mapped_column(Float)
    healthcare: Mapped[float] = mapped_column(Float)
    transport: Mapped[float] = mapped_column(Float)
    family_support: Mapped[float] = mapped_column(Float)
    debt: Mapped[float] = mapped_column(Float)
    savings: Mapped[float] = mapped_column(Float)
    investments: Mapped[float] = mapped_column(Float)
    assets: Mapped[float] = mapped_column(Float)
    liabilities: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8))
    price_index: Mapped[float] = mapped_column(Float)


class SimulationRun(Stamped, Base):
    __tablename__ = "simulation_runs"
    episode_id: Mapped[str] = mapped_column(EP_FK(), index=True)
    seed: Mapped[int] = mapped_column(Integer)
    controls: Mapped[dict] = mapped_column(JSON)
    decision_points: Mapped[list] = mapped_column(JSON)  # includes SimulationBranch records
    is_prototype: Mapped[bool] = mapped_column(Boolean, default=True)


class StoryChapter(Stamped, Base):
    __tablename__ = "story_chapters"
    episode_id: Mapped[str] = mapped_column(EP_FK(), index=True)
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    timeline_event_ids: Mapped[list] = mapped_column(JSON, default=list)
    fact_ids: Mapped[list] = mapped_column(JSON, default=list)
    assumption_ids: Mapped[list] = mapped_column(JSON, default=list)
    text: Mapped[str] = mapped_column(Text, default="")
    emotional_arc: Mapped[str] = mapped_column(Text, default="")
    unresolved: Mapped[str] = mapped_column(Text, default="")
    engagement: Mapped[dict] = mapped_column(JSON)


class AgentRun(Stamped, Base):
    """Reserved for future agent orchestration. Nothing writes here in Phase 2."""
    __tablename__ = "agent_runs"
    episode_id: Mapped[str | None] = mapped_column(EP_FK(), nullable=True)
    agent: Mapped[str] = mapped_column(String(120))
    task: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))


class Activity(Base):
    __tablename__ = "activity"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    at: Mapped[str] = mapped_column(String(40), index=True)
    episode_id: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)


class Meta(Base):
    """Key/value store: app settings and seed markers."""
    __tablename__ = "meta"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


# ---------------- Phase 3: truth + economic engine ----------------

class ExternalObservation(Base):
    """A value exactly as retrieved from an external provider (before it becomes a Fact)."""
    __tablename__ = "external_observations"
    id: Mapped[str] = mapped_column(String(160), primary_key=True)  # provider:indicator:country:year
    provider: Mapped[str] = mapped_column(String(40), index=True)
    dataset: Mapped[str] = mapped_column(String(200))
    indicator_code: Mapped[str] = mapped_column(String(80), index=True)
    indicator_name: Mapped[str] = mapped_column(Text)
    country_code: Mapped[str] = mapped_column(String(8), index=True)
    country_name: Mapped[str] = mapped_column(String(200))
    year: Mapped[int] = mapped_column(Integer, index=True)
    value: Mapped[str] = mapped_column(String(60))  # decimal string: full provider precision, no float rounding
    unit: Mapped[str] = mapped_column(String(120))
    source_organization: Mapped[str] = mapped_column(Text, default="")
    source_note: Mapped[str] = mapped_column(Text, default="")
    license: Mapped[str] = mapped_column(String(200), default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    provider_last_updated: Mapped[str] = mapped_column(String(40), default="")
    raw_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    retrieved_at: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class ObservationRevision(Base):
    """Audit trail when a refresh returns a different value for an existing observation."""
    __tablename__ = "observation_revisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    observation_id: Mapped[str] = mapped_column(ForeignKey("external_observations.id", ondelete="CASCADE"), index=True)
    old_value: Mapped[str] = mapped_column(String(60))
    new_value: Mapped[str] = mapped_column(String(60))
    old_retrieved_at: Mapped[str] = mapped_column(String(40))
    new_retrieved_at: Mapped[str] = mapped_column(String(40))
    old_provider_last_updated: Mapped[str] = mapped_column(String(40), default="")


class ProviderSync(Base):
    """One row per synchronisation request (what was asked, what came back)."""
    __tablename__ = "provider_syncs"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    started_at: Mapped[str] = mapped_column(String(40))
    finished_at: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))  # ok | partial | error
    request: Mapped[dict] = mapped_column(JSON)
    summary: Mapped[dict] = mapped_column(JSON)


class DerivedCalculation(Base):
    __tablename__ = "derived_calculations"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    episode_id: Mapped[str | None] = mapped_column(EP_FK(), nullable=True, index=True)
    output_fact_id: Mapped[str | None] = mapped_column(ForeignKey("facts.id", ondelete="SET NULL"), nullable=True, index=True)
    calculation_type: Mapped[str] = mapped_column(String(40))
    formula: Mapped[str] = mapped_column(Text)
    formula_version: Mapped[str] = mapped_column(String(40))
    engine_version: Mapped[str] = mapped_column(String(20))
    parameters_json: Mapped[dict] = mapped_column(JSON)
    result_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40))


class CalculationInput(Base):
    __tablename__ = "calculation_inputs"
    calculation_id: Mapped[str] = mapped_column(ForeignKey("derived_calculations.id", ondelete="CASCADE"), primary_key=True)
    fact_id: Mapped[str] = mapped_column(ForeignKey("facts.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(40), primary_key=True)


class EpisodeDatasetSnapshot(Base):
    """Immutable (once final) record of exactly what evidence an episode relied on."""
    __tablename__ = "episode_dataset_snapshots"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    episode_id: Mapped[str] = mapped_column(EP_FK(), index=True)
    label: Mapped[str] = mapped_column(String(200))  # snapshot name, e.g. "Delhi-Dubai Baseline v1"
    created_at: Mapped[str] = mapped_column(String(40))
    items: Mapped[list] = mapped_column(JSON)  # Phase 3 legacy observation pins
    status: Mapped[str] = mapped_column(String(10), default="draft")  # draft | final
    notes: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    finalized_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


SNAP_FK = lambda: ForeignKey("episode_dataset_snapshots.id", ondelete="CASCADE")  # noqa: E731


class SnapshotFact(Base):
    __tablename__ = "snapshot_facts"
    snapshot_id: Mapped[str] = mapped_column(SNAP_FK(), primary_key=True)
    fact_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    fact_updated_at: Mapped[str] = mapped_column(String(40))  # version reference
    payload: Mapped[dict] = mapped_column(JSON)  # frozen copy of the fact


class SnapshotObservation(Base):
    __tablename__ = "snapshot_observations"
    snapshot_id: Mapped[str] = mapped_column(SNAP_FK(), primary_key=True)
    external_observation_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    value: Mapped[str] = mapped_column(String(60))
    retrieved_at: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)


class SnapshotBaseline(Base):
    __tablename__ = "snapshot_baselines"
    snapshot_id: Mapped[str] = mapped_column(SNAP_FK(), primary_key=True)
    economic_baseline_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)


# ---------------- Phase 4: labour evidence ----------------

class WageObservation(Base):
    """Normalised wage statistic. NULL = the source does not provide that dimension (never invented)."""
    __tablename__ = "wage_observations"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    external_observation_id: Mapped[str] = mapped_column(ForeignKey("external_observations.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    country: Mapped[str] = mapped_column(String(8), index=True)
    region: Mapped[str | None] = mapped_column(String(200), nullable=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    period: Mapped[str] = mapped_column(String(20))
    frequency: Mapped[str] = mapped_column(String(10))
    statistic_type: Mapped[str] = mapped_column(String(14))  # MEAN | MEDIAN | DISTRIBUTION | OTHER
    pay_period: Mapped[str] = mapped_column(String(10))  # HOURLY | DAILY | WEEKLY | MONTHLY | ANNUAL
    value: Mapped[str | None] = mapped_column(String(60), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    nominal_or_real: Mapped[str] = mapped_column(String(80), default="UNKNOWN")
    gross_or_net: Mapped[str] = mapped_column(String(10), default="UNKNOWN")
    employee_scope: Mapped[str | None] = mapped_column(String(120), nullable=True)
    occupation_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    occupation_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    occupation_classification: Mapped[str | None] = mapped_column(String(40), nullable=True)
    industry_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    industry_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    industry_classification: Mapped[str | None] = mapped_column(String(40), nullable=True)
    education_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    education_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    education_classification: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sex: Mapped[str | None] = mapped_column(String(10), nullable=True)
    age_group: Mapped[str | None] = mapped_column(String(40), nullable=True)
    rural_urban: Mapped[str | None] = mapped_column(String(10), nullable=True)
    citizenship: Mapped[str | None] = mapped_column(String(40), nullable=True)
    migrant_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    formal_informal: Mapped[str | None] = mapped_column(String(10), nullable=True)
    employment_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    full_part_time: Mapped[str | None] = mapped_column(String(10), nullable=True)
    source_population: Mapped[str] = mapped_column(Text, default="")
    survey_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    confidence: Mapped[str] = mapped_column(String(10), default="high")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class WageDistribution(Base):
    __tablename__ = "wage_distributions"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    provider: Mapped[str] = mapped_column(String(40))
    dataset: Mapped[str] = mapped_column(String(200))
    country: Mapped[str] = mapped_column(String(8), index=True)
    year: Mapped[int] = mapped_column(Integer)
    metric: Mapped[str] = mapped_column(Text)
    pay_period: Mapped[str] = mapped_column(String(10))
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dimensions: Mapped[dict] = mapped_column(JSON, default=dict)  # sex, citizenship, ... as published
    source_organization: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40))


class WageDistributionBin(Base):
    __tablename__ = "wage_distribution_bins"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    distribution_id: Mapped[str] = mapped_column(ForeignKey("wage_distributions.id", ondelete="CASCADE"), index=True)
    lower_bound: Mapped[str | None] = mapped_column(String(40), nullable=True)
    upper_bound: Mapped[str | None] = mapped_column(String(40), nullable=True)
    open_lower: Mapped[bool] = mapped_column(Boolean, default=False)
    open_upper: Mapped[bool] = mapped_column(Boolean, default=False)
    count: Mapped[str | None] = mapped_column(String(40), nullable=True)
    share: Mapped[str | None] = mapped_column(String(40), nullable=True)
    unit: Mapped[str] = mapped_column(String(60), default="")
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    external_observation_id: Mapped[str | None] = mapped_column(String(200), nullable=True)


class CharacterEconomicProfile(Base):
    """What evidence to search for at one life stage. Not a wage claim."""
    __tablename__ = "character_economic_profiles"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    episode_id: Mapped[str] = mapped_column(EP_FK(), index=True)
    life_stage: Mapped[str] = mapped_column(String(40))
    target_year: Mapped[int] = mapped_column(Integer)
    year_start: Mapped[int] = mapped_column(Integer)
    year_end: Mapped[int] = mapped_column(Integer)
    fields: Mapped[dict] = mapped_column(JSON)  # country, region, urbanRural, educationLevel, occupation, occupationCode, ...
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class CandidateReview(Base):
    __tablename__ = "candidate_reviews"
    profile_id: Mapped[str] = mapped_column(ForeignKey("character_economic_profiles.id", ondelete="CASCADE"), primary_key=True)
    wage_observation_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    decision: Mapped[str] = mapped_column(String(12))  # rejected | flagged
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40))


class EconomicBaseline(Base):
    __tablename__ = "economic_baselines"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    episode_id: Mapped[str] = mapped_column(EP_FK(), index=True)
    profile_id: Mapped[str | None] = mapped_column(ForeignKey("character_economic_profiles.id", ondelete="SET NULL"), nullable=True)
    life_stage: Mapped[str] = mapped_column(String(40))
    year_start: Mapped[int] = mapped_column(Integer)
    year_end: Mapped[int] = mapped_column(Integer)
    employment_type: Mapped[str] = mapped_column(String(40), default="")
    occupation: Mapped[str] = mapped_column(String(200), default="")
    baseline_type: Mapped[str] = mapped_column(String(16))  # FACT_SUPPORTED | ASSUMPTION | DERIVED
    estimate_kind: Mapped[str] = mapped_column(String(12))  # POINT | RANGE | DISTRIBUTION
    low: Mapped[str | None] = mapped_column(String(60), nullable=True)
    high: Mapped[str | None] = mapped_column(String(60), nullable=True)
    point: Mapped[str | None] = mapped_column(String(60), nullable=True)
    currency: Mapped[str] = mapped_column(String(8))
    pay_period: Mapped[str] = mapped_column(String(10))
    gross_or_net: Mapped[str] = mapped_column(String(10), default="UNKNOWN")
    annualization: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[str] = mapped_column(String(20))  # HIGH | MEDIUM | LOW | INSUFFICIENT_DATA
    confidence_reasons: Mapped[list] = mapped_column(JSON, default=list)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[list] = mapped_column(JSON, default=list)  # [{wageObservationId, observationId, factId, score, yearDistance}]
    source_fact_ids: Mapped[list] = mapped_column(JSON, default=list)
    derived_calculation_ids: Mapped[list] = mapped_column(JSON, default=list)
    assumption_fact_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class EvidenceGap(Base):
    __tablename__ = "evidence_gaps"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    episode_id: Mapped[str] = mapped_column(EP_FK(), index=True)
    gap_key: Mapped[str] = mapped_column(String(200), index=True)
    title: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(40))
    country: Mapped[str] = mapped_column(String(120), default="")
    year_start: Mapped[int] = mapped_column(Integer)
    year_end: Mapped[int] = mapped_column(Integer)
    priority: Mapped[str] = mapped_column(String(8))  # HIGH | MEDIUM | LOW
    status: Mapped[str] = mapped_column(String(10), default="open")
    auto: Mapped[bool] = mapped_column(Boolean, default=True)
    research_task_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    # Phase 5 generalisation (NULL on Phase 4 gaps)
    domain: Mapped[str | None] = mapped_column(String(40), nullable=True)
    life_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target_population: Mapped[str | None] = mapped_column(Text, nullable=True)


class HouseholdUnit(Base):
    __tablename__ = "household_units"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    episode_id: Mapped[str] = mapped_column(EP_FK(), index=True)
    label: Mapped[str] = mapped_column(String(200))
    year_start: Mapped[int] = mapped_column(Integer)
    year_end: Mapped[int] = mapped_column(Integer)
    members: Mapped[list] = mapped_column(JSON, default=list)  # [{id, role, name, employmentKind}]
    created_at: Mapped[str] = mapped_column(String(40))


class IncomeStream(Base):
    __tablename__ = "income_streams"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    household_id: Mapped[str] = mapped_column(ForeignKey("household_units.id", ondelete="CASCADE"), index=True)
    member_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    kind: Mapped[str] = mapped_column(String(30))
    year_start: Mapped[int] = mapped_column(Integer)
    year_end: Mapped[int] = mapped_column(Integer)
    low: Mapped[str | None] = mapped_column(String(60), nullable=True)
    high: Mapped[str | None] = mapped_column(String(60), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    pay_period: Mapped[str | None] = mapped_column(String(10), nullable=True)
    basis: Mapped[str] = mapped_column(String(16))  # FACT_SUPPORTED | ASSUMPTION | DERIVED | UNKNOWN
    baseline_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    fact_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40))


# ---------------- Phase 5: life-context evidence ----------------

class LifeObservation(Base):
    """Normalised population-level evidence for one life domain (demographic, mortality, fertility,
    migration, education, education_cost, housing, household_expenditure, family_formation,
    retirement, pension, employment_context). One table, discriminated by `domain`; NULL dimension =
    the source does not publish it (never invented). A population statistic, never an individual outcome."""
    __tablename__ = "life_observations"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    external_observation_id: Mapped[str | None] = mapped_column(ForeignKey("external_observations.id", ondelete="CASCADE"), nullable=True, index=True)
    domain: Mapped[str] = mapped_column(String(40), index=True)
    metric: Mapped[str] = mapped_column(String(80), index=True)
    metric_label: Mapped[str] = mapped_column(Text)
    value: Mapped[str] = mapped_column(String(60))
    unit: Mapped[str] = mapped_column(String(120))
    country: Mapped[str] = mapped_column(String(8), index=True)  # ISO3
    region: Mapped[str | None] = mapped_column(String(200), nullable=True)
    geo_level: Mapped[str] = mapped_column(String(12), default="NATIONAL")  # NATIONAL | REGION | CITY
    year: Mapped[int] = mapped_column(Integer, index=True)
    age: Mapped[str | None] = mapped_column(String(20), nullable=True)
    age_group: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sex: Mapped[str | None] = mapped_column(String(10), nullable=True)
    education_level: Mapped[str | None] = mapped_column(String(60), nullable=True)
    urban_rural: Mapped[str | None] = mapped_column(String(10), nullable=True)
    income_group: Mapped[str | None] = mapped_column(String(60), nullable=True)
    household_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    housing_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    category: Mapped[str | None] = mapped_column(String(60), nullable=True)  # expenditure category / cost type
    origin_country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    destination_country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    population_scope: Mapped[str] = mapped_column(Text, default="")
    observation_type: Mapped[str] = mapped_column(String(20), default="ESTIMATE")  # ESTIMATE | PROJECTION | SURVEY | ADMINISTRATIVE | CENSUS | MANUAL
    provider: Mapped[str] = mapped_column(String(40), index=True)
    dataset: Mapped[str] = mapped_column(String(200), default="")
    source: Mapped[str] = mapped_column(Text, default="")
    source_organization: Mapped[str] = mapped_column(Text, default="")
    is_prototype: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class PolicyEvidence(Base):
    __tablename__ = "policy_evidence"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    country: Mapped[str] = mapped_column(String(8), index=True)
    policy_type: Mapped[str] = mapped_column(String(40))  # work-visa | residency | citizenship | family-sponsorship | retirement | pension | labour-law | emigration
    title: Mapped[str] = mapped_column(Text)
    effective_start: Mapped[str] = mapped_column(String(10))  # YYYY or YYYY-MM-DD
    effective_end: Mapped[str | None] = mapped_column(String(10), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(Text, default="")
    source_organization: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    fact_type: Mapped[str] = mapped_column(String(16), default="FACT")  # FACT | CONTEXT
    confidence: Mapped[str] = mapped_column(String(10), default="MEDIUM")
    verification: Mapped[str] = mapped_column(String(20), default="unverified")  # unverified | verified
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class HistoricalEvent(Base):
    __tablename__ = "historical_events"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40))  # recession | currency-crisis | war | pandemic | oil-shock | financial-crisis | policy-change | migration-event | technology | natural-disaster
    geography: Mapped[list] = mapped_column(JSON, default=list)  # ISO3 codes, region groups (GCC, SOUTH_ASIA) or WORLD
    region: Mapped[str | None] = mapped_column(String(200), nullable=True)  # sub-national scope, when the event was regional
    start_date: Mapped[str] = mapped_column(String(10))
    end_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    economic_relevance: Mapped[str] = mapped_column(String(10), default="MEDIUM")  # HIGH | MEDIUM | LOW
    description: Mapped[str] = mapped_column(Text, default="")
    sources: Mapped[list] = mapped_column(JSON, default=list)  # [{organization, title, url}]
    verification: Mapped[str] = mapped_column(String(20), default="unverified")
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class ContextEvidence(Base):
    """Qualitative social context. NOT a statistical fact unless the source supports a measurable claim."""
    __tablename__ = "context_evidence"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    topic: Mapped[str] = mapped_column(String(60))
    country: Mapped[str] = mapped_column(String(8), index=True)
    region: Mapped[str | None] = mapped_column(String(200), nullable=True)
    year_start: Mapped[int] = mapped_column(Integer)
    year_end: Mapped[int] = mapped_column(Integer)
    population_scope: Mapped[str] = mapped_column(Text, default="")
    claim: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text, default="")
    evidence_type: Mapped[str] = mapped_column(String(30))  # QUALITATIVE | SURVEY_FINDING | ETHNOGRAPHIC | LEGAL_TEXT | MEASURABLE_CLAIM
    confidence: Mapped[str] = mapped_column(String(10), default="LOW")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class Assumption(Base):
    __tablename__ = "assumptions"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    episode_id: Mapped[str] = mapped_column(EP_FK(), index=True)
    domain: Mapped[str] = mapped_column(String(40))
    life_stage: Mapped[str] = mapped_column(String(40))
    claim: Mapped[str] = mapped_column(Text)
    value: Mapped[str] = mapped_column(String(120), default="")
    unit: Mapped[str] = mapped_column(String(120), default="")
    year_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    year_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(80), default="user")
    supporting_evidence: Mapped[list] = mapped_column(JSON, default=list)  # ids of life observations / facts
    confidence: Mapped[str] = mapped_column(String(10), default="LOW")
    status: Mapped[str] = mapped_column(String(12), default="active")  # active | retired
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class LifeStageBaseline(Base):
    __tablename__ = "life_stage_baselines"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    episode_id: Mapped[str] = mapped_column(EP_FK(), index=True)
    domain: Mapped[str] = mapped_column(String(40))
    life_stage: Mapped[str] = mapped_column(String(40))
    year_start: Mapped[int] = mapped_column(Integer)
    year_end: Mapped[int] = mapped_column(Integer)
    country: Mapped[str] = mapped_column(String(8))
    scope: Mapped[str] = mapped_column(Text, default="")
    metric: Mapped[str] = mapped_column(String(80), default="")
    estimate_kind: Mapped[str] = mapped_column(String(12))  # POINT | RANGE | DISTRIBUTION
    low: Mapped[str | None] = mapped_column(String(60), nullable=True)
    high: Mapped[str | None] = mapped_column(String(60), nullable=True)
    point: Mapped[str | None] = mapped_column(String(60), nullable=True)
    distribution: Mapped[list | None] = mapped_column(JSON, nullable=True)
    unit: Mapped[str] = mapped_column(String(120), default="")
    coverage_type: Mapped[str] = mapped_column(String(10))  # DIRECT | NEARBY | DERIVED | ASSUMED
    coverage: Mapped[list] = mapped_column(JSON, default=list)  # per-year coverage
    confidence: Mapped[str] = mapped_column(String(20))
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    assumption_ids: Mapped[list] = mapped_column(JSON, default=list)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    user_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class MigrationPath(Base):
    __tablename__ = "migration_paths"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    episode_id: Mapped[str] = mapped_column(EP_FK(), index=True)
    origin: Mapped[str] = mapped_column(String(8))
    destination: Mapped[str] = mapped_column(String(8))
    year_start: Mapped[int] = mapped_column(Integer)
    year_end: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40))


class SnapshotRecord(Base):
    """Phase 5 snapshot contents: frozen copies of life evidence, baselines, policies, events,
    context, assumptions and gaps (immutable once the snapshot is final — DB triggers)."""
    __tablename__ = "snapshot_records"
    snapshot_id: Mapped[str] = mapped_column(SNAP_FK(), primary_key=True)
    record_type: Mapped[str] = mapped_column(String(30), primary_key=True)
    record_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)


# ---------------- Phase 6: simulation, story, production, research interface ----------------
RUN_FK = lambda: ForeignKey("life_simulation_runs.id", ondelete="CASCADE")  # noqa: E731


class SimulationPrior(Base):
    """Provisional model prior — NOT a researched probability. Versioned: an edit creates a new row
    (same key, version+1) and deactivates the previous one, so old simulation inputs stay reproducible."""
    __tablename__ = "simulation_priors"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)  # e.g. P-MARRIAGE-BASE@v1
    key: Mapped[str] = mapped_column(String(60), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    domain: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    parameter: Mapped[dict] = mapped_column(JSON)
    conditions: Mapped[dict] = mapped_column(JSON, default=dict)
    source_type: Mapped[str] = mapped_column(String(40), default="PROVISIONAL_SYSTEM_PRIOR")
    notes: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)  # disabled = not approved for simulation use
    active: Mapped[bool] = mapped_column(Boolean, default=True)  # latest version of its key
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class SimulationInput(Base):
    """Frozen input package (immutable via DB trigger)."""
    __tablename__ = "simulation_inputs"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    episode_id: Mapped[str] = mapped_column(EP_FK(), index=True)
    dataset_snapshot_id: Mapped[str] = mapped_column(String(80))
    character_version: Mapped[str] = mapped_column(String(64))
    assumption_ids: Mapped[list] = mapped_column(JSON, default=list)
    locked_timeline_event_ids: Mapped[list] = mapped_column(JSON, default=list)
    prior_ids: Mapped[list] = mapped_column(JSON, default=list)
    prior_registry_version: Mapped[str] = mapped_column(String(64))
    economic_engine_version: Mapped[str] = mapped_column(String(20))
    simulation_engine_version: Mapped[str] = mapped_column(String(20))
    config: Mapped[dict] = mapped_column(JSON)
    master_seed: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)  # frozen character, assumptions, locks, priors, evidence
    review: Mapped[dict] = mapped_column(JSON)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40))


class LifeSimulationRun(Base):
    __tablename__ = "life_simulation_runs"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    episode_id: Mapped[str] = mapped_column(EP_FK(), index=True)
    input_id: Mapped[str] = mapped_column(ForeignKey("simulation_inputs.id", ondelete="CASCADE"), index=True)
    seed: Mapped[int] = mapped_column(Integer)
    engine_version: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(20), default="single")  # single | batch | branch | regenerate | what-if
    status: Mapped[str] = mapped_column(String(12), default="COMPLETED")
    batch_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    parent_run_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    branch_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overrides: Mapped[list] = mapped_column(JSON, default=list)
    label: Mapped[str] = mapped_column(String(200), default="")
    final_state: Mapped[dict] = mapped_column(JSON, default=dict)
    economic_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    outcome: Mapped[dict] = mapped_column(JSON, default=dict)
    quality_report: Mapped[dict] = mapped_column(JSON, default=dict)
    audit: Mapped[list] = mapped_column(JSON, default=list)
    is_canonical: Mapped[bool] = mapped_column(Boolean, default=False)
    canonical_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[str] = mapped_column(String(40))
    completed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class AnnualLifeState(Base):
    __tablename__ = "annual_life_states"
    run_id: Mapped[str] = mapped_column(RUN_FK(), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    age: Mapped[int] = mapped_column(Integer)
    country: Mapped[str] = mapped_column(String(8))
    employment_state: Mapped[str] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(String(8))
    income: Mapped[str] = mapped_column(String(40))
    net_worth: Mapped[str] = mapped_column(String(40))
    state: Mapped[dict] = mapped_column(JSON)


class SimulationEvent(Base):
    __tablename__ = "simulation_events"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    run_id: Mapped[str] = mapped_column(RUN_FK(), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    year: Mapped[int] = mapped_column(Integer)
    age: Mapped[int] = mapped_column(Integer)
    domain: Mapped[str] = mapped_column(String(30))
    event_type: Mapped[str] = mapped_column(String(40))
    state_before: Mapped[dict] = mapped_column(JSON, default=dict)
    state_after: Mapped[dict] = mapped_column(JSON, default=dict)
    probability: Mapped[str | None] = mapped_column(String(20), nullable=True)
    probability_class: Mapped[str] = mapped_column(String(30))
    probability_source_ids: Mapped[list] = mapped_column(JSON, default=list)
    fact_ids: Mapped[list] = mapped_column(JSON, default=list)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    assumption_ids: Mapped[list] = mapped_column(JSON, default=list)
    prior_ids: Mapped[list] = mapped_column(JSON, default=list)
    rule_id: Mapped[str] = mapped_column(String(60))
    rule_version: Mapped[str] = mapped_column(String(10))
    modifiers: Mapped[list] = mapped_column(JSON, default=list)
    base_probability: Mapped[str | None] = mapped_column(String(20), nullable=True)
    random_draw: Mapped[str | None] = mapped_column(String(20), nullable=True)
    outcome: Mapped[str] = mapped_column(String(20))  # OCCURRED | NOT_OCCURRED | FORCED | DETERMINISTIC
    occurred: Mapped[bool] = mapped_column(Boolean)
    importance: Mapped[int] = mapped_column(Integer, default=1)
    explanation: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))
    lineage: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Phase 6.1: source → formula → result (mortality, wages)


class SimulationJob(Base):
    __tablename__ = "simulation_jobs"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    episode_id: Mapped[str] = mapped_column(EP_FK(), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(12))  # QUEUED | RUNNING | COMPLETED | FAILED | CANCELLED
    total: Mapped[int] = mapped_column(Integer, default=0)
    done: Mapped[int] = mapped_column(Integer, default=0)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(40))
    started_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    completed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class StoryArtifact(Base):
    """Generated story / production structure for one canonical run (kind = story | production)."""
    __tablename__ = "story_artifacts"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    episode_id: Mapped[str] = mapped_column(EP_FK(), index=True)
    run_id: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSON)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class CandidateEvidence(Base):
    """Evidence submitted by an external researcher (human, MCP agent, future AI). Never self-verifying."""
    __tablename__ = "candidate_evidence"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    episode_id: Mapped[str | None] = mapped_column(EP_FK(), nullable=True, index=True)
    research_task_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    claim: Mapped[str] = mapped_column(Text)
    value: Mapped[str] = mapped_column(String(120), default="")
    unit: Mapped[str] = mapped_column(String(120), default="")
    location: Mapped[str] = mapped_column(String(200), default="")
    period_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    period_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    proposed_type: Mapped[str] = mapped_column(String(30), default="FACT")
    submitted_by: Mapped[str] = mapped_column(String(80), default="user")
    status: Mapped[str] = mapped_column(String(16), default="PENDING_REVIEW")
    review_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    # Phase 6.1 acceptance pipeline: reviewer-validated scope + links to the structured records it produced (original fields above never change)
    accepted_as: Mapped[str | None] = mapped_column(String(20), nullable=True)  # FACT | ESTIMATE | CONTEXT | ASSUMPTION | REJECT
    reviewed_scope: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    links: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # sourceId, externalObservationId, lifeObservationId, factId, contextId, assumptionId


class EvidenceReplacement(Base):
    """'New evidence may replace assumption/prior X.' Never applied silently: review → new snapshot version → rerun."""
    __tablename__ = "evidence_replacements"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    episode_id: Mapped[str] = mapped_column(EP_FK(), index=True)
    candidate_id: Mapped[str] = mapped_column(String(80))
    target_kind: Mapped[str] = mapped_column(String(12))  # ASSUMPTION | PRIOR
    target_id: Mapped[str] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="OPEN")  # OPEN | SNAPSHOTTED | RERUN | DISMISSED
    new_snapshot_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    new_run_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    resolved_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class McpApproval(Base):
    """A CONSEQUENTIAL_WRITE MCP call waiting for the user's explicit decision. Executed only after approval."""
    __tablename__ = "mcp_approvals"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tool: Mapped[str] = mapped_column(String(60))
    arguments: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(12), default="PENDING")  # PENDING | APPROVED | REJECTED | EXECUTED | FAILED
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    decided_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class AgentJob(Base):
    """Reserved for future AI orchestration. No provider is configured; nothing produces results yet."""
    __tablename__ = "agent_jobs"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    role: Mapped[str] = mapped_column(String(30))
    task: Mapped[str] = mapped_column(Text)
    parent_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="QUEUED")
    provider: Mapped[str] = mapped_column(String(20), default="NOT_CONFIGURED")
    model: Mapped[str] = mapped_column(String(80), default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))
