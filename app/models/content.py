"""Modelo de Conteúdo Original Produzido pelo Content Engine."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ContentItem(Base):
    """Conteúdo comercial original (artigo SEO, guia, comparativo, roteiro, copy, vídeo, miniatura)."""

    __tablename__ = "contents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    campaign_id: Mapped[Optional[int]] = mapped_column(ForeignKey("campaigns.id"), nullable=True, index=True)
    content_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # ARTICLE | BUYING_GUIDE | COMPARISON | PRODUCT_LIST | EDITORIAL_REVIEW | VIDEO_SCRIPT | SHORT_VIDEO | SOCIAL_CAPTION | SEO_TITLE | PRODUCT_DESCRIPTION | CALL_TO_ACTION | ILLUSTRATIVE_IMAGE | THUMBNAIL
    title: Mapped[str] = mapped_column(String(280), nullable=False)
    slug: Mapped[str] = mapped_column(String(280), nullable=False, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    call_to_action: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    seo_keywords: Mapped[Optional[str]] = mapped_column(String(280), nullable=True)
    meta_description: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    media_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    subtitle_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    aspect_ratio: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    ai_provider_used: Mapped[str] = mapped_column(
        String(60), default="NativePythonProvider", nullable=False
    )
    quality_score: Mapped[float] = mapped_column(Float, default=85.0, nullable=False, index=True)
    quality_breakdown: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    structured_data_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(
        String(40), default="READY", nullable=False, index=True
    )  # DRAFT | READY | PUBLISHED | BLOCKED_LOW_QUALITY | ARCHIVED
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
