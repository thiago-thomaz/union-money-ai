"""Controles de Emergência — STOP ALL AUTOMATIONS e Desativação Imediata de Integrações (Seções 4 e 5)."""

from datetime import datetime, timezone
from typing import Any, Dict
from sqlalchemy.orm import Session
from app.core.logging import logger
from app.core.scheduler import union_scheduler
from app.models.audit import AuditLog, SystemSetting
from app.models.autopilot import EditorialQueueItem, EditorialState
from app.models.compliance import CompliancePolicyRecord
from app.models.marketplace import Marketplace


def is_emergency_stopped(db: Session) -> bool:
    """Verifica se o modo de parada de emergência (STOP ALL AUTOMATIONS) está ativo."""
    setting = db.query(SystemSetting).filter(SystemSetting.key == "autonomy_config").first()
    if setting and isinstance(setting.value_json, dict):
        return bool(setting.value_json.get("emergency_stop", False))
    return False


def trigger_stop_all_automations(
    db: Session,
    actor: str = "admin",
    reason: str = "Acionamento do botão de emergência STOP ALL AUTOMATIONS",
) -> Dict[str, Any]:
    """Suspende todas as tarefas agendadas, interrompe publicações pendentes, preserva dados e mantém o painel acessível."""
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Suspende jobs agendados no APScheduler se estiver rodando
    scheduler_stopped = False
    try:
        if union_scheduler.scheduler.running:
            union_scheduler.shutdown()
            scheduler_stopped = True
    except Exception as exc:
        logger.warning("Aviso ao encerrar agendador durante STOP ALL AUTOMATIONS: %s", exc)

    # 2. Atualiza configuração de autonomia marcando emergency_stop = True
    setting = db.query(SystemSetting).filter(SystemSetting.key == "autonomy_config").first()
    current_cfg = dict(setting.value_json) if (setting and isinstance(setting.value_json, dict)) else {}
    current_cfg["emergency_stop"] = True
    current_cfg["emergency_stopped_at"] = now_iso
    current_cfg["emergency_reason"] = reason
    if not setting:
        setting = SystemSetting(
            key="autonomy_config",
            value_json=current_cfg,
            description="Configuração de nível de autonomia operacional e botão de emergência",
        )
        db.add(setting)
    else:
        setting.value_json = current_cfg

    # 3. Interrompe publicações pendentes na fila editorial (volta para EM_REVISAO sem apagar dados)
    pending_items = (
        db.query(EditorialQueueItem)
        .filter(EditorialQueueItem.state.in_([EditorialState.APROVADO, EditorialState.AGENDADO]))
        .all()
    )
    interrupted_queue_ids = []
    for item in pending_items:
        item.state = EditorialState.EM_REVISAO
        item.require_human_approval = True
        interrupted_queue_ids.append(item.id)

    # 4. Registra auditoria obrigatória
    details = {
        "timestamp": now_iso,
        "reason": reason,
        "scheduler_suspended": scheduler_stopped,
        "interrupted_publications_count": len(interrupted_queue_ids),
        "interrupted_queue_ids": interrupted_queue_ids,
        "data_preserved": True,
        "dashboard_accessible": True,
    }
    db.add(
        AuditLog(
            actor=actor,
            action="STOP_ALL_AUTOMATIONS",
            entity_type="SystemSetting",
            entity_id="autonomy_config",
            details=details,
        )
    )
    db.commit()
    logger.warning("STOP ALL AUTOMATIONS acionado por '%s': %s", actor, reason)

    return {
        "status": "EMERGENCY_STOP_ACTIVE",
        "emergency_stop": True,
        **details,
    }


def resume_automations(
    db: Session,
    actor: str = "admin",
    reason: str = "Retomada manual autorizada pelo administrador",
) -> Dict[str, Any]:
    """Desativa o bloqueio de emergência mediante ação explícita do administrador."""
    now_iso = datetime.now(timezone.utc).isoformat()
    setting = db.query(SystemSetting).filter(SystemSetting.key == "autonomy_config").first()
    current_cfg = dict(setting.value_json) if (setting and isinstance(setting.value_json, dict)) else {}
    current_cfg["emergency_stop"] = False
    current_cfg["resumed_at"] = now_iso

    if not setting:
        setting = SystemSetting(
            key="autonomy_config",
            value_json=current_cfg,
            description="Configuração de nível de autonomia operacional e botão de emergência",
        )
        db.add(setting)
    else:
        setting.value_json = current_cfg

    db.add(
        AuditLog(
            actor=actor,
            action="RESUME_AUTOMATIONS",
            entity_type="SystemSetting",
            entity_id="autonomy_config",
            details={"timestamp": now_iso, "reason": reason},
        )
    )
    db.commit()
    return {
        "status": "AUTOMATIONS_RESUMED",
        "emergency_stop": False,
        "resumed_at": now_iso,
    }


def disable_integration_immediately(
    db: Session,
    target_slug: str,
    actor: str = "admin",
    reason: str = "Desativação imediata de marketplace/canal",
) -> Dict[str, Any]:
    """Desativa imediatamente qualquer marketplace ou canal e bloqueia recursos associados."""
    slug = target_slug.lower().strip()
    mkt = db.query(Marketplace).filter(Marketplace.slug == slug).first()
    mkt_disabled = False
    if mkt:
        mkt.is_active = False
        mkt.integration_status = "DISABLED_IMMEDIATELY"
        mkt_disabled = True

    comp = db.query(CompliancePolicyRecord).filter(CompliancePolicyRecord.target_slug == slug).first()
    comp_blocked = False
    if comp:
        comp.is_integration_enabled = False
        comp_blocked = True

    if not mkt_disabled and not comp_blocked:
        raise ValueError(f"Integração ou canal '{slug}' não encontrado.")

    db.add(
        AuditLog(
            actor=actor,
            action="DISABLE_INTEGRATION_IMMEDIATELY",
            entity_type="Integration",
            entity_id=slug,
            details={
                "target_slug": slug,
                "marketplace_disabled": mkt_disabled,
                "compliance_blocked": comp_blocked,
                "reason": reason,
            },
        )
    )
    db.commit()
    return {
        "status": "INTEGRATION_DISABLED",
        "target_slug": slug,
        "marketplace_disabled": mkt_disabled,
        "compliance_blocked": comp_blocked,
    }
