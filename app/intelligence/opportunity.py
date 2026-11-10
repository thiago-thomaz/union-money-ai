"""Avaliação e ranqueamento de oportunidades comerciais."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from app.intelligence.product_scoring import (
    ProductOpportunityScorer,
    ProductScoringInput,
    ScoringResult,
)
from app.intelligence.trend_analysis import evaluate_price_utility_ratio
from app.models.audit import SystemSetting
from app.models.commission import Commission
from app.models.product import Product


def get_configured_scorer(db: Session) -> ProductOpportunityScorer:
    """Carrega pesos configurados no banco ou utiliza os pesos padrão oficiais."""
    setting = db.query(SystemSetting).filter(SystemSetting.key == "scoring_weights").first()
    custom_weights = setting.value_json if setting and isinstance(setting.value_json, dict) else None
    return ProductOpportunityScorer(custom_weights=custom_weights)


def compute_effective_commission_from_history(db: Session, product_id: int) -> Optional[float]:
    """Calcula a taxa de comissão efetivamente recebida com base no histórico real aprovado."""
    approved_commissions = (
        db.query(Commission)
        .filter(
            Commission.product_id == product_id,
            Commission.status.in_(["APPROVED", "PAID"]),
            Commission.effective_rate_pct.isnot(None),
        )
        .all()
    )
    if not approved_commissions:
        return None
    rates = [c.effective_rate_pct for c in approved_commissions if c.effective_rate_pct is not None]
    if not rates:
        return None
    return round(sum(rates) / len(rates), 2)


def score_and_update_product(db: Session, product: Product) -> ScoringResult:
    """Calcula o Product Opportunity Score de uma instância Product e atualiza seus metadados."""
    scorer = get_configured_scorer(db)

    if product.id:
        historical_effective = compute_effective_commission_from_history(db, product.id)
        if historical_effective is not None:
            product.effective_commission_rate = historical_effective

    utility = product.utility_score
    if utility is None and product.price and product.price > 0:
        utility = evaluate_price_utility_ratio(product.price, product.original_price, product.rating)
        product.utility_score = utility

    scoring_input = ProductScoringInput(
        price=product.price,
        original_price=product.original_price,
        in_stock=product.in_stock,
        announced_commission_rate=product.announced_commission_rate,
        effective_commission_rate=product.effective_commission_rate,
        rating=product.rating,
        review_count=product.review_count,
        demand_index=product.demand_index,
        competition_index=product.competition_index,
        content_potential_index=product.content_potential_index,
        utility_score=utility,
        verification_map=product.data_verification_map or {},
    )

    result = scorer.evaluate(scoring_input)
    product.opportunity_score = result.score
    product.score_classification = result.classification
    product.confidence_score = result.confidence_score
    product.score_breakdown = {
        "sufficient_data": result.sufficient_data,
        "reason": result.reason,
        "commission_basis": result.commission_basis,
        "effective_vs_announced_gap_pct": result.effective_vs_announced_gap_pct,
        "data_separation": result.data_separation,
        "dimensions": result.dimension_scores,
        "weights_used": result.weights_used,
    }

    rate_for_value = (
        product.effective_commission_rate
        if product.effective_commission_rate is not None
        else product.announced_commission_rate
    )
    if rate_for_value is not None and product.price and product.price > 0:
        product.estimated_commission_value = round(product.price * (rate_for_value / 100.0), 2)
    else:
        product.estimated_commission_value = None

    product.last_checked_at = datetime.now(timezone.utc)
    return result


def list_ranked_opportunities(
    db: Session,
    min_score: Optional[float] = None,
    classification: Optional[str] = None,
    include_synthetic: bool = False,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Retorna oportunidades ordenadas pelo Product Opportunity Score e confiança."""
    query = db.query(Product).filter(Product.is_active.is_(True))
    if not include_synthetic:
        query = query.filter(Product.is_synthetic_test.is_(False))
    if min_score is not None:
        query = query.filter(Product.opportunity_score.isnot(None), Product.opportunity_score >= min_score)
    if classification:
        query = query.filter(Product.score_classification == classification)

    products = (
        query.order_by(
            Product.opportunity_score.desc().nullslast(),
            Product.confidence_score.desc(),
        )
        .limit(limit)
        .all()
    )

    return [
        {
            "id": p.id,
            "title": p.title,
            "marketplace_id": p.marketplace_id,
            "category_id": p.category_id,
            "price": p.price,
            "announced_commission_rate": p.announced_commission_rate,
            "effective_commission_rate": p.effective_commission_rate,
            "estimated_commission_value": p.estimated_commission_value,
            "opportunity_score": p.opportunity_score,
            "score_classification": p.score_classification,
            "confidence_score": p.confidence_score,
            "in_stock": p.in_stock,
            "data_source": p.data_source,
            "is_synthetic_test": p.is_synthetic_test,
            "score_breakdown": p.score_breakdown,
        }
        for p in products
    ]

