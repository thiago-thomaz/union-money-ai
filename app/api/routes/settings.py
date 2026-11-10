"""Rotas de Configurações do Sistema, Pesos do Motor de Score, Autonomia, Conformidade, Logs, Auditoria e Backup."""

from pathlib import Path
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.automation.autonomy import AutonomyManager, OperationalRoutineManager
from app.config import settings
from app.core.compliance import UnionCompliance
from app.core.privacy_lgpd import LGPDPrivacyManager
from app.core.scheduler import union_scheduler
from app.dependencies import get_db_session
from app.intelligence.opportunity import get_configured_scorer
from app.models.audit import AuditLog, SystemLog, SystemSetting
from scripts.backup_db import create_sqlite_backup, verify_backup_integrity

router = APIRouter(tags=["Settings"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent.parent / "templates"))


class ScoringWeightsSchema(BaseModel):
    demand_potential: float = 20.0
    offer_quality: float = 15.0
    estimated_commission: float = 20.0
    competition: float = 10.0
    review_quality: float = 10.0
    content_potential: float = 10.0
    data_reliability: float = 10.0
    availability: float = 5.0


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db_session)):
    scorer = get_configured_scorer(db)
    autonomy = AutonomyManager(db).get_config()
    compliance = UnionCompliance(db).list_checklist()
    routine_intervals = OperationalRoutineManager(db).get_intervals()
    incidents = LGPDPrivacyManager(db).list_security_incidents(limit=15)
    audit_logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(30).all()
    system_logs = db.query(SystemLog).order_by(SystemLog.created_at.desc()).limit(30).all()
    jobs = union_scheduler.list_jobs()
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "page_title": "Configurações, Segurança, Conformidade, Autonomia e Auditoria",
            "weights": scorer.weights,
            "autonomy": autonomy,
            "compliance_checklist": compliance,
            "routine_intervals": routine_intervals,
            "security_incidents": incidents,
            "audit_logs": audit_logs,
            "system_logs": system_logs,
            "scheduler_jobs": jobs,
        },
    )


@router.get("/api/settings/weights")
def api_get_scoring_weights(db: Session = Depends(get_db_session)):
    scorer = get_configured_scorer(db)
    return {"weights": scorer.weights, "default_weights": settings.DEFAULT_SCORING_WEIGHTS}


@router.put("/api/settings/weights")
def api_update_scoring_weights(payload: ScoringWeightsSchema, db: Session = Depends(get_db_session)):
    weights_dict: Dict[str, float] = payload.model_dump()
    if sum(weights_dict.values()) <= 0:
        raise HTTPException(status_code=400, detail="A soma dos pesos deve ser maior que zero.")

    setting = db.query(SystemSetting).filter(SystemSetting.key == "scoring_weights").first()
    if not setting:
        setting = SystemSetting(
            key="scoring_weights",
            value_json=weights_dict,
            description="Pesos configuráveis do Product Opportunity Score (0 a 100)",
        )
        db.add(setting)
    else:
        setting.value_json = weights_dict

    db.add(
        AuditLog(
            actor="admin",
            action="UPDATE_SCORING_WEIGHTS",
            entity_type="SystemSetting",
            entity_id="scoring_weights",
            details=weights_dict,
        )
    )
    db.commit()
    scorer = get_configured_scorer(db)
    return {"status": "UPDATED", "normalized_weights": scorer.weights}


@router.get("/api/settings/logs")
def api_get_logs(limit: int = 50, db: Session = Depends(get_db_session)):
    sys_logs = db.query(SystemLog).order_by(SystemLog.created_at.desc()).limit(limit).all()
    aud_logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()
    return {
        "system_logs": [
            {
                "id": l.id,
                "level": l.level,
                "module": l.module,
                "message": l.message,
                "context": l.context,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in sys_logs
        ],
        "audit_logs": [
            {
                "id": a.id,
                "actor": a.actor,
                "action": a.action,
                "entity_type": a.entity_type,
                "entity_id": a.entity_id,
                "details": a.details,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in aud_logs
        ],
    }


@router.post("/api/settings/backup")
def api_trigger_backup(db: Session = Depends(get_db_session)):
    backup_path = create_sqlite_backup(db=db)
    integrity = verify_backup_integrity(backup_path)
    return {
        "status": "BACKUP_CREATED",
        "backup_path": str(backup_path),
        "integrity": integrity,
    }
