"""Modelos de Visitantes Agregados e Cliques Rastreáveis (nunca contabilizados como vendas)."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class VisitorAggregate(Base):
    """Métricas diárias agregadas de visitantes e visualizações por canal/página."""

    __tablename__ = "visitor_aggregates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    date_bucket: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # YYYY-MM-DD
    channel: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    publication_id: Mapped[Optional[int]] = mapped_column(ForeignKey("publications.id"), nullable=True)
    unique_visitors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    page_views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ClickLog(Base):
    """Registro auditável de clique real em link de afiliado (NUNCA tratado como venda)."""

    __tablename__ = "clicks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    affiliate_link_id: Mapped[Optional[int]] = mapped_column(ForeignKey("affiliate_links.id"), nullable=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    marketplace_id: Mapped[int] = mapped_column(ForeignKey("marketplaces.id"), nullable=False, index=True)
    campaign_id: Mapped[Optional[int]] = mapped_column(ForeignKey("campaigns.id"), nullable=True, index=True)
    publication_id: Mapped[Optional[int]] = mapped_column(ForeignKey("publications.id"), nullable=True)
    channel: Mapped[str] = mapped_column(String(60), default="DIRECT", nullable=False, index=True)
    visitor_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    referrer: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_valid_human: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    clicked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

