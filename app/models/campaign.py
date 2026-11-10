"""Modelos de Campanhas Comerciais e Experimentação A/B."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Campaign(Base):
    """Campanha de divulgação de produtos de afiliados por nicho."""

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    objective: Mapped[str] = mapped_column(String(120), default="CONVERSIONS", nullable=False)
    target_channel: Mapped[str] = mapped_column(String(80), default="ORGANIC_MULTI", nullable=False)
    target_audience: Mapped[Optional[str]] = mapped_column(String(220), nullable=True)
    problem_solved: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    priority_weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"), nullable=True, index=True)
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(40), default="ACTIVE", nullable=False, index=True
    )  # DRAFT | ACTIVE | PAUSED | COMPLETED
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class Experiment(Base):
    """Experimento A/B para títulos, formatos de conteúdo e chamadas (CTAs)."""

    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    campaign_id: Mapped[Optional[int]] = mapped_column(ForeignKey("campaigns.id"), nullable=True, index=True)
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    dimension: Mapped[str] = mapped_column(
        String(50), default="TITLE", nullable=False
    )  # TITLE | FORMAT | CTA
    status: Mapped[str] = mapped_column(
        String(40), default="RUNNING", nullable=False
    )  # RUNNING | COMPLETED | ARCHIVED
    winning_variant_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    confidence_level: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ExperimentVariant(Base):
    """Variante individual dentro de um experimento A/B."""

    __tablename__ = "experiment_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"), nullable=False, index=True)
    variant_key: Mapped[str] = mapped_column(String(20), nullable=False)  # Ex.: "A", "B"
    headline_or_cta: Mapped[str] = mapped_column(String(280), nullable=False)
    content_format: Mapped[str] = mapped_column(String(60), default="ARTICLE_REVIEW", nullable=False)
    impressions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conversions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
