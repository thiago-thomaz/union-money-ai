"""Rotas de Campanhas Comerciais e Experimentação A/B."""

from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.dependencies import get_db_session
from app.models.campaign import Experiment, ExperimentVariant
from app.services.campaign_service import (
    create_new_campaign,
    create_new_experiment,
    evaluate_experiment_service,
    list_campaigns,
    record_variant_event,
)

router = APIRouter(tags=["Campaigns"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent.parent / "templates"))


class CampaignCreateSchema(BaseModel):
    name: str = Field(..., min_length=3, max_length=160)
    objective: str = "CONVERSIONS"
    target_channel: str = "ORGANIC_MULTI"
    category_id: Optional[int] = None
    product_id: Optional[int] = None
    notes: Optional[str] = None


class VariantSchema(BaseModel):
    variant_key: Optional[str] = None
    headline_or_cta: str = Field(..., min_length=2, max_length=280)
    content_format: str = "ARTICLE_REVIEW"


class ExperimentCreateSchema(BaseModel):
    name: str = Field(..., min_length=3, max_length=160)
    dimension: str = "TITLE"
    campaign_id: Optional[int] = None
    product_id: Optional[int] = None
    variants: List[VariantSchema] = Field(..., min_length=2)


class VariantEventSchema(BaseModel):
    variant_id: int
    impressions_delta: int = 0
    clicks_delta: int = 0
    conversions_delta: int = 0


@router.get("/campaigns", response_class=HTMLResponse)
def campaigns_page(request: Request, db: Session = Depends(get_db_session)):
    campaigns = list_campaigns(db)
    experiments = db.query(Experiment).order_by(Experiment.created_at.desc()).all()
    variants_map = {}
    for exp in experiments:
        variants_map[exp.id] = (
            db.query(ExperimentVariant)
            .filter(ExperimentVariant.experiment_id == exp.id)
            .all()
        )
    return templates.TemplateResponse(
        request,
        "campaigns.html",
        {
            "page_title": "Campanhas e Testes A/B",
            "campaigns": campaigns,
            "experiments": experiments,
            "variants_map": variants_map,
        },
    )


@router.get("/api/campaigns")
def api_list_campaigns(only_active: bool = False, db: Session = Depends(get_db_session)):
    items = list_campaigns(db, only_active=only_active)
    return [
        {
            "id": c.id,
            "name": c.name,
            "slug": c.slug,
            "objective": c.objective,
            "target_channel": c.target_channel,
            "status": c.status,
            "is_active": c.is_active,
        }
        for c in items
    ]


@router.post("/api/campaigns", status_code=status.HTTP_201_CREATED)
def api_create_campaign(payload: CampaignCreateSchema, db: Session = Depends(get_db_session)):
    camp = create_new_campaign(db, payload.model_dump())
    return {
        "id": camp.id,
        "name": camp.name,
        "slug": camp.slug,
        "status": camp.status,
    }


@router.post("/api/campaigns/experiments", status_code=status.HTTP_201_CREATED)
def api_create_experiment(payload: ExperimentCreateSchema, db: Session = Depends(get_db_session)):
    exp = create_new_experiment(db, payload.model_dump())
    variants = db.query(ExperimentVariant).filter(ExperimentVariant.experiment_id == exp.id).all()
    return {
        "id": exp.id,
        "name": exp.name,
        "dimension": exp.dimension,
        "status": exp.status,
        "variants": [
            {
                "id": v.id,
                "variant_key": v.variant_key,
                "headline_or_cta": v.headline_or_cta,
            }
            for v in variants
        ],
    }


@router.post("/api/campaigns/experiments/events")
def api_record_experiment_event(payload: VariantEventSchema, db: Session = Depends(get_db_session)):
    variant = record_variant_event(
        db,
        variant_id=payload.variant_id,
        impressions_delta=payload.impressions_delta,
        clicks_delta=payload.clicks_delta,
        conversions_delta=payload.conversions_delta,
    )
    if not variant:
        raise HTTPException(status_code=404, detail="Variante não encontrada.")
    return {
        "variant_id": variant.id,
        "impressions": variant.impressions,
        "clicks": variant.clicks,
        "conversions": variant.conversions,
    }


@router.get("/api/campaigns/experiments/{experiment_id}/evaluate")
def api_evaluate_experiment(experiment_id: int, db: Session = Depends(get_db_session)):
    try:
        return evaluate_experiment_service(db, experiment_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

