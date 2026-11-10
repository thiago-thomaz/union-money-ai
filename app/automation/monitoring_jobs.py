"""Jobs de Monitoramento Operacional e Registro de Saúde."""

from app.core.logging import logger
from app.database import SessionLocal
from app.models.audit import SystemLog
from app.models.product import Product


def run_system_health_check_job() -> bool:
    """Registra heartbeat de saúde operacional no banco de dados."""
    db = SessionLocal()
    try:
        active_products = db.query(Product).filter(Product.is_active.is_(True)).count()
        log_entry = SystemLog(
            level="INFO",
            module="monitoring_jobs",
            message="Verificação periódica de integridade executada com sucesso.",
            context={"active_products": active_products},
        )
        db.add(log_entry)
        db.commit()
        return True
    except Exception as exc:
        db.rollback()
        logger.error("Falha no job de monitoramento: %s", exc)
        return False
    finally:
        db.close()

