"""Gerenciador de Campanhas por Nicho, Experimentos A/B e Regras de Otimização (Seção 9)."""

from typing import Any, Dict, List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.content_engine.seo import slugify
from app.marketing.link_manager import UnionLinkManager
from app.models.campaign import Campaign, Experiment, ExperimentVariant
from app.models.click import ClickLog
from app.models.conversion import Conversion
from app.models.product import Product


def create_campaign(
    db: Session,
    name: str,
    objective: str = "CONVERSIONS",
    target_channel: str = "ORGANIC_MULTI",
    category_id: Optional[int] = None,
    product_id: Optional[int] = None,
    notes: Optional[str] = None,
    target_audience: Optional[str] = None,
    problem_solved: Optional[str] = None,
    keywords: Optional[str] = None,
) -> Campaign:
    """Cria uma nova campanha comercial por nicho."""
    base_slug = slugify(name) or "campanha"
    slug = base_slug
    counter = 1
    while db.query(Campaign).filter(Campaign.slug == slug).first():
        counter += 1
        slug = f"{base_slug}-{counter}"

    campaign = Campaign(
        name=name,
        slug=slug,
        objective=objective,
        target_channel=target_channel,
        target_audience=target_audience or "Consumidores buscando melhor relação custo-benefício",
        problem_solved=problem_solved or "Facilitar a comparação objetiva de especificações e preço atualizado",
        keywords=keywords,
        priority_weight=1.0,
        category_id=category_id,
        product_id=product_id,
        status="ACTIVE",
        notes=notes,
        is_active=True,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


def create_ab_experiment(
    db: Session,
    name: str,
    dimension: str,
    variants_data: List[dict],
    campaign_id: Optional[int] = None,
    product_id: Optional[int] = None,
) -> Experiment:
    """Cria experimento A/B com suas variantes iniciais."""
    exp = Experiment(
        name=name,
        campaign_id=campaign_id,
        product_id=product_id,
        dimension=dimension.upper(),
        status="RUNNING",
    )
    db.add(exp)
    db.flush()

    for idx, v in enumerate(variants_data):
        key = v.get("variant_key") or chr(65 + idx)
        variant = ExperimentVariant(
            experiment_id=exp.id,
            variant_key=key,
            headline_or_cta=v["headline_or_cta"],
            content_format=v.get("content_format", "ARTICLE_REVIEW"),
        )
        db.add(variant)

    db.commit()
    db.refresh(exp)
    return exp


def apply_campaign_optimization_rules(db: Session) -> Dict[str, Any]:
    """Aplica as regras determinísticas de otimização de marketing (Seção 9):
    - Aumenta prioridade de campanhas/produtos com conversões confirmadas.
    - Reduz prioridade de produtos com muitos cliques (>= 30) e zero conversões.
    - Não interpreta ausência inicial de dados (poucos cliques) como falha do produto.
    - Pausa produtos indisponíveis (fora de estoque) e links inválidos.
    """
    boosted_campaigns = 0
    reduced_priority_products = 0
    paused_out_of_stock = 0

    # 1. Revisão de links e pausa de links inválidos
    link_review = UnionLinkManager.review_all_links(db)

    # 2. Pausa produtos sem estoque
    out_of_stock_products = (
        db.query(Product)
        .filter(Product.is_active.is_(True), Product.in_stock.is_(False))
        .all()
    )
    for prod in out_of_stock_products:
        prod.score_classification = "descartar"
        if prod.opportunity_score is not None and prod.opportunity_score > 39.0:
            prod.opportunity_score = 39.0
        paused_out_of_stock += 1

    # 3. Avalia produtos ativos com cliques suficientes (não penaliza quem ainda não teve tráfego)
    active_products = db.query(Product).filter(Product.is_active.is_(True)).all()
    for prod in active_products:
        clicks = (
            db.query(func.count(ClickLog.id))
            .filter(ClickLog.product_id == prod.id, ClickLog.is_valid_human.is_(True))
            .scalar()
            or 0
        )
        convs = (
            db.query(func.count(Conversion.id))
            .filter(Conversion.product_id == prod.id, Conversion.status == "CONFIRMED")
            .scalar()
            or 0
        )
        if convs > 0 and prod.opportunity_score is not None:
            prod.opportunity_score = round(min(100.0, prod.opportunity_score + 3.0), 2)
        elif clicks >= 30 and convs == 0 and prod.opportunity_score is not None:
            prod.opportunity_score = round(max(20.0, prod.opportunity_score - 5.0), 2)
            reduced_priority_products += 1

    # 4. Ajusta prioridade das campanhas com conversões comprovadas
    campaigns = db.query(Campaign).filter(Campaign.is_active.is_(True)).all()
    for camp in campaigns:
        convs = (
            db.query(func.count(Conversion.id))
            .filter(Conversion.campaign_id == camp.id, Conversion.status == "CONFIRMED")
            .scalar()
            or 0
        )
        if convs > 0:
            camp.priority_weight = round(min(5.0, (camp.priority_weight or 1.0) + 0.5), 2)
            boosted_campaigns += 1

    db.commit()
    return {
        "boosted_campaigns": boosted_campaigns,
        "reduced_priority_products": reduced_priority_products,
        "paused_out_of_stock_products": paused_out_of_stock,
        "links_review": link_review,
    }
