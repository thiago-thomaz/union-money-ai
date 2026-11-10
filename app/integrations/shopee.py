"""Conector Oficial para Shopee Brasil (Programa de Afiliados Shopee / Open Platform GraphQL API).

Política de Integração:
- Suporta a API oficial Shopee Affiliate Open Platform (`https://open-api.affiliate.shopee.com.br/graphql`)
  autenticada via assinatura SHA256 (`SHOPEE_APP_ID` + `SHOPEE_APP_SECRET`).
- Implementa as 3 operações GraphQL oficiais:
  1. `productOfferV2` (consulta de produtos, preços e taxas de comissão).
  2. `generateShortLink` (geração automática de links curtos oficiais `s.shopee.com.br`).
  3. `conversionReport` (consulta automática de conversões e comissões).
- Quando a conta de afiliado ainda não possui liberação da Open API na Shopee, informa claramente
  `MISSING_CREDENTIALS` e disponibiliza o fluxo de importação manual de links (`s.shopee.com.br` ou
  URLs parametrizadas com `SHOPEE_AFFILIATE_ID`).
"""

import hashlib
import json
import time
from typing import Any, Dict, List, Optional
import httpx
from app.config import settings
from app.core.exceptions import CredentialsMissingError, IntegrationError
from app.integrations.base import BaseMarketplaceConnector


class ShopeeBrasilConnector(BaseMarketplaceConnector):
    """Conector Shopee Brasil (Affiliate Open API GraphQL + Importação Manual)."""

    slug = "shopee"
    name = "Shopee Brasil"
    base_url = "https://shopee.com.br"
    graphql_url = "https://open-api.affiliate.shopee.com.br/graphql"
    default_rate_limit_per_minute = 30

    def check_availability(self) -> Dict[str, Any]:
        has_api = bool(settings.SHOPEE_APP_ID.strip() and settings.SHOPEE_APP_SECRET.strip())
        has_aff_id = bool(settings.SHOPEE_AFFILIATE_ID.strip())

        if has_api:
            status = "READY"
            mode = "OFFICIAL_API"
            panel_state = "REALMENTE CONECTADO"
        elif has_aff_id:
            status = "MISSING_CREDENTIALS"
            mode = "AFFILIATE_ID_ACTIVE_AWAITING_OPEN_API"
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
            "has_api_credentials": has_api,
            "has_affiliate_tag": has_aff_id,
            "official_requirements": (
                "Requer aprovação no Programa de Afiliados da Shopee Brasil. "
                "Para uso via API GraphQL oficial (productOfferV2, generateShortLink, conversionReport), "
                "configure SHOPEE_APP_ID e SHOPEE_APP_SECRET; para links parametrizados configure SHOPEE_AFFILIATE_ID."
            ),
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "last_sync_status": self.last_sync_status,
        }

    def authenticate(self) -> bool:
        if not (settings.SHOPEE_APP_ID.strip() and settings.SHOPEE_APP_SECRET.strip()):
            raise CredentialsMissingError(
                self.name,
                "SHOPEE_APP_ID e SHOPEE_APP_SECRET não estão configurados. Utilize a importação manual.",
            )
        return True

    def _build_graphql_headers(self, body_json: str) -> Dict[str, str]:
        timestamp = str(int(time.time()))
        app_id = settings.SHOPEE_APP_ID.strip()
        secret = settings.SHOPEE_APP_SECRET.strip()
        factor = f"{app_id}{timestamp}{body_json}{secret}"
        signature = hashlib.sha256(factor.encode("utf-8")).hexdigest()
        return {
            "Content-Type": "application/json",
            "Authorization": f"SHA256 Credential={app_id}, Timestamp={timestamp}, Signature={signature}",
        }

    def search_products(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        self.authenticate()
        self.enforce_rate_limit()

        gql_query = {
            "query": (
                "query($keyword: String!, $limit: Int) { "
                "productOfferV2(keyword: $keyword, limit: $limit) { "
                "nodes { itemId productName price commissionRate offerLink productLink imageUrl } "
                "} }"
            ),
            "variables": {"keyword": query, "limit": min(limit, 50)},
        }
        body_str = json.dumps(gql_query, separators=(",", ":"))
        headers = self._build_graphql_headers(body_str)

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(self.graphql_url, content=body_str, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            raise IntegrationError(self.name, f"Erro ao consultar GraphQL Shopee Affiliate: {exc}") from exc

        nodes = data.get("data", {}).get("productOfferV2", {}).get("nodes", []) or []
        results = []
        for node in nodes:
            comm_raw = float(node.get("commissionRate", 0.0) or 0.0)
            comm_pct = comm_raw * 100.0 if comm_raw <= 1.0 else comm_raw
            results.append(
                {
                    "external_id": str(node.get("itemId", "")),
                    "title": node.get("productName", ""),
                    "price": float(node.get("price", 0.0) or 0.0),
                    "announced_commission_rate": round(comm_pct, 2),
                    "in_stock": True,
                    "product_url": node.get("productLink", ""),
                    "affiliate_url": node.get("offerLink", ""),
                    "image_url": node.get("imageUrl"),
                    "data_source": "OFFICIAL_API",
                    "is_synthetic_test": False,
                }
            )
        return results

    def generate_short_link_graphql(self, origin_url: str, sub_ids: Optional[List[str]] = None) -> str:
        """Gera link curto oficial (s.shopee.com.br) via mutation generateShortLink da Open API."""
        self.authenticate()
        self.enforce_rate_limit()
        gql_mutation = {
            "query": (
                "mutation($input: ShortLinkInput!) { "
                "generateShortLink(input: $input) { shortLink } "
                "}"
            ),
            "variables": {
                "input": {
                    "originUrl": origin_url.strip(),
                    "subIds": (sub_ids or ["union_money_ai"])[:5],
                }
            },
        }
        body_str = json.dumps(gql_mutation, separators=(",", ":"))
        headers = self._build_graphql_headers(body_str)
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(self.graphql_url, content=body_str, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            short_link = data.get("data", {}).get("generateShortLink", {}).get("shortLink")
            if short_link:
                return str(short_link)
        except Exception as exc:
            raise IntegrationError(self.name, f"Erro ao gerar shortLink via GraphQL Shopee: {exc}") from exc
        return self.build_affiliate_link(origin_url)

    def fetch_conversion_report_graphql(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Consulta relatório de conversões e comissões via query conversionReport da Open API."""
        self.authenticate()
        self.enforce_rate_limit()
        gql_query = {
            "query": (
                "query($limit: Int) { "
                "conversionReport(limit: $limit) { "
                "nodes { conversionId orderId orderStatus totalCommission netCommission purchaseTime } "
                "} }"
            ),
            "variables": {"limit": min(limit, 100)},
        }
        body_str = json.dumps(gql_query, separators=(",", ":"))
        headers = self._build_graphql_headers(body_str)
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(self.graphql_url, content=body_str, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            return data.get("data", {}).get("conversionReport", {}).get("nodes", []) or []
        except Exception as exc:
            raise IntegrationError(self.name, f"Erro ao consultar conversionReport Shopee: {exc}") from exc

    def fetch_authorized_deals(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self.search_products(query="oferta", limit=limit)

    def build_affiliate_link(self, product_url: str, affiliate_tag: Optional[str] = None) -> str:
        clean_url = product_url.strip()
        if "s.shopee.com.br" in clean_url.lower() or "shp.ee" in clean_url.lower():
            return clean_url
        aff_id = (affiliate_tag or settings.SHOPEE_AFFILIATE_ID).strip()
        if not aff_id:
            return clean_url
        return self.append_query_params(
            clean_url,
            {"utm_source": "an_affiliate", "utm_medium": "selleraffiliate", "af_siteid": aff_id},
        )

    def refresh_product_info(self, external_id: str) -> Dict[str, Any]:
        self.authenticate()
        self.enforce_rate_limit()
        items = self.search_products(query=external_id, limit=1)
        if not items:
            raise IntegrationError(self.name, f"Item {external_id} não retornado pela API oficial.")
        return items[0]
