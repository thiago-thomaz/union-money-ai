"""Modelo de Publicações realizadas nos canais de distribuição."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Publication(Base):
    """Registro de publicação de conteúdo em canal próprio ou rede social."""

    __tablename__ = "publications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("contents.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    campaign_id: Mapped[Optional[int]] = mapped_column(ForeignKey("campaigns.id"), nullable=True, index=True)
    channel: Mapped[str] = mapped_column(
        String(60), nullable=False, index=True
    )  # LANDING_PAGE | YOUTUBE | INSTAGRAM | PINTEREST | EMAIL
    external_post_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    published_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(40), default="PUBLISHED", nullable=False, index=True
    )  # SCHEDULED | PUBLISHED | FAILED | EXPORTED_FOR_MANUAL
    views_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

