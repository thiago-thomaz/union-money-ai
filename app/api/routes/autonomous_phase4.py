"""Rotas REST da Fase 4 — Autonomia Total e Operação Comercial 24/7.

Expõe:
- UNION CONNECT (Central de Integrações Automáticas, OAuth, Renovação, Permissões e Status)
- AutonomousProductDiscovery (Descoberta incremental 100% automática sem formulários manuais)
- AutonomousContentPipeline (Pipeline de 9 estados + atualização de artigos antigos)
- AutoSalesTracker (Webhooks assinados, API de relatórios e conciliação sem upload manual de CSV)
- UNION GROWTH AI (Otimização comercial automática com travas de segurança financeira)
- UNION AUTONOMOUS ORCHESTRATOR & Supervisor 24/7 (Ciclos 6h/diário/semanal/mensal e fila persistente)
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.automation.autonomous_orchestrator import UnionAutonomousOrchestrator
from app.content_engine.autonomous_pipeline import AutonomousContentPipeline
from app.dependencies import get_db_session as get_db
from app.finance.auto_sales_tracker import AutoSalesTracker, PLATFORM_REPORT_CAPABILITIES
from app.integrations.union_connect import UnionConnect
from app.intelligence.autonomous_discovery import AutonomousProductDiscovery
from app.intelligence.union_growth_ai import UnionGrowthAI
from app.models.autonomous import ContentProductionPipeline
from app.models.product import Product
from scripts.keep_alive_runner import inspect_execution_infrastructure


router = APIRouter(tags=["Phase 4 - Autonomous 24/7"])


class StoreOAuthTokenPayload(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    expires_in_seconds: int = 21600
    granted_scopes: Optional[List[str]] = None


class AutonomousDiscoveryPayload(BaseModel):
    keywords: Optional[List[str]] = None
    limit_per_query: int = 2


class AutonomousPipelineRunPayload(BaseModel):
    channels: Optional[List[str]] = None


# ==================================================
# 1. UNION CONNECT — CENTRAL DE INTEGRAÇÕES
# ==================================================

@router.get("/api/connect/status")
def list_all_integrations_status(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Retorna o status em tempo real de todos os conectores A..H do UNION CONNECT."""
    connect = UnionConnect(db)
    return {
        "connectors": connect.list_all_connectors(),
        "autonomy_flags": connect.get_autonomy_flags_status(),
        "commercial_audit_matrix": connect.get_commercial_integration_audit_matrix(),
    }


@router.get("/api/connect/commercial-audit-matrix")
def get_commercial_integration_audit_matrix(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Retorna a classificação oficial REALMENTE FUNCIONAL | PENDENTE DE CREDENCIAIS | NÃO SUPORTADA."""
    return {"matrix": UnionConnect(db).get_commercial_integration_audit_matrix()}


@router.get("/api/connect/autonomy-flags")
def get_autonomy_flags(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Retorna as variáveis de operação autônoma configuradas no ambiente."""
    return UnionConnect(db).get_autonomy_flags_status()


@router.get("/api/connect/oauth-url/{connector_slug}")
def build_connector_oauth_url(
    connector_slug: str,
    redirect_uri: Optional[str] = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Gera URL oficial de autorização OAuth2 para ativação inicial única pelo proprietário."""
    try:
        return UnionConnect(db).get_oauth_authorization_url(connector_slug, redirect_uri=redirect_uri)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/connect/token/{connector_slug}")
def save_connector_oauth_token(
    connector_slug: str,
    payload: StoreOAuthTokenPayload,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Armazena token OAuth criptografado com controle de escopos e expiração."""
    try:
        return UnionConnect(db).store_authorized_token(
            connector_slug=connector_slug,
            access_token=payload.access_token,
            refresh_token=payload.refresh_token,
            granted_scopes=payload.granted_scopes,
            expires_in_seconds=payload.expires_in_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/connect/renew/{connector_slug}")
def renew_connector_token(
    connector_slug: str,
    force: bool = False,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Renova automaticamente o token de acesso via refresh_token quando suportado."""
    return UnionConnect(db).renew_token_if_needed(connector_slug, force=force)


@router.post("/api/connect/reconnect/{connector_slug}")
def reconnect_connector(connector_slug: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Tenta reconexão segura de uma integração em estado de erro ou expirada."""
    return UnionConnect(db).reconnect_connector(connector_slug)


@router.post("/api/connect/disable/{connector_slug}")
def disable_connector_safely(
    connector_slug: str,
    reason: str = "Desativação segura solicitada.",
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Desativa uma integração com segurança."""
    return UnionConnect(db).disable_connector_safely(connector_slug, reason=reason)


# ==================================================
# 2. DESCOBERTA AUTÔNOMA E PIPELINE DE CONTEÚDO
# ==================================================

@router.post("/api/autonomous/discovery/run")
def run_autonomous_product_discovery(
    payload: AutonomousDiscoveryPayload,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Executa descoberta incremental automática de produtos, links oficiais e scores."""
    discovery = AutonomousProductDiscovery(db)
    return discovery.run_continuous_discovery_cycle(
        queries=payload.keywords,
        limit_per_query=payload.limit_per_query,
    )


@router.post("/api/autonomous/discovery/suspend-stale")
def suspend_stale_or_invalid_products(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Suspende automaticamente produtos indisponíveis, com preço zerado ou comissão inválida."""
    return AutonomousProductDiscovery(db).suspend_invalid_or_uninteresting_products()


@router.post("/api/autonomous/pipeline/run/{product_id}")
def run_autonomous_content_pipeline(
    product_id: int,
    payload: Optional[AutonomousPipelineRunPayload] = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Executa a máquina de 9 estados (DISCOVERY -> ... -> PUBLISHED -> MONITORING)."""
    prod = db.query(Product).filter(Product.id == product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail=f"Produto {product_id} não encontrado.")
    channels = payload.channels if payload else None
    return AutonomousContentPipeline(db).execute_for_product(
        product=prod,
        target_channels=channels,
    )


@router.post("/api/autonomous/pipeline/refresh-stale")
def refresh_outdated_published_contents(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Atualiza automaticamente conteúdos antigos quando preço ou disponibilidade mudam."""
    return AutonomousContentPipeline(db).refresh_outdated_contents()


@router.get("/api/autonomous/pipeline/list")
def list_content_pipelines(limit: int = 50, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Lista os pipelines autônomos de conteúdo e seus respectivos estágios."""
    rows = (
        db.query(ContentProductionPipeline)
        .order_by(ContentProductionPipeline.id.desc())
        .limit(limit)
        .all()
    )
    return {
        "pipelines": [
            {
                "id": r.id,
                "pipeline_uid": r.pipeline_uid,
                "product_id": r.product_id,
                "content_id": r.content_id,
                "video_content_id": r.video_content_id,
                "publication_id": r.publication_id,
                "current_state": r.current_state,
                "buyer_intent": r.buyer_intent,
                "quality_score": r.quality_score,
                "state_history": r.state_history,
            }
            for r in rows
        ]
    }


# ==================================================
# 3. AUTO SALES TRACKER & WEBHOOKS DE COMISSÕES
# ==================================================

@router.get("/api/autonomous/sales/capabilities")
def get_sales_tracking_capabilities() -> Dict[str, Any]:
    """Documenta de forma transparente os mecanismos reais de leitura de vendas por plataforma."""
    return {"capabilities": PLATFORM_REPORT_CAPABILITIES}


@router.post("/api/webhooks/conversions/{marketplace_slug}")
def receive_marketplace_conversion_webhook(
    marketplace_slug: str,
    payload: Dict[str, Any],
    x_hub_signature_256: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Recebe postback/webhook assinado de conversão ou comissão sem necessidade de CSV manual."""
    tracker = AutoSalesTracker(db)
    try:
        return tracker.process_official_webhook(
            marketplace_slug=marketplace_slug,
            payload=payload,
            signature_header=x_hub_signature_256,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/autonomous/sales/sync")
def sync_all_authorized_sales_and_commissions(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Sincroniza automaticamente vendas e comissões das plataformas autorizadas."""
    return AutoSalesTracker(db).sync_from_official_apis()


# ==================================================
# 4. UNION GROWTH AI & ORQUESTRADOR 24/7
# ==================================================

@router.get("/api/autonomous/growth-ai")
def get_growth_ai_evaluation(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Retorna a avaliação completa de performance comercial do UNION GROWTH AI."""
    return UnionGrowthAI(db).evaluate_commercial_performance()


@router.post("/api/autonomous/growth-ai/optimize")
def trigger_growth_ai_optimization(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Atualiza prioridades de produtos e campanhas respeitando as travas de gasto zero."""
    return UnionGrowthAI(db).update_priorities_automatically()


@router.post("/api/autonomous/orchestrator/cycle/{cycle_type}")
def run_autonomous_orchestrator_cycle(
    cycle_type: str,
    bucket_suffix: Optional[str] = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Dispara um ciclo do UNION AUTONOMOUS ORCHESTRATOR (every_6_hours, daily, weekly, monthly)."""
    try:
        return UnionAutonomousOrchestrator(db).execute_cycle(
            cycle_type=cycle_type,
            bucket_suffix=bucket_suffix,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/autonomous/orchestrator/queue")
def get_persistent_orchestrator_queue(
    limit: int = 50,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Lista os jobs persistentes e auditáveis do UNION AUTONOMOUS ORCHESTRATOR."""
    return {"queue": UnionAutonomousOrchestrator(db).list_persistent_queue(limit=limit)}


@router.post("/api/autonomous/orchestrator/recover")
def recover_stuck_orchestrator_jobs(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Recupera tarefas interrompidas na fila persistente."""
    return UnionAutonomousOrchestrator(db).recover_persistent_queue()


@router.get("/api/autonomous/infrastructure")
def get_execution_infrastructure_status() -> Dict[str, Any]:
    """Inspeciona se o sistema roda em computador local (Opção 1) ou servidor/VPS (Opção 2)."""
    return inspect_execution_infrastructure()
