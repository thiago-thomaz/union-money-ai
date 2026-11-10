"""Rotas de Integrações de Marketplaces, Auditoria Fase 5, Ativação OAuth/Credenciais e Importação Autorizada."""

from pathlib import Path
from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.automation.autonomous_orchestrator import UnionAutonomousOrchestrator
from app.core.exceptions import IntegrationError
from app.dependencies import get_db_session
from app.integrations.union_connect import UnionConnect
from app.intelligence.discovery import (
    discover_from_marketplace,
    get_all_connectors_status,
    get_connector,
)
from app.models.marketplace import Category, Marketplace
from app.services.product_service import create_product

router = APIRouter(tags=["Integrations"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent.parent / "templates"))


class ManualImportSchema(BaseModel):
    title: str = Field(..., min_length=3)
    product_url: str = Field(..., min_length=8)
    affiliate_url: Optional[str] = None
    affiliate_tag: Optional[str] = None
    category_id: int
    price: float = Field(..., gt=0)
    original_price: Optional[float] = None
    announced_commission_rate: Optional[float] = Field(default=None, ge=0, le=100)
    rating: Optional[float] = Field(default=None, ge=0, le=5)
    review_count: Optional[int] = Field(default=None, ge=0)
    demand_index: Optional[float] = Field(default=None, ge=0, le=100)
    competition_index: Optional[float] = Field(default=None, ge=0, le=100)
    content_potential_index: Optional[float] = Field(default=None, ge=0, le=100)
    in_stock: bool = True


class RuntimeCredentialsPayload(BaseModel):
    credentials: Dict[str, Optional[str]]
    trigger_immediate_cycle: bool = True


@router.get("/integrations", response_class=HTMLResponse)
def integrations_page(request: Request, db: Session = Depends(get_db_session)):
    uc = UnionConnect(db)
    phase5_audit = uc.get_phase5_platform_audit_panel()
    connector_statuses = get_all_connectors_status(db)
    marketplaces = db.query(Marketplace).order_by(Marketplace.id).all()
    categories = db.query(Category).filter(Category.is_active.is_(True)).order_by(Category.name).all()
    return templates.TemplateResponse(
        request,
        "integrations.html",
        {
            "page_title": "Integrações, Auditoria Técnica e Ativação OAuth (Fase 5)",
            "phase5_audit": phase5_audit,
            "connector_statuses": connector_statuses,
            "marketplaces": marketplaces,
            "categories": categories,
        },
    )


@router.get("/api/integrations/status")
def api_integrations_status(db: Session = Depends(get_db_session)):
    _ = UnionConnect(db)
    return get_all_connectors_status(db)


@router.get("/api/integrations/phase5-audit")
def api_integrations_phase5_audit(db: Session = Depends(get_db_session)):
    """Retorna a auditoria detalhada das plataformas com os 4 estados oficiais da Fase 5."""
    return UnionConnect(db).get_phase5_platform_audit_panel()


@router.post("/api/connect/credentials/configure")
def api_configure_runtime_credentials(
    payload: RuntimeCredentialsPayload,
    db: Session = Depends(get_db_session),
):
    """Salva com criptografia simétrica as credenciais/tags informadas pelo proprietário no painel Cloud."""
    uc = UnionConnect(db)
    saved = uc.save_runtime_credentials(payload.credentials)
    cycle_res = None
    if payload.trigger_immediate_cycle and saved.get("updated_keys"):
        orch = UnionAutonomousOrchestrator(db)
        cycle_res = orch.execute_cycle("every_6_hours")
    return {
        **saved,
        "phase5_audit": uc.get_phase5_platform_audit_panel(),
        "immediate_cycle": cycle_res,
    }


@router.get("/api/connect/oauth/callback/{connector_slug}")
def api_oauth_callback(
    connector_slug: str,
    code: str = Query(..., min_length=2),
    db: Session = Depends(get_db_session),
):
    """Recebe o redirecionamento OAuth 2.0 oficial da plataforma e armazena o token criptografado."""
    try:
        return UnionConnect(db).handle_oauth_callback(connector_slug=connector_slug, code=code)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/integrations/{marketplace_slug}/discover")
def api_discover_marketplace(
    marketplace_slug: str,
    query: str = "ofertas",
    limit: int = 10,
    db: Session = Depends(get_db_session),
):
    _ = UnionConnect(db)
    return discover_from_marketplace(db=db, marketplace_slug=marketplace_slug, query=query, limit=limit)


@router.post("/api/integrations/{marketplace_slug}/manual-import", status_code=status.HTTP_201_CREATED)
def api_manual_import_product(
    marketplace_slug: str,
    payload: ManualImportSchema,
    db: Session = Depends(get_db_session),
):
    """Fluxo oficial de importação autorizada de links e produtos verificados."""
    try:
        _ = UnionConnect(db)
        connector = get_connector(marketplace_slug)
        normalized = connector.normalize_manual_import(payload.model_dump())
    except IntegrationError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    mp = db.query(Marketplace).filter(Marketplace.slug == marketplace_slug.lower().strip()).first()
    if not mp:
        raise HTTPException(status_code=404, detail=f"Marketplace '{marketplace_slug}' não encontrado no banco.")

    product_data = {
        **normalized,
        "marketplace_id": mp.id,
        "category_id": payload.category_id,
        "demand_index": payload.demand_index,
        "competition_index": payload.competition_index,
        "content_potential_index": payload.content_potential_index,
    }
    product = create_product(db, product_data)
    connector.record_sync_status(
        db,
        status_message=f"Importação concluída: produto #{product.id} ({product.title[:40]})",
    )
    return {
        "status": "MANUAL_IMPORT_SUCCESS",
        "product_id": product.id,
        "title": product.title,
        "affiliate_url": product.affiliate_url,
        "opportunity_score": product.opportunity_score,
        "score_classification": product.score_classification,
        "confidence_score": product.confidence_score,
    }
