"""Jobs automáticos de descoberta e reavaliação de pontuação de produtos."""

from app.core.logging import logger
from app.database import SessionLocal
from app.intelligence.discovery import get_all_connectors_status
from app.intelligence.opportunity import score_and_update_product
from app.models.product import Product


def run_rescore_all_products_job() -> int:
    """Recalcula o Product Opportunity Score de todos os produtos ativos no banco."""
    db = SessionLocal()
    try:
        products = db.query(Product).filter(Product.is_active.is_(True)).all()
        for prod in products:
            score_and_update_product(db, prod)
        db.commit()
        get_all_connectors_status(db)
        logger.info("Job de reavaliação concluído para %d produto(s).", len(products))
        return len(products)
    except Exception as exc:
        db.rollback()
        logger.error("Erro no job de reavaliação de produtos: %s", exc)
        return 0
    finally:
        db.close()

