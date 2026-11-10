"""Classe base para conectores de Marketplaces com Rate Limiting e Registro de Sincronização."""

from abc import ABC, abstractmethod
from collections import deque
from datetime import datetime, timezone
import time
from typing import Any, Deque, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from sqlalchemy.orm import Session
from app.core.exceptions import (
    IntegrationError,
    RateLimitExceededError,
)
from app.core.logging import logger
from app.models.marketplace import Marketplace


class BaseMarketplaceConnector(ABC):
    """Interface base obrigatória para todos os conectores de marketplaces."""

    slug: str = "base"
    name: str = "Base Marketplace"
    base_url: str = "https://example.com"
    default_rate_limit_per_minute: int = 30

    def __init__(self, rate_limit_per_minute: Optional[int] = None) -> None:
        self.rate_limit_per_minute = rate_limit_per_minute or self.default_rate_limit_per_minute
        self._request_timestamps: Deque[float] = deque()
        self.last_sync_at: Optional[datetime] = None
        self.last_sync_status: Optional[str] = None

    def enforce_rate_limit(self) -> None:
        """Aplica controle de taxa de requisições em janela deslizante de 60 segundos."""
        now = time.monotonic()
        while self._request_timestamps and (now - self._request_timestamps[0]) > 60.0:
            self._request_timestamps.popleft()

        if len(self._request_timestamps) >= self.rate_limit_per_minute:
            oldest = self._request_timestamps[0]
            retry_after = max(0.5, 60.0 - (now - oldest))
            raise RateLimitExceededError(self.name, retry_after_seconds=retry_after)

        self._request_timestamps.append(now)

    def record_sync_status(self, db: Optional[Session], status_message: str, availability: Optional[str] = None) -> None:
        """Registra a última sincronização e disponibilidade na instância e no banco."""
        now_utc = datetime.now(timezone.utc)
        self.last_sync_at = now_utc
        self.last_sync_status = status_message
        if db is not None:
            mp = db.query(Marketplace).filter(Marketplace.slug == self.slug).first()
            if mp:
                mp.last_sync_at = now_utc
                mp.last_sync_status = status_message
                if availability:
                    mp.availability_status = availability
                db.commit()

    @abstractmethod
    def check_availability(self) -> Dict[str, Any]:
        """Verifica credenciais, elegibilidade e disponibilidade real do conector."""

    @abstractmethod
    def authenticate(self) -> bool:
        """Realiza ou valida autenticação oficial na API do marketplace."""

    @abstractmethod
    def search_products(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Consulta produtos na API oficial quando autorizada."""

    @abstractmethod
    def fetch_authorized_deals(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Consulta ofertas autorizadas na API oficial."""

    @abstractmethod
    def build_affiliate_link(self, product_url: str, affiliate_tag: Optional[str] = None) -> str:
        """Gera ou valida link de afiliado oficial para um produto."""

    @abstractmethod
    def refresh_product_info(self, external_id: str) -> Dict[str, Any]:
        """Atualiza informações de preço e estoque via API oficial."""

    def normalize_manual_import(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Valida e normaliza importação manual de produto/link autorizado quando sem API."""
        title = str(payload.get("title", "")).strip()
        product_url = str(payload.get("product_url", "")).strip()
        price = float(payload.get("price", 0.0) or 0.0)
        if not title or not product_url or price <= 0:
            raise IntegrationError(
                self.name,
                "Importação manual exige título, product_url válida e preço maior que zero.",
                code="INVALID_MANUAL_IMPORT",
            )

        affiliate_url = payload.get("affiliate_url")
        if not affiliate_url:
            affiliate_url = self.build_affiliate_link(product_url, payload.get("affiliate_tag"))

        return {
            "external_id": payload.get("external_id"),
            "title": title,
            "price": price,
            "original_price": payload.get("original_price"),
            "announced_commission_rate": payload.get("announced_commission_rate"),
            "rating": payload.get("rating"),
            "review_count": payload.get("review_count"),
            "in_stock": payload.get("in_stock", True),
            "product_url": product_url,
            "affiliate_url": affiliate_url,
            "data_source": "MANUAL_VERIFIED",
            "is_synthetic_test": False,
        }

    @staticmethod
    def append_query_params(url: str, params: Dict[str, str]) -> str:
        """Adiciona parâmetros de rastreamento ou tag de afiliado preservando a URL original."""
        parsed = urlparse(url)
        query_dict = dict(parse_qsl(parsed.query, keep_blank_values=True))
        for k, v in params.items():
            if v:
                query_dict[k] = v
        new_query = urlencode(query_dict)
        return urlunparse(parsed._replace(query=new_query))

