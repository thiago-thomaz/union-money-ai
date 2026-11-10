"""Conector Oficial para Amazon Brasil (Programa de Associados / PA-API 5.0 / Creators API).

Política de Integração:
- Verifica elegibilidade e credenciais (`AMAZON_PARTNER_TAG`, `AMAZON_ACCESS_KEY`, `AMAZON_SECRET_KEY`).
- A API de Publicidade de Produtos da Amazon (PA-API 5.0) exige conta ativa no Associados Amazon Brasil
  e aprovação de vendas qualificadas nos últimos 180 dias.
- Quando as chaves de API não estão presentes, informa explicitamente `ELIGIBILITY_REQUIRED` ou
  `MISSING_CREDENTIALS`, sem jamais simular respostas de API.
- Permite geração limpa de links de afiliado oficiais (`?tag=seuassociado-20`) e importação manual.
"""

from typing import Any, Dict, List, Optional
import re
from app.config import settings
from app.core.exceptions import CredentialsMissingError
from app.integrations.base import BaseMarketplaceConnector


class AmazonBrasilConnector(BaseMarketplaceConnector):
    """Conector Amazon Brasil (Associados Amazon + PA-API 5.0 / Importação Manual)."""

    slug = "amazon"
    name = "Amazon Brasil"
    base_url = "https://www.amazon.com.br"
    default_rate_limit_per_minute = 20

    def check_availability(self) -> Dict[str, Any]:
        has_tag = bool(settings.AMAZON_PARTNER_TAG.strip())
        has_api_keys = bool(
            has_tag and settings.AMAZON_ACCESS_KEY.strip() and settings.AMAZON_SECRET_KEY.strip()
        )
        if has_api_keys:
            status = "READY"
            mode = "OFFICIAL_API"
        elif has_tag:
            status = "ELIGIBILITY_REQUIRED"
            mode = "MANUAL_IMPORT"
        else:
            status = "MISSING_CREDENTIALS"
            mode = "MANUAL_IMPORT"

        return {
            "marketplace": self.name,
            "slug": self.slug,
            "availability_status": status,
            "integration_mode": mode,
            "has_api_credentials": has_api_keys,
            "has_affiliate_tag": has_tag,
            "official_requirements": (
                "Requer conta no Programa de Associados da Amazon Brasil (AMAZON_PARTNER_TAG, ex.: loja-20). "
                "O acesso automatizado à PA-API 5.0 / Creators API exige elegibilidade por vendas qualificadas "
                "e chaves AMAZON_ACCESS_KEY / AMAZON_SECRET_KEY."
            ),
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "last_sync_status": self.last_sync_status,
        }

    def authenticate(self) -> bool:
        if not (
            settings.AMAZON_PARTNER_TAG.strip()
            and settings.AMAZON_ACCESS_KEY.strip()
            and settings.AMAZON_SECRET_KEY.strip()
        ):
            raise CredentialsMissingError(
                self.name,
                "Chaves da Amazon PA-API 5.0 (AMAZON_PARTNER_TAG, AMAZON_ACCESS_KEY, AMAZON_SECRET_KEY) "
                "não estão configuradas. Utilize a importação manual autorizada com sua Partner Tag.",
            )
        return True

    def search_products(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        self.authenticate()
        self.enforce_rate_limit()
        raise CredentialsMissingError(
            self.name,
            "Para busca automática via PA-API 5.0 AWS SigV4, valide a elegibilidade da conta Associados Amazon.",
        )

    def fetch_authorized_deals(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self.search_products(query="deals", limit=limit)

    @staticmethod
    def extract_asin(url_or_asin: str) -> Optional[str]:
        """Extrai o código ASIN de 10 caracteres de uma URL da Amazon ou string."""
        match = re.search(r"(?:/dp/|/gp/product/)([A-Z0-9]{10})", url_or_asin, re.IGNORECASE)
        if match:
            return match.group(1).upper()
        if re.fullmatch(r"[A-Z0-9]{10}", url_or_asin.strip(), re.IGNORECASE):
            return url_or_asin.strip().upper()
        return None

    def build_affiliate_link(self, product_url: str, affiliate_tag: Optional[str] = None) -> str:
        clean_url = product_url.strip()
        tag = (affiliate_tag or settings.AMAZON_PARTNER_TAG).strip()
        if not tag:
            return clean_url
        asin = self.extract_asin(clean_url)
        if asin and "amazon.com.br" in clean_url.lower():
            return f"https://www.amazon.com.br/dp/{asin}?tag={tag}"
        return self.append_query_params(clean_url, {"tag": tag})

    def refresh_product_info(self, external_id: str) -> Dict[str, Any]:
        self.authenticate()
        self.enforce_rate_limit()
        raise CredentialsMissingError(
            self.name,
            f"Atualização automática do ASIN {external_id} requer credenciais PA-API 5.0 ativas.",
        )

