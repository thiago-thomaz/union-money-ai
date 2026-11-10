"""Modelo de Comissões (Pendentes, Aprovadas, Canceladas, Pagas)."""

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


class Commission(Base):
    """Registro financeiro de comissão de afiliado (sem jamais misturar com comissão fictícia)."""

    __tablename__ = "commissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    uid: Mapped[str] = mapped_column(String(64), unique=True, default=new_uid, nullable=False, index=True)
    conversion_id: Mapped[Optional[int]] = mapped_column(ForeignKey("conversions.id"), nullable=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    marketplace_id: Mapped[int] = mapped_column(ForeignKey("marketplaces.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(40), default="PENDING", nullable=False, index=True
    )  # PENDING | APPROVED | CANCELLED | PAID
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="BRL", nullable=False)
    announced_rate_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    effective_rate_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    external_reference: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    change_history: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

