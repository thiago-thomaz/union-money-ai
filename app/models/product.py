"""Modelo de Produto e indicadores de Inteligência Comercial."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Product(Base):
    """Produto monitorado ou promovido pela operação de afiliados."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(280), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    marketplace_id: Mapped[int] = mapped_column(ForeignKey("marketplaces.id"), nullable=False, index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False, index=True)

    # Preço e oferta
    price: Mapped[float] = mapped_column(Float, nullable=False)
    original_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="BRL", nullable=False)
    discount_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Comissões: separação estrita entre anunciada e efetivamente recebida
    announced_commission_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    effective_commission_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimated_commission_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Avaliações e Reputação (quando autorizadas)
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    review_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    seller_reputation: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)

    # Sinais de inteligência (0 a 100 na entrada da avaliação, ou None quando indisponível)
    demand_index: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    competition_index: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    content_potential_index: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    utility_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Disponibilidade e URLs
    in_stock: Mapped[Optional[bool]] = mapped_column(Boolean, default=True, nullable=True)
    product_url: Mapped[str] = mapped_column(Text, nullable=False)
    affiliate_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Qualidade e rastreabilidade dos dados: VERIFIED | ESTIMATED | UNAVAILABLE
    data_verification_map: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    data_source: Mapped[str] = mapped_column(
        String(50), default="MANUAL_VERIFIED", nullable=False
    )  # OFFICIAL_API | MANUAL_VERIFIED | SYNTHETIC_TEST
    is_synthetic_test: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    # Resultado do Product Opportunity Score (0 a 100 ou None se dados insuficientes)
    opportunity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, index=True)
    score_classification: Mapped[str] = mapped_column(
        String(60), default="INSUFFICIENT_DATA", nullable=False
    )
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    score_breakdown: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

