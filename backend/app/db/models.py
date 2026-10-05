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
    fact_id: Mapped[str] = mapped_column(ForeignKey("facts.id", ondelete="RESTRICT"), primary_key=True)
    role: Mapped[str] = mapped_column(String(40), primary_key=True)


class WageObservation(Base):
    """Structure for future wage datasets. Nothing writes here in Phase 3 (no wage provider exists)."""
    __tablename__ = "wage_observations"
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    provider: Mapped[str] = mapped_column(String(40))
    dataset: Mapped[str] = mapped_column(String(200))
    country_code: Mapped[str] = mapped_column(String(8))
    region: Mapped[str] = mapped_column(String(200), default="")
    year: Mapped[int] = mapped_column(Integer)
    occupation: Mapped[str] = mapped_column(String(200), default="")
    industry: Mapped[str] = mapped_column(String(200), default="")
    experience_level: Mapped[str] = mapped_column(String(80), default="")
    education: Mapped[str] = mapped_column(String(120), default="")
    gender: Mapped[str] = mapped_column(String(40), default="")
    sector: Mapped[str] = mapped_column(String(40), default="")  # formal | informal | all
    period: Mapped[str] = mapped_column(String(20))  # monthly | annual | hourly
    basis: Mapped[str] = mapped_column(String(10))  # gross | net
    statistic: Mapped[str] = mapped_column(String(10))  # mean | median
    value: Mapped[str] = mapped_column(String(60))
    currency: Mapped[str] = mapped_column(String(8))
    source_population: Mapped[str] = mapped_column(Text, default="")
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    retrieved_at: Mapped[str] = mapped_column(String(40))


class EpisodeDatasetSnapshot(Base):
    """Pins the exact observation values an episode relied on at a point in time."""
    __tablename__ = "episode_dataset_snapshots"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    episode_id: Mapped[str] = mapped_column(EP_FK(), index=True)
    label: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[str] = mapped_column(String(40))
    items: Mapped[list] = mapped_column(JSON)  # [{observationId, value, retrievedAt, providerLastUpdated}]
