"""Modelo de Conversões Confirmadas ou Reportadas."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_uid() -> str:
    return str(uuid.uuid4())


class Conversion(Base):
    """Registro de conversão de venda associada a link/produto de afiliado."""

    __tablename__ = "conversions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    uid: Mapped[str] = mapped_column(String(64), unique=True, default=new_uid, nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    marketplace_id: Mapped[int] = mapped_column(ForeignKey("marketplaces.id"), nullable=False, index=True)
    campaign_id: Mapped[Optional[int]] = mapped_column(ForeignKey("campaigns.id"), nullable=True, index=True)
    click_id: Mapped[Optional[int]] = mapped_column(ForeignKey("clicks.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)  # Ex.: "MERCADOLIVRE_REPORT", "AMAZON_REPORT"
    channel: Mapped[str] = mapped_column(String(60), default="DIRECT", nullable=False, index=True)
    content_format: Mapped[str] = mapped_column(String(60), default="ARTICLE", nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    order_value: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="BRL", nullable=False)
    status: Mapped[str] = mapped_column(
        String(40), default="CONFIRMED", nullable=False, index=True
    )  # PENDING | CONFIRMED | CANCELLED
    external_reference: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    change_history: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

