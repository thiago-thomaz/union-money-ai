"""Jobs automáticos de preparação de conteúdo para oportunidades prioritárias."""

from app.content_engine.articles import generate_review_article
from app.core.logging import logger
from app.database import SessionLocal
from app.models.content import ContentItem
from app.models.marketplace import Category, Marketplace
from app.models.product import Product


def run_priority_content_generation_job() -> int:
    """Gera rascunhos de artigos para oportunidades com score >= 75 ainda sem conteúdo."""
    db = SessionLocal()
    created_count = 0
    try:
        candidates = (
            db.query(Product)
            .filter(
                Product.is_active.is_(True),
                Product.is_synthetic_test.is_(False),
                Product.opportunity_score.isnot(None),
                Product.opportunity_score >= 75.0,
            )
            .all()
        )
        for prod in candidates:
            existing = db.query(ContentItem).filter(ContentItem.product_id == prod.id).first()
            if existing:
                continue
            cat = db.query(Category).filter(Category.id == prod.category_id).first()
            mp = db.query(Marketplace).filter(Marketplace.id == prod.marketplace_id).first()
            article_data = generate_review_article(
                product=prod,
                category_name=cat.name if cat else "Geral",
                marketplace_name=mp.name if mp else "Marketplace",
                affiliate_link=prod.affiliate_url or prod.product_url,
            )
            content = ContentItem(
                product_id=prod.id,
                content_type="ARTICLE",
                title=article_data["title"],
                slug=f"{article_data['slug']}-{prod.id}",
                body=article_data["body"],
                call_to_action=article_data["cta"],
                seo_keywords=article_data["seo_keywords"],
                status="READY",
            )
            db.add(content)
            created_count += 1
        db.commit()
        if created_count > 0:
            logger.info("Job de conteúdo gerou %d novo(s) artigo(s).", created_count)
        return created_count
    except Exception as exc:
        db.rollback()
        logger.error("Erro no job de geração de conteúdo: %s", exc)
        return 0
    finally:
        db.close()

