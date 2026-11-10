"""Conector Oficial para Amazon Brasil (Programa de Associados / PA-API 5.0 / Creators API).

Política de Integração:
- Verifica elegibilidade e credenciais (`AMAZON_PARTNER_TAG`, `AMAZON_ACCESS_KEY`, `AMAZON_SECRET_KEY`).
- A API de Publicidade de Produtos da Amazon (PA-API 5.0) exige conta ativa no Associados Amazon Brasil
  e aprovação de vendas qualificadas nos últimos 180 dias.
- Quando as chaves de API estão presentes, executa chamadas HTTP assinadas com AWS Signature Version 4
  (AWS4-HMAC-SHA256) para `https://webservices.amazon.com.br/paapi5/searchitems` e `getitems`.
- Quando as chaves de API não estão presentes, informa explicitamente `ELIGIBILITY_REQUIRED` ou
  `MISSING_CREDENTIALS`, sem jamais simular respostas de API.
- Permite geração limpa de links de afiliado oficiais (`?tag=seuassociado-20`) e importação manual.
"""

from datetime import datetime, timezone
import hashlib
import hmac
import json
import re
from typing import Any, Dict, List, Optional
import httpx
from app.config import settings
from app.core.exceptions import CredentialsMissingError, IntegrationError
from app.integrations.base import BaseMarketplaceConnector


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _get_signature_key(key: str, date_stamp: str, region_name: str, service_name: str) -> bytes:
    k_date = _sign(("AWS4" + key).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region_name)
    k_service = _sign(k_region, service_name)
    return _sign(k_service, "aws4_request")


class AmazonBrasilConnector(BaseMarketplaceConnector):
    """Conector Amazon Brasil (Associados Amazon + PA-API 5.0 AWS SigV4 / Importação Manual)."""

    slug = "amazon"
    name = "Amazon Brasil"
    base_url = "https://www.amazon.com.br"
    paapi_host = "webservices.amazon.com.br"
    paapi_region = "us-east-1"
    paapi_service = "ProductAdvertisingAPI"
    default_rate_limit_per_minute = 20

    def check_availability(self) -> Dict[str, Any]:
        has_tag = bool(settings.AMAZON_PARTNER_TAG.strip())
        has_api_keys = bool(
            has_tag and settings.AMAZON_ACCESS_KEY.strip() and settings.AMAZON_SECRET_KEY.strip()
        )
        if has_api_keys:
            status = "READY"
            mode = "OFFICIAL_API"
            panel_state = "REALMENTE CONECTADO"
        elif has_tag:
            status = "ELIGIBILITY_REQUIRED"
            mode = "AFFILIATE_TAG_ACTIVE_AWAITING_PAAPI"
            panel_state = "AGUARDANDO AUTORIZAÇÃO"
        else:
            status = "MISSING_CREDENTIALS"
            mode = "MANUAL_IMPORT"
            panel_state = "CREDENCIAIS AUSENTES"

        return {
            "marketplace": self.name,
            "slug": self.slug,
            "availability_status": status,
            "panel_state": panel_state,
            "integration_mode": mode,
            "has_api_credentials": has_api_keys,
            "has_affiliate_tag": has_tag,
            "official_requirements": (
                "Requer conta no Programa de Associados da Amazon Brasil (AMAZON_PARTNER_TAG, ex.: loja-20). "
                "O acesso automatizado à PA-API 5.0 / Creators API exige elegibilidade por 3 vendas qualificadas "
                "nos primeiros 180 dias e chaves AMAZON_ACCESS_KEY / AMAZON_SECRET_KEY."
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

    def _build_sigv4_headers(self, target_operation: str, canonical_uri: str, payload_str: str) -> Dict[str, str]:
        """Constrói cabeçalhos AWS Signature Version 4 oficiais para Amazon PA-API 5.0."""
        access_key = settings.AMAZON_ACCESS_KEY.strip()
        secret_key = settings.AMAZON_SECRET_KEY.strip()
        host = settings.AMAZON_HOST.strip() or self.paapi_host
        region = settings.AMAZON_REGION.strip() or self.paapi_region

        now = datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        amz_target = f"com.amazon.paapi5.v1.ProductAdvertisingAPIv1.{target_operation}"
        content_type = "application/json; charset=utf-8"

        canonical_headers = (
            f"content-encoding:amz-1.0\n"
            f"content-type:{content_type}\n"
            f"host:{host}\n"
            f"x-amz-date:{amz_date}\n"
            f"x-amz-target:{amz_target}\n"
        )
        signed_headers = "content-encoding;content-type;host;x-amz-date;x-amz-target"
        payload_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
        canonical_request = f"POST\n{canonical_uri}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"

        algorithm = "AWS4-HMAC-SHA256"
        credential_scope = f"{date_stamp}/{region}/{self.paapi_service}/aws4_request"
        string_to_sign = (
            f"{algorithm}\n{amz_date}\n{credential_scope}\n"
            f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
        )
        signing_key = _get_signature_key(secret_key, date_stamp, region, self.paapi_service)
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        authorization_header = (
            f"{algorithm} Credential={access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        return {
            "content-encoding": "amz-1.0",
            "content-type": content_type,
            "host": host,
            "x-amz-date": amz_date,
            "x-amz-target": amz_target,
            "Authorization": authorization_header,
        }

    def search_products(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        self.authenticate()
        self.enforce_rate_limit()

        if settings.AMAZON_ACCESS_KEY.strip().startswith("SANDBOX_"):
            raise CredentialsMissingError(
                self.name,
                "Para busca automática via PA-API 5.0 AWS SigV4, valide a elegibilidade da conta Associados Amazon.",
            )

        payload = {
            "Keywords": query,
            "ItemCount": min(max(1, limit), 10),
            "PartnerTag": settings.AMAZON_PARTNER_TAG.strip(),
            "PartnerType": "Associates",
            "Marketplace": "www.amazon.com.br",
            "Resources": [
                "Images.Primary.Large",
                "ItemInfo.Title",
                "Offers.Listings.Price",
                "Offers.Listings.SavingBasis",
                "Offers.Listings.Availability.Type",
            ],
        }
        payload_str = json.dumps(payload, separators=(",", ":"))
        uri = "/paapi5/searchitems"
        headers = self._build_sigv4_headers("SearchItems", uri, payload_str)
        host = settings.AMAZON_HOST.strip() or self.paapi_host

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(f"https://{host}{uri}", content=payload_str, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            raise IntegrationError(self.name, f"Falha ao consultar PA-API 5.0 da Amazon Brasil: {exc}") from exc

        items = data.get("SearchResult", {}).get("Items", []) or []
        results: List[Dict[str, Any]] = []
        for item in items:
            asin = item.get("ASIN", "")
            detail_url = item.get("DetailPageURL") or f"https://www.amazon.com.br/dp/{asin}"
            title = item.get("ItemInfo", {}).get("Title", {}).get("DisplayValue", "")
            listings = item.get("Offers", {}).get("Listings", []) or [{}]
            first_listing = listings[0]
            price_val = float(first_listing.get("Price", {}).get("Amount", 0.0) or 0.0)
            saving_val = first_listing.get("SavingBasis", {}).get("Amount")
            avail_type = first_listing.get("Availability", {}).get("Type", "Now")
            img_url = item.get("Images", {}).get("Primary", {}).get("Large", {}).get("URL")

            results.append(
                {
                    "external_id": asin,
                    "title": title,
                    "price": price_val,
                    "original_price": float(saving_val) if saving_val else None,
                    "in_stock": avail_type.lower() in ("now", "in_stock", "available"),
                    "product_url": detail_url,
                    "affiliate_url": self.build_affiliate_link(detail_url),
                    "image_url": img_url,
                    "data_source": "OFFICIAL_API",
                    "is_synthetic_test": False,
                }
            )
        return results

    def fetch_authorized_deals(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self.search_products(query="ofertas", limit=limit)

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
        asin = self.extract_asin(external_id) or external_id.strip().upper()
        items = self.search_products(query=asin, limit=1)
        if not items:
            raise IntegrationError(self.name, f"ASIN {asin} não retornado pela PA-API 5.0.")
        return items[0]
