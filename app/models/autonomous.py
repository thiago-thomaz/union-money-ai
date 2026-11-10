"""Modelos da Fase 4 — UNION CONNECT, Pipeline Autônomo de 9 Estados e Fila Persistente 24/7."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_uid() -> str:
    return str(uuid.uuid4())


class IntegrationStatusIndicator:
    """Indicadores individuais de cada integração (Seção 11)."""

    ACTIVE = "ACTIVE"
    AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
    PENDING = "PENDING"
    ERROR = "ERROR"
    DISABLED = "DISABLED"


class PipelineStage:
    """Estados oficiais do pipeline autônomo de produção de conteúdo (Seção 6)."""

    DISCOVERY = "DISCOVERY"
    ANALYSIS = "ANALYSIS"
    SCRIPT = "SCRIPT"
    CONTENT = "CONTENT"
    QUALITY_CHECK = "QUALITY_CHECK"
    SEO = "SEO"
    READY = "READY"
    PUBLISHED = "PUBLISHED"
    MONITORING = "MONITORING"

    ORDERED_STAGES = (
        DISCOVERY,
        ANALYSIS,
        SCRIPT,
        CONTENT,
        QUALITY_CHECK,
        SEO,
        READY,
        PUBLISHED,
        MONITORING,
    )


class IntegrationCredentialToken(Base):
    """Armazenamento seguro e estado de conectividade do UNION CONNECT (Seções 3 e 11)."""

    __tablename__ = "integration_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    connector_slug: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    connector_name: Mapped[str] = mapped_column(String(120), nullable=False)
    connector_category: Mapped[str] = mapped_column(
        String(40), default="MARKETPLACE", nullable=False
    )  # MARKETPLACE | SOCIAL | ANALYTICS | INTERNAL
    auth_method: Mapped[str] = mapped_column(
        String(40), default="OAUTH2", nullable=False
    )  # OAUTH2 | HMAC_SHA256 | AWS_SIGV4 | NATIVE
    status_indicator: Mapped[str] = mapped_column(
        String(40), default=IntegrationStatusIndicator.AUTHORIZATION_REQUIRED, nullable=False, index=True
    )  # ACTIVE | AUTHORIZATION_REQUIRED | PENDING | ERROR | DISABLED
    authorization_block_status: Mapped[str] = mapped_column(
        String(60), default="BLOQUEADA POR AUTORIZAÇÃO", nullable=False
    )  # OPERACIONAL | BLOQUEADA POR AUTORIZAÇÃO | DESATIVADA
    masked_token_preview: Mapped[str] = mapped_column(String(80), default="<NOT_CONFIGURED>", nullable=False)
    encrypted_access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    encrypted_refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    required_scopes: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    granted_scopes: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    auto_renew_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_renewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class ContentProductionPipeline(Base):
    """Rastreamento persistente do pipeline autônomo de 9 estágios (Seção 6)."""

    __tablename__ = "content_production_pipeline"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    pipeline_uid: Mapped[str] = mapped_column(String(64), unique=True, default=new_uid, nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    content_id: Mapped[Optional[int]] = mapped_column(ForeignKey("contents.id"), nullable=True, index=True)
    video_content_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    publication_id: Mapped[Optional[int]] = mapped_column(ForeignKey("publications.id"), nullable=True, index=True)
    current_state: Mapped[str] = mapped_column(
        String(40), default=PipelineStage.DISCOVERY, nullable=False, index=True
    )
    buyer_intent: Mapped[str] = mapped_column(
        String(60), default="COMMERCIAL_INVESTIGATION", nullable=False
    )
    quality_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_stale_refresh: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    state_history: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class PersistentOrchestratorQueue(Base):
    """Fila persistente no banco de dados para o UNION AUTONOMOUS ORCHESTRATOR 24/7 (Seções 10 e 12)."""

    __tablename__ = "persistent_orchestrator_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_uid: Mapped[str] = mapped_column(String(64), unique=True, default=new_uid, nullable=False, index=True)
    cycle_type: Mapped[str] = mapped_column(
        String(40), default="EVERY_6_HOURS", nullable=False, index=True
    )  # EVERY_6_HOURS | DAILY | WEEKLY | MONTHLY | EVENT_DRIVEN
    task_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(40), default="QUEUED", nullable=False, index=True
    )  # QUEUED | RUNNING | COMPLETED | FAILED | RECOVERED
    priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    payload_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    result_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    locked_by: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

