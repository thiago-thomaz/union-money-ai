"""Rotas de Inteligência de Oportunidades, Simulador de Score e Análise de Nichos."""

from pathlib import Path
from typing import Dict, Optional
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.dependencies import get_db_session
from app.intelligence.niche_analysis import analyze_niches
from app.intelligence.opportunity import get_configured_scorer, list_ranked_opportunities
from app.intelligence.product_scoring import ProductScoringInput

router = APIRouter(tags=["Opportunities"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent.parent / "templates"))


class ScoreSimulationRequest(BaseModel):
    price: Optional[float] = None
    original_price: Optional[float] = None
    in_stock: Optional[bool] = None
    announced_commission_rate: Optional[float] = None
    effective_commission_rate: Optional[float] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    demand_index: Optional[float] = None
    competition_index: Optional[float] = None
    content_potential_index: Optional[float] = None
    utility_score: Optional[float] = None
    verification_map: Dict[str, str] = {}


@router.get("/opportunities", response_class=HTMLResponse)
def opportunities_page(request: Request, db: Session = Depends(get_db_session)):
    opportunities = list_ranked_opportunities(db, limit=50)
    niches = analyze_niches(db)
    return templates.TemplateResponse(
        request,
        "opportunities.html",
        {
            "page_title": "Motor de Inteligência Comercial",
            "opportunities": opportunities,
            "niches": niches,
        },
    )


@router.get("/api/opportunities")
def api_list_opportunities(
    min_score: Optional[float] = None,
    classification: Optional[str] = None,
    include_synthetic: bool = False,
    db: Session = Depends(get_db_session),
):
    return list_ranked_opportunities(
        db,
        min_score=min_score,
        classification=classification,
        include_synthetic=include_synthetic,
    )


@router.post("/api/opportunities/evaluate")
def api_evaluate_opportunity(payload: ScoreSimulationRequest, db: Session = Depends(get_db_session)):
    scorer = get_configured_scorer(db)
    inp = ProductScoringInput(
        price=payload.price,
        original_price=payload.original_price,
        in_stock=payload.in_stock,
        announced_commission_rate=payload.announced_commission_rate,
        effective_commission_rate=payload.effective_commission_rate,
        rating=payload.rating,
        review_count=payload.review_count,
        demand_index=payload.demand_index,
        competition_index=payload.competition_index,
        content_potential_index=payload.content_potential_index,
        utility_score=payload.utility_score,
        verification_map=payload.verification_map,
    )
    res = scorer.evaluate(inp)
    return {
        "score": res.score,
        "classification": res.classification,
        "confidence_score": res.confidence_score,
        "sufficient_data": res.sufficient_data,
        "reason": res.reason,
        "commission_basis": res.commission_basis,
        "effective_vs_announced_gap_pct": res.effective_vs_announced_gap_pct,
        "data_separation": res.data_separation,
        "dimension_scores": res.dimension_scores,
        "weights_used": res.weights_used,
    }


@router.get("/api/opportunities/niches")
def api_analyze_niches(include_synthetic: bool = False, db: Session = Depends(get_db_session)):
    return analyze_niches(db, include_synthetic=include_synthetic)

