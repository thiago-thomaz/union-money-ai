"""Rotas de Segurança, STOP ALL AUTOMATIONS, Conformidade, LGPD, Autonomia Operacional, Rotinas e Restauração."""

from pathlib import Path
from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.automation.autonomy import AutonomyManager, OperationalRoutineManager
from app.config import settings
from app.core.compliance import UnionCompliance
from app.core.emergency import (
    disable_integration_immediately,
    is_emergency_stopped,
    resume_automations,
    trigger_stop_all_automations,
)
from app.core.privacy_lgpd import LGPDPrivacyManager
from app.core.security import (
    generate_csrf_token,
    scan_codebase_for_hardcoded_secrets,
    sensitive_rate_limiter,
)
from app.dependencies import get_db_session
from scripts.restore_db import restore_sqlite_backup

router = APIRouter(tags=["Security & Compliance"])


class StopAutomationsSchema(BaseModel):
    actor: str = "admin"
    reason: str = "Botão de emergência STOP ALL AUTOMATIONS acionado"


class DisableIntegrationSchema(BaseModel):
    actor: str = "admin"
    reason: str = "Desativação imediata de marketplace/canal"


class ComplianceUpdateSchema(BaseModel):
    terms_accepted: Optional[bool] = None
    is_feature_blocked: Optional[bool] = None
    daily_limit: Optional[int] = None
    validity_days: Optional[int] = None
    mark_verified_now: bool = True


class ConsentCreateSchema(BaseModel):
    subject_identifier: str = Field(..., min_length=3)
    purpose: str = "NEWSLETTER_OFERTAS"
    consent_granted: bool = True
    retention_days: int = 365


class SecurityIncidentCreateSchema(BaseModel):
    severity: str = "MEDIUM"
    incident_type: str = Field(..., min_length=3)
    description: str = Field(..., min_length=5)
    mitigation_applied: Optional[str] = None
    affected_records_count: int = 0


class AutonomyConfigUpdateSchema(BaseModel):
    level: str = "LEVEL_2_SEMIAUTOMATIC"
    daily_publication_limit: Optional[int] = 20


class AutonomyEvaluationSchema(BaseModel):
    action_type: str
    target_channel: str = "SITE"
    content_quality_score: float = 100.0


class RestoreBackupSchema(BaseModel):
    backup_path: str
    expected_sha256: Optional[str] = None


@router.get("/api/security/status")
def api_security_status(db: Session = Depends(get_db_session)):
    return {
        "emergency_stop_active": is_emergency_stopped(db),
        "csrf_protection_enabled": True,
        "rate_limiting_enabled": True,
        "secret_scan": scan_codebase_for_hardcoded_secrets(settings.base_dir / "app"),
    }


@router.get("/api/security/csrf-token")
def api_get_csrf_token():
    return {"csrf_token": generate_csrf_token()}


@router.post("/api/security/stop-all-automations")
def api_stop_all_automations(
    payload: Optional[StopAutomationsSchema] = None,
    request: Request = None,
    db: Session = Depends(get_db_session),
):
    client_ip = request.client.host if (request and request.client) else "local"
    rl = sensitive_rate_limiter.check_allowed(f"stop_all:{client_ip}")
    if not rl["allowed"]:
        raise HTTPException(status_code=429, detail="Limite de requisições excedido para este endpoint.")

    actor = payload.actor if payload else "admin"
    reason = payload.reason if payload else "Botão de emergência STOP ALL AUTOMATIONS acionado"
    return trigger_stop_all_automations(db=db, actor=actor, reason=reason)


@router.post("/api/security/resume-automations")
def api_resume_automations(
    payload: Optional[StopAutomationsSchema] = None,
    db: Session = Depends(get_db_session),
):
    actor = payload.actor if payload else "admin"
    reason = payload.reason if payload else "Retomada manual autorizada pelo administrador"
    return resume_automations(db=db, actor=actor, reason=reason)


@router.post("/api/security/integrations/{target_slug}/disable")
def api_disable_integration(
    target_slug: str,
    payload: Optional[DisableIntegrationSchema] = None,
    db: Session = Depends(get_db_session),
):
    try:
        return disable_integration_immediately(
            db=db,
            target_slug=target_slug,
            actor=payload.actor if payload else "admin",
            reason=payload.reason if payload else "Desativação imediata",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/compliance/checklist")
def api_list_compliance_checklist(db: Session = Depends(get_db_session)):
    return UnionCompliance(db).list_checklist()


@router.put("/api/compliance/checklist/{target_slug}")
def api_update_compliance_checklist(
    target_slug: str,
    payload: ComplianceUpdateSchema,
    db: Session = Depends(get_db_session),
):
    try:
        return UnionCompliance(db).verify_or_update_policy(
            target_slug=target_slug,
            terms_accepted=payload.terms_accepted,
            is_feature_blocked=payload.is_feature_blocked,
            daily_limit=payload.daily_limit,
            validity_days=payload.validity_days,
            mark_verified_now=payload.mark_verified_now,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/lgpd/consent", status_code=status.HTTP_201_CREATED)
def api_record_lgpd_consent(
    payload: ConsentCreateSchema,
    request: Request,
    db: Session = Depends(get_db_session),
):
    try:
        rec = LGPDPrivacyManager(db).record_consent(
            subject_identifier=payload.subject_identifier,
            purpose=payload.purpose,
            consent_granted=payload.consent_granted,
            ip_address=request.client.host if request.client else "127.0.0.1",
            user_agent=request.headers.get("user-agent", "unknown"),
            retention_days=payload.retention_days,
        )
        return {
            "id": rec.id,
            "subject_identifier_hash": rec.subject_identifier_hash,
            "purpose": rec.purpose,
            "consent_granted": rec.consent_granted,
            "legal_basis": rec.legal_basis,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/lgpd/subject/{identifier}")
def api_delete_lgpd_subject(identifier: str, db: Session = Depends(get_db_session)):
    try:
        return LGPDPrivacyManager(db).delete_subject_data(identifier)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/lgpd/retention/enforce")
def api_enforce_lgpd_retention(default_days: int = 365, db: Session = Depends(get_db_session)):
    return LGPDPrivacyManager(db).enforce_retention_policy(default_days=default_days)


@router.post("/api/lgpd/incidents", status_code=status.HTTP_201_CREATED)
def api_create_security_incident(
    payload: SecurityIncidentCreateSchema,
    db: Session = Depends(get_db_session),
):
    inc = LGPDPrivacyManager(db).record_security_incident(
        severity=payload.severity,
        incident_type=payload.incident_type,
        description=payload.description,
        mitigation_applied=payload.mitigation_applied,
        affected_records_count=payload.affected_records_count,
    )
    return {
        "id": inc.id,
        "severity": inc.severity,
        "incident_type": inc.incident_type,
        "resolved": bool((inc.details or {}).get("resolved", True)),
    }


@router.get("/api/lgpd/incidents")
def api_list_security_incidents(db: Session = Depends(get_db_session)):
    return LGPDPrivacyManager(db).list_security_incidents()


@router.get("/api/autonomy/config")
def api_get_autonomy_config(db: Session = Depends(get_db_session)):
    return AutonomyManager(db).get_config()


@router.put("/api/autonomy/config")
def api_update_autonomy_config(
    payload: AutonomyConfigUpdateSchema,
    db: Session = Depends(get_db_session),
):
    try:
        return AutonomyManager(db).set_level(
            level_code=payload.level,
            daily_publication_limit=payload.daily_publication_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/autonomy/evaluate")
def api_evaluate_autonomy_permission(
    payload: AutonomyEvaluationSchema,
    db: Session = Depends(get_db_session),
):
    return AutonomyManager(db).evaluate_action_permission(
        action_type=payload.action_type,
        target_channel=payload.target_channel,
        content_quality_score=payload.content_quality_score,
    )


@router.get("/api/autonomy/routines/intervals")
def api_get_routine_intervals(db: Session = Depends(get_db_session)):
    return OperationalRoutineManager(db).get_intervals()


@router.put("/api/autonomy/routines/intervals")
def api_update_routine_intervals(
    payload: Dict[str, int],
    db: Session = Depends(get_db_session),
):
    return OperationalRoutineManager(db).update_intervals(payload)


@router.post("/api/autonomy/routines/{period}/run")
def api_run_operational_routine(period: str, db: Session = Depends(get_db_session)):
    try:
        return OperationalRoutineManager(db).run_routine(period)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/settings/restore")
def api_restore_database_backup(payload: RestoreBackupSchema):
    try:
        return restore_sqlite_backup(
            backup_path=Path(payload.backup_path),
            expected_sha256=payload.expected_sha256,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
