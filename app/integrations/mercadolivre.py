"""Conector Oficial para Mercado Livre Brasil.

Política de Integração:
- Utiliza exclusivamente a API oficial do Mercado Livre (`https://api.mercadolibre.com`) quando
  `ML_ACCESS_TOKEN` está configurado (o Mercado Livre exige token Bearer para buscas e itens).
- Para links de afiliados, utiliza links autorizados do Programa de Afiliados do Mercado Livre
  (`/sec/...` ou parâmetro `matt_tool` / `matt_word` da conta de afiliado).
- Nunca realiza web scraping proibido. Quando não há token configurado, informa claramente
  `MISSING_CREDENTIALS` e disponibiliza o fluxo de importação manual de links e produtos.
"""

from typing import Any, Dict, List, Optional
import re
import httpx
from app.config import settings
from app.core.exceptions import CredentialsMissingError, IntegrationError
from app.integrations.base import BaseMarketplaceConnector


class MercadoLivreConnector(BaseMarketplaceConnector):
    """Conector Mercado Livre Brasil (API Oficial + Importação Manual Autorizada)."""

    slug = "mercadolivre"
    name = "Mercado Livre"
    base_url = "https://www.mercadolivre.com.br"
    api_base_url = "https://api.mercadolibre.com"
    default_rate_limit_per_minute = 30

    def check_availability(self) -> Dict[str, Any]:
        has_token = bool(settings.ML_ACCESS_TOKEN.strip())
        has_tag = bool(settings.ML_AFFILIATE_TAG.strip())
        status = "READY" if has_token else "MISSING_CREDENTIALS"
        return {
            "marketplace": self.name,
            "slug": self.slug,
            "availability_status": status,
            "integration_mode": "OFFICIAL_API" if has_token else "MANUAL_IMPORT",
            "has_api_credentials": has_token,
            "has_affiliate_tag": has_tag,
            "official_requirements": (
                "Requer conta ativa no Programa de Afiliados do Mercado Livre para geração de links "
                "oficiais (/sec/ ou matt_tool) e ML_ACCESS_TOKEN OAuth 2.0 para consultas na API oficial."
            ),
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "last_sync_status": self.last_sync_status,
        }

    def authenticate(self) -> bool:
        if not settings.ML_ACCESS_TOKEN.strip():
            raise CredentialsMissingError(
                self.name,
                "ML_ACCESS_TOKEN não configurado. Configure o token OAuth oficial ou utilize a importação manual.",
            )
        return True

    def search_products(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        self.authenticate()
        self.enforce_rate_limit()

        headers = {"Authorization": f"Bearer {settings.ML_ACCESS_TOKEN.strip()}"}
        params = {"q": query, "limit": min(limit, 50)}
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(f"{self.api_base_url}/sites/MLB/search", headers=headers, params=params)
                resp.raise_for_status()
                payload = resp.json()
        except Exception as exc:
            raise IntegrationError(self.name, f"Falha ao consultar API oficial do Mercado Livre: {exc}") from exc

        results = []
        for item in payload.get("results", []):
            permalink = item.get("permalink", "")
            results.append(
                {
                    "external_id": item.get("id"),
                    "title": item.get("title"),
                    "price": float(item.get("price", 0.0)),
                    "original_price": item.get("original_price"),
                    "in_stock": (item.get("available_quantity", 0) or 0) > 0,
                    "product_url": permalink,
                    "affiliate_url": self.build_affiliate_link(permalink),
                    "image_url": item.get("thumbnail"),
                    "data_source": "OFFICIAL_API",
                    "is_synthetic_test": False,
                }
            )
        return results

    def fetch_authorized_deals(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self.search_products(query="ofertas", limit=limit)

    def build_affiliate_link(self, product_url: str, affiliate_tag: Optional[str] = None) -> str:
        clean_url = product_url.strip()
        if "/sec/" in clean_url:
            return clean_url
        tag = (affiliate_tag or settings.ML_AFFILIATE_TAG).strip()
        if not tag:
            return clean_url
        return self.append_query_params(clean_url, {"matt_tool": tag})

    def refresh_product_info(self, external_id: str) -> Dict[str, Any]:
        self.authenticate()
        self.enforce_rate_limit()
        clean_id = re.sub(r"[^A-Z0-9]", "", external_id.upper())
        headers = {"Authorization": f"Bearer {settings.ML_ACCESS_TOKEN.strip()}"}
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(f"{self.api_base_url}/items/{clean_id}", headers=headers)
                resp.raise_for_status()
                item = resp.json()
        except Exception as exc:
            raise IntegrationError(self.name, f"Falha ao atualizar item {clean_id}: {exc}") from exc

        return {
            "external_id": item.get("id"),
            "title": item.get("title"),
            "price": float(item.get("price", 0.0)),
            "original_price": item.get("original_price"),
            "in_stock": (item.get("available_quantity", 0) or 0) > 0,
            "product_url": item.get("permalink", ""),
        }

