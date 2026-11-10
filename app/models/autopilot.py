"""Modelos do UNION AUTOPILOT, Fila Editorial e Monitoramento de Alertas (Parte 2)."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EditorialState:
    """Estados oficiais da fila editorial (Seção 8)."""

    RASCUNHO = "RASCUNHO"
    EM_REVISAO = "EM_REVISAO"
    APROVADO = "APROVADO"
    AGENDADO = "AGENDADO"
    PUBLICADO = "PUBLICADO"
    FALHOU = "FALHOU"
    ARQUIVADO = "ARQUIVADO"


class AutopilotTaskRun(Base):
    """Registro auditável de execução de tarefas do UNION AUTOPILOT com idempotência e recuperação."""

    __tablename__ = "autopilot_task_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    task_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(140), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(40), default="RUNNING", nullable=False, index=True
    )  # RUNNING | COMPLETED | FAILED | RECOVERED | SKIPPED_DUPLICATE
    attempt_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    duration_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_summary: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class EditorialQueueItem(Base):
    """Fila editorial com controle de qualidade, aprovação humana/automática e deduplicação."""

    __tablename__ = "editorial_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    content_id: Mapped[Optional[int]] = mapped_column(ForeignKey("contents.id"), nullable=True, index=True)
    campaign_id: Mapped[Optional[int]] = mapped_column(ForeignKey("campaigns.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(280), nullable=False)
    content_format: Mapped[str] = mapped_column(String(60), default="ARTICLE", nullable=False)
    target_channel: Mapped[str] = mapped_column(String(60), default="SITE", nullable=False, index=True)
    search_intent: Mapped[str] = mapped_column(String(60), default="COMMERCIAL_INVESTIGATION", nullable=False)
    target_keyword: Mapped[Optional[str]] = mapped_column(String(180), nullable=True)
    quality_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    require_human_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    state: Mapped[str] = mapped_column(
        String(40), default=EditorialState.RASCUNHO, nullable=False, index=True
    )  # RASCUNHO | EM_REVISAO | APROVADO | AGENDADO | PUBLICADO | FALHOU | ARQUIVADO
    dedup_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    external_post_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    published_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    package_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class SystemAlert(Base):
    """Alertas operacionais e de monitoramento automático do sistema (Seção 11)."""

    __tablename__ = "system_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    severity: Mapped[str] = mapped_column(
        String(20), default="WARNING", nullable=False, index=True
    )  # INFO | WARNING | CRITICAL
    category: Mapped[str] = mapped_column(
        String(40), nullable=False, index=True
    )  # APP | DATABASE | DISK | MEMORY | PROCESS | SCHEDULER | LINK | PUBLICATION | INTEGRATION | EXECUTION
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    notified_email: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    context: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

