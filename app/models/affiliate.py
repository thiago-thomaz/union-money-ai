"""Modelos de Contas de Afiliados e Links Rastreáveis (UNION LINK MANAGER)."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AffiliateAccount(Base):
    """Conta de afiliado associada a um marketplace."""

    __tablename__ = "affiliate_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    marketplace_id: Mapped[int] = mapped_column(ForeignKey("marketplaces.id"), nullable=False, index=True)
    account_label: Mapped[str] = mapped_column(String(120), nullable=False)
    affiliate_tag: Mapped[str] = mapped_column(String(120), nullable=False)
    api_Status: Mapped[str] = mapped_column(
        String(50), default="MANUAL_ONLY", nullable=False
    )  # API_ACTIVE | MANUAL_ONLY | PENDING_APPROVAL
    has_api_credentials: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class AffiliateLink(Base):
    """Link de afiliado autorizado e rastreável pelo UNION LINK MANAGER."""

    __tablename__ = "affiliate_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    marketplace_id: Mapped[int] = mapped_column(ForeignKey("marketplaces.id"), nullable=False, index=True)
    campaign_id: Mapped[Optional[int]] = mapped_column(ForeignKey("campaigns.id"), nullable=True, index=True)
    channel: Mapped[str] = mapped_column(String(60), default="SITE", nullable=False, index=True)
    short_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    original_product_url: Mapped[str] = mapped_column(Text, nullable=False)
    affiliate_url: Mapped[str] = mapped_column(Text, nullable=False)
    utm_source: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    utm_medium: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    utm_campaign: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    validity_status: Mapped[str] = mapped_column(
        String(40), default="VALID", nullable=False
    )  # VALID | INVALID | UNVERIFIED
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
