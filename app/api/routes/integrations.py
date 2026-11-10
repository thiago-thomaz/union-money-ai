"""Rotas de Integrações de Marketplaces, Diagnóstico de APIs e Importação Manual Autorizada."""

from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core.exceptions import IntegrationError
from app.dependencies import get_db_session
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


@router.get("/integrations", response_class=HTMLResponse)
def integrations_page(request: Request, db: Session = Depends(get_db_session)):
    connector_statuses = get_all_connectors_status(db)
    marketplaces = db.query(Marketplace).order_by(Marketplace.id).all()
    categories = db.query(Category).filter(Category.is_active.is_(True)).order_by(Category.name).all()
    return templates.TemplateResponse(
        request,
        "integrations.html",
        {
            "page_title": "Integrações e Conectores",
            "connector_statuses": connector_statuses,
            "marketplaces": marketplaces,
            "categories": categories,
        },
    )


@router.get("/api/integrations/status")
def api_integrations_status(db: Session = Depends(get_db_session)):
    return get_all_connectors_status(db)


@router.post("/api/integrations/{marketplace_slug}/discover")
def api_discover_marketplace(
    marketplace_slug: str,
    query: str = "ofertas",
    limit: int = 10,
    db: Session = Depends(get_db_session),
):
    return discover_from_marketplace(db=db, marketplace_slug=marketplace_slug, query=query, limit=limit)


@router.post("/api/integrations/{marketplace_slug}/manual-import", status_code=status.HTTP_201_CREATED)
def api_manual_import_product(
    marketplace_slug: str,
    payload: ManualImportSchema,
    db: Session = Depends(get_db_session),
):
    """Fluxo oficial de importação manual de links e produtos autorizados quando API não está ativa."""
    try:
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
        status_message=f"Importação manual concluída: produto #{product.id} ({product.title[:40]})",
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

