"""Mecanismo de Descoberta de Produtos e Registro de Conectores."""

from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from app.core.exceptions import CredentialsMissingError, IntegrationError
from app.core.logging import logger
from app.integrations.amazon import AmazonBrasilConnector
from app.integrations.base import BaseMarketplaceConnector
from app.integrations.mercadolivre import MercadoLivreConnector
from app.integrations.shopee import ShopeeBrasilConnector


CONNECTOR_REGISTRY: Dict[str, BaseMarketplaceConnector] = {
    "mercadolivre": MercadoLivreConnector(),
    "amazon": AmazonBrasilConnector(),
    "shopee": ShopeeBrasilConnector(),
}


def get_connector(marketplace_slug: str) -> BaseMarketplaceConnector:
    """Retorna a instância do conector correspondente ao slug do marketplace."""
    connector = CONNECTOR_REGISTRY.get(marketplace_slug.lower().strip())
    if not connector:
        raise IntegrationError(marketplace_slug, f"Conector '{marketplace_slug}' não registrado.")
    return connector


def get_all_connectors_status(db: Optional[Session] = None) -> List[Dict[str, Any]]:
    """Retorna o status real de disponibilidade e credenciais de todos os marketplaces."""
    statuses = []
    for slug, connector in CONNECTOR_REGISTRY.items():
        info = connector.check_availability()
        if db is not None:
            connector.record_sync_status(
                db,
                status_message=f"Verificação de status: {info['availability_status']}",
                availability=info["availability_status"],
            )
        statuses.append(info)
    return statuses


def discover_from_marketplace(
    db: Session,
    marketplace_slug: str,
    query: str,
    limit: int = 10,
) -> Dict[str, Any]:
    """Executa busca autorizada em um marketplace ou informa necessidade de importação manual."""
    connector = get_connector(marketplace_slug)
    availability = connector.check_availability()
    try:
        items = connector.search_products(query=query, limit=limit)
        connector.record_sync_status(
            db,
            status_message=f"Sincronização concluída: {len(items)} itens encontrados para '{query}'.",
            availability="READY",
        )
        return {
            "marketplace": connector.name,
            "slug": connector.slug,
            "status": "SUCCESS",
            "mode": "OFFICIAL_API",
            "items_found": len(items),
            "items": items,
        }
    except CredentialsMissingError as exc:
        connector.record_sync_status(
            db,
            status_message=exc.message,
            availability=availability["availability_status"],
        )
        logger.info("Descoberta via API indisponível para %s: %s", connector.name, exc.message)
        return {
            "marketplace": connector.name,
            "slug": connector.slug,
            "status": availability["availability_status"],
            "mode": "MANUAL_IMPORT_REQUIRED",
            "message": exc.message,
            "items_found": 0,
            "items": [],
        }
    except IntegrationError as exc:
        connector.record_sync_status(
            db,
            status_message=f"Erro na consulta: {exc.message}",
            availability="UNAVAILABLE",
        )
        return {
            "marketplace": connector.name,
            "slug": connector.slug,
            "status": "ERROR",
            "mode": availability["integration_mode"],
            "message": exc.message,
            "items_found": 0,
            "items": [],
        }

