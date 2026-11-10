"""Modelos de Marketplaces e Categorias Comerciais."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Category(Base):
    """Categorias comerciais de produtos (não limitadas apenas às 10 iniciais)."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    default_commission_estimate: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Marketplace(Base):
    """Plataforma de marketplace parceira (Mercado Livre, Amazon Brasil, Shopee Brasil, etc.)."""

    __tablename__ = "marketplaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    integration_mode: Mapped[str] = mapped_column(
        String(40), default="MANUAL_IMPORT", nullable=False
    )  # OFFICIAL_API | MANUAL_IMPORT
    availability_status: Mapped[str] = mapped_column(
        String(40), default="MISSING_CREDENTIALS", nullable=False
    )  # READY | MISSING_CREDENTIALS | ELIGIBILITY_REQUIRED | UNAVAILABLE
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    default_commission_rate: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_status: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

