"""Modelos de Conformidade (UNION COMPLIANCE), Privacidade/LGPD e Histórico de Backups (Parte 3)."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CompliancePolicyRecord(Base):
    """Registro de verificação de políticas de cada marketplace e canal de distribuição (Seção 5)."""

    __tablename__ = "compliance_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    target_slug: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    target_name: Mapped[str] = mapped_column(String(120), nullable=False)
    target_type: Mapped[str] = mapped_column(String(40), default="MARKETPLACE", nullable=False)  # MARKETPLACE | CHANNEL
    eligibility_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    authorization_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    permissions_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rate_limits_verified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    disclosure_rules_verified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    image_usage_verified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    brand_usage_verified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ad_rules_verified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    publishing_rules_verified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    attribution_rules_verified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_integration_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    validity_days: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    last_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ConsentRecord(Base):
    """Registro auditável de consentimento e preferências de privacidade LGPD (Seção 6)."""

    __tablename__ = "lgpd_consents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    subject_identifier_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(120), nullable=False)  # ESSENTIAL_COOKIES | OPTIN_NEWSLETTER | CONTACT
    consent_granted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    legal_basis: Mapped[str] = mapped_column(String(60), default="CONSENTIMENTO_EXPLICITO", nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class SecurityIncident(Base):
    """Registro de incidentes de segurança e privacidade (Seções 4 e 6)."""

    __tablename__ = "security_incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    severity: Mapped[str] = mapped_column(String(30), default="MEDIUM", nullable=False, index=True)
    incident_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    mitigation_applied: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class BackupRecord(Base):
    """Histórico auditável de backups locais e verificações de integridade (Seção 7)."""

    __tablename__ = "backup_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    backup_filename: Mapped[str] = mapped_column(String(180), nullable=False)
    db_backup_path: Mapped[str] = mapped_column(Text, nullable=False)
    settings_backup_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contents_backup_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    integrity_verified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

