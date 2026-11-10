"""Serviço de Campanhas e Experimentação A/B."""

from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from app.intelligence.recommendation import evaluate_ab_experiment
from app.marketing.campaign_manager import create_ab_experiment, create_campaign
from app.models.campaign import Campaign, Experiment, ExperimentVariant


def list_campaigns(db: Session, only_active: bool = False) -> List[Campaign]:
    query = db.query(Campaign)
    if only_active:
        query = query.filter(Campaign.is_active.is_(True), Campaign.status == "ACTIVE")
    return query.order_by(Campaign.created_at.desc()).all()


def create_new_campaign(db: Session, payload: Dict[str, Any]) -> Campaign:
    return create_campaign(
        db=db,
        name=str(payload["name"]).strip(),
        objective=payload.get("objective", "CONVERSIONS"),
        target_channel=payload.get("target_channel", "ORGANIC_MULTI"),
        category_id=payload.get("category_id"),
        product_id=payload.get("product_id"),
        notes=payload.get("notes"),
    )


def create_new_experiment(db: Session, payload: Dict[str, Any]) -> Experiment:
    return create_ab_experiment(
        db=db,
        name=str(payload["name"]).strip(),
        dimension=payload.get("dimension", "TITLE"),
        variants_data=payload["variants"],
        campaign_id=payload.get("campaign_id"),
        product_id=payload.get("product_id"),
    )


def record_variant_event(
    db: Session,
    variant_id: int,
    impressions_delta: int = 0,
    clicks_delta: int = 0,
    conversions_delta: int = 0,
) -> Optional[ExperimentVariant]:
    variant = db.query(ExperimentVariant).filter(ExperimentVariant.id == variant_id).first()
    if not variant:
        return None
    variant.impressions += max(0, impressions_delta)
    variant.clicks += max(0, clicks_delta)
    variant.conversions += max(0, conversions_delta)
    db.commit()
    db.refresh(variant)
    return variant


def evaluate_experiment_service(db: Session, experiment_id: int) -> Dict[str, Any]:
    return evaluate_ab_experiment(db, experiment_id)

