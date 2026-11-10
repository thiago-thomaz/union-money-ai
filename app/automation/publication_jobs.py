"""Jobs de preparação de Landing Pages locais para conteúdos prontos."""

from app.core.logging import logger
from app.database import SessionLocal
from app.marketing.landing_pages import build_product_landing_page
from app.models.marketplace import Marketplace
from app.models.product import Product


def run_landing_page_sync_job() -> int:
    """Garante que produtos ativos de alta prioridade possuam Landing Page estática atualizada."""
    db = SessionLocal()
    synced = 0
    try:
        products = (
            db.query(Product)
            .filter(
                Product.is_active.is_(True),
                Product.is_synthetic_test.is_(False),
                Product.opportunity_score.isnot(None),
                Product.opportunity_score >= 75.0,
            )
            .all()
        )
        for prod in products:
            mp = db.query(Marketplace).filter(Marketplace.id == prod.marketplace_id).first()
            build_product_landing_page(
                product=prod,
                marketplace_name=mp.name if mp else "Marketplace",
                tracked_url=prod.affiliate_url or prod.product_url,
            )
            synced += 1
        return synced
    except Exception as exc:
        logger.error("Erro no job de landing pages: %s", exc)
        return 0
    finally:
        db.close()

