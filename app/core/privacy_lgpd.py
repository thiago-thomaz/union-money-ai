"""Privacidade, Proteção de Dados e Conformidade com a LGPD (Seção 6).

Recursos:
- Registro de consentimento explícito com hash de identificador e prazo de retenção.
- Direito ao esquecimento / exclusão completa de dados pessoais (consentimentos e registros associados).
- Política de retenção automática para expurgo de registros vencidos.
- Registro e listagem de incidentes de segurança.
"""

from datetime import datetime, timedelta, timezone
import hashlib
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from app.models.audit import AuditLog
from app.models.click import ClickLog
from app.models.compliance import ConsentRecord, SecurityIncident


class LGPDPrivacyManager:
    """Gerenciador de privacidade, consentimento, retenção e incidentes segundo a LGPD."""

    DEFAULT_RETENTION_DAYS = 365

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _hash_subject(subject_identifier: str) -> str:
        clean = subject_identifier.strip().lower()
        return hashlib.sha256(clean.encode("utf-8")).hexdigest()

    def record_consent(
        self,
        subject_identifier: str,
        purpose: str = "NEWSLETTER_OFERTAS",
        consent_granted: bool = True,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        retention_days: int = DEFAULT_RETENTION_DAYS,
    ) -> ConsentRecord:
        """Registra consentimento explícito do titular com minimização de dados (hash SHA-256)."""
        identifier = subject_identifier.strip().lower()
        if not identifier:
            raise ValueError("Identificador do titular é obrigatório para registro de consentimento.")

        subj_hash = self._hash_subject(identifier)
        rec = ConsentRecord(
            subject_identifier_hash=subj_hash,
            purpose=purpose,
            consent_granted=bool(consent_granted),
            legal_basis="CONSENTIMENTO_EXPLICITO",
            revoked_at=None if consent_granted else datetime.now(timezone.utc),
        )
        self.db.add(rec)
        self.db.commit()
        self.db.refresh(rec)
        return rec

    def delete_subject_data(self, subject_identifier: str, actor: str = "titular_lgpd") -> Dict[str, Any]:
        """Executa exclusão definitiva de dados pessoais (Consentimentos e hashes associados) mediante solicitação."""
        identifier = subject_identifier.strip().lower()
        if not identifier:
            raise ValueError("Identificador inválido para exclusão.")

        subj_hash = self._hash_subject(identifier)
        deleted_consents = (
            self.db.query(ConsentRecord)
            .filter(ConsentRecord.subject_identifier_hash.in_([subj_hash, identifier]))
            .delete(synchronize_session=False)
        )
        deleted_clicks = (
            self.db.query(ClickLog)
            .filter(ClickLog.visitor_fingerprint.in_([subj_hash[:32], identifier]))
            .delete(synchronize_session=False)
        )

        self.db.add(
            AuditLog(
                actor=actor,
                action="LGPD_DATA_DELETION",
                entity_type="PersonalData",
                entity_id=subj_hash[:10],
                details={
                    "consents_deleted": deleted_consents,
                    "clicks_deleted": deleted_clicks,
                },
            )
        )
        self.db.commit()
        return {
            "status": "PERSONAL_DATA_DELETED",
            "consents_deleted": deleted_consents,
            "clicks_deleted": deleted_clicks,
        }

    def enforce_retention_policy(self, default_days: int = DEFAULT_RETENTION_DAYS) -> Dict[str, int]:
        """Remove dados pessoais cujo prazo de retenção expirou."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, default_days))
        expired_consents = (
            self.db.query(ConsentRecord)
            .filter(ConsentRecord.created_at < cutoff)
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return {
            "expired_consents_purged": expired_consents,
        }

    def record_security_incident(
        self,
        severity: str,
        incident_type: str,
        description: str,
        mitigation_applied: Optional[str] = None,
        affected_records_count: int = 0,
        actor: str = "system",
    ) -> SecurityIncident:
        """Registra um incidente de segurança ou privacidade para auditoria e resposta."""
        inc = SecurityIncident(
            severity=severity.upper().strip(),
            incident_type=incident_type.upper().strip(),
            description=description,
            mitigation_applied=mitigation_applied or "Em análise pela equipe de segurança.",
            details={
                "affected_records_count": max(0, affected_records_count),
                "resolved": bool(mitigation_applied),
            },
        )
        self.db.add(inc)
        self.db.add(
            AuditLog(
                actor=actor,
                action="RECORD_SECURITY_INCIDENT",
                entity_type="SecurityIncident",
                entity_id=inc.incident_type,
                details={
                    "severity": inc.severity,
                    "affected_records_count": max(0, affected_records_count),
                },
            )
        )
        self.db.commit()
        self.db.refresh(inc)
        return inc

    def list_security_incidents(self, limit: int = 50) -> List[Dict[str, Any]]:
        rows = (
            self.db.query(SecurityIncident)
            .order_by(SecurityIncident.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "severity": r.severity,
                "incident_type": r.incident_type,
                "description": r.description,
                "mitigation_applied": r.mitigation_applied,
                "affected_records_count": (r.details or {}).get("affected_records_count", 0),
                "resolved": (r.details or {}).get("resolved", True),
                "occurred_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
