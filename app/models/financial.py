"""Modelos Financeiros: Receitas Confirmadas, Despesas e Histórico de Alterações."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_uid() -> str:
    return str(uuid.uuid4())


class RevenueRecord(Base):
    """Registro oficial de receita confirmada (nunca inclui projeções ou cliques)."""

    __tablename__ = "revenues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    uid: Mapped[str] = mapped_column(String(64), unique=True, default=new_uid, nullable=False, index=True)
    commission_id: Mapped[Optional[int]] = mapped_column(ForeignKey("commissions.id"), nullable=True, index=True)
    marketplace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("marketplaces.id"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(
        String(40), default="CONFIRMED", nullable=False, index=True
    )  # CONFIRMED | REVERSED
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="BRL", nullable=False)
    external_reference: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    change_history: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class Expense(Base):
    """Registro de despesa operacional (sistema inicia sem gastos obrigatórios)."""

    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    uid: Mapped[str] = mapped_column(String(64), unique=True, default=new_uid, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(80), default="INFRASTRUCTURE", nullable=False)
    status: Mapped[str] = mapped_column(
        String(40), default="PAID", nullable=False, index=True
    )  # PENDING | PAID | CANCELLED
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="BRL", nullable=False)
    external_reference: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    change_history: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class FinancialHistory(Base):
    """Tabela relacional imutável do histórico de alterações de qualquer registro financeiro."""

    __tablename__ = "financial_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    record_type: Mapped[str] = mapped_column(
        String(40), nullable=False, index=True
    )  # COMMISSION | REVENUE | EXPENSE | CONVERSION
    record_uid: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    previous_status: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    new_status: Mapped[str] = mapped_column(String(40), nullable=False)
    previous_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    new_amount: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

