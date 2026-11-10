"""Análise de Nichos e Categorias Comerciais."""

from typing import Any, Dict, List
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.click import ClickLog
from app.models.commission import Commission
from app.models.conversion import Conversion
from app.models.marketplace import Category
from app.models.product import Product


INITIAL_CATEGORIES = [
    ("tecnologia", "Tecnologia", "Smartphones, áudio, wearables e gadgets inteligentes.", 6.0),
    ("informatica", "Informática", "Notebooks, periféricos, monitores, SSDs e componentes.", 5.5),
    ("casa-e-decoracao", "Casa e decoração", "Iluminação, móveis compactos, têxteis e decoração funcional.", 8.0),
    ("cozinha", "Cozinha", "Eletroportáteis, airfryers, panelas e utensílios culinários.", 7.5),
    ("organizacao", "Organização", "Caixas organizadoras, prateleiras modulares e otimização de espaço.", 9.0),
    ("beleza", "Beleza", "Cuidados pessoais, skincare, secadores e dermocosméticos.", 10.0),
    ("acessorios", "Acessórios", "Mochilas, bolsas, relógios, capas e acessórios do dia a dia.", 9.5),
    ("ferramentas", "Ferramentas", "Parafusadeiras, kits manuais, medição e manutenção residencial.", 7.0),
    ("pet", "Pet", "Comedouros automáticos, higiene, brinquedos e conforto pet.", 8.5),
    ("produtos-para-escritorio", "Produtos para escritório", "Cadeiras ergonômicas, suportes, luminárias e papelaria técnica.", 7.5),
]


def analyze_niches(db: Session, include_synthetic: bool = False) -> List[Dict[str, Any]]:
    """Analisa desempenho real de todas as categorias cadastradas."""
    categories = db.query(Category).filter(Category.is_active.is_(True)).order_by(Category.name).all()
    report: List[Dict[str, Any]] = []

    for cat in categories:
        prod_query = db.query(Product).filter(Product.category_id == cat.id, Product.is_active.is_(True))
        if not include_synthetic:
            prod_query = prod_query.filter(Product.is_synthetic_test.is_(False))

        products = prod_query.all()
        product_ids = [p.id for p in products]

        clicks_count = 0
        conversions_count = 0
        approved_commission_brl = 0.0

        if product_ids:
            clicks_count = (
                db.query(func.count(ClickLog.id))
                .filter(ClickLog.product_id.in_(product_ids), ClickLog.is_valid_human.is_(True))
                .scalar()
                or 0
            )
            conversions_count = (
                db.query(func.count(Conversion.id))
                .filter(Conversion.product_id.in_(product_ids), Conversion.status == "CONFIRMED")
                .scalar()
                or 0
            )
            approved_commission_brl = float(
                db.query(func.coalesce(func.sum(Commission.amount), 0.0))
                .filter(
                    Commission.product_id.in_(product_ids),
                    Commission.status.in_(["APPROVED", "PAID"]),
                )
                .scalar()
                or 0.0
            )

        scored = [p.opportunity_score for p in products if p.opportunity_score is not None]
        avg_score = round(sum(scored) / len(scored), 2) if scored else None

        report.append(
            {
                "category_id": cat.id,
                "slug": cat.slug,
                "name": cat.name,
                "active_products": len(products),
                "average_opportunity_score": avg_score,
                "clicks": clicks_count,
                "confirmed_conversions": conversions_count,
                "approved_commissions_brl": round(approved_commission_brl, 2),
                "conversion_rate_pct": round((conversions_count / clicks_count) * 100.0, 2) if clicks_count > 0 else 0.0,
            }
        )

    return report

