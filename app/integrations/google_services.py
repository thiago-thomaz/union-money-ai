"""Conectores Oficiais Google Search Console (G) e Google Analytics 4 (H) para o UNION CONNECT (Seção 3)."""

from typing import Any, Dict, List, Optional
from urllib.parse import quote
import httpx
from app.config import settings


class GoogleSearchConsoleConnector:
    """Conector G — Google Search Console API v1 / Webmasters v3 (Somente endpoints oficiais)."""

    slug = "gsc"
    name = "Google Search Console"
    oauth_token_url = "https://oauth2.googleapis.com/token"
    search_analytics_base = "https://searchconsole.googleapis.com/v1/sites"
    webmasters_base = "https://www.googleapis.com/webmasters/v3/sites"

    def check_status(self, db_token: Optional[str] = None) -> Dict[str, Any]:
        token = (db_token or settings.GSC_ACCESS_TOKEN or "").strip()
        site_url = settings.GSC_SITE_URL.strip()
        authorized = bool(token and site_url)
        return {
            "connector": self.name,
            "slug": self.slug,
            "status_indicator": "ACTIVE" if authorized else "AUTHORIZATION_REQUIRED",
            "authorization_block_status": "OPERACIONAL" if authorized else "BLOQUEADA POR AUTORIZAÇÃO",
            "has_credentials": authorized,
            "site_url": site_url or None,
            "official_endpoints": [
                "POST https://oauth2.googleapis.com/token",
                "PUT https://www.googleapis.com/webmasters/v3/sites/{siteUrl}/sitemaps/{feedpath}",
                "POST https://searchconsole.googleapis.com/v1/sites/{siteUrl}/searchAnalytics/query",
            ],
        }

    def submit_sitemap(self, sitemap_url: str, access_token: Optional[str] = None) -> Dict[str, Any]:
        """Submete sitemap.xml ao Google Search Console quando autorizado."""
        tok = (access_token or settings.GSC_ACCESS_TOKEN or "").strip()
        site_url = settings.GSC_SITE_URL.strip()
        if not tok or not site_url:
            return {
                "connector": self.slug,
                "submitted": False,
                "status": "BLOQUEADA POR AUTORIZAÇÃO",
                "reason": "GSC_ACCESS_TOKEN ou GSC_SITE_URL não configurados.",
            }

        encoded_site = quote(site_url, safe="")
        encoded_feed = quote(sitemap_url, safe="")
        endpoint = f"{self.webmasters_base}/{encoded_site}/sitemaps/{encoded_feed}"
        headers = {"Authorization": f"Bearer {tok}"}
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.put(endpoint, headers=headers)
                resp.raise_for_status()
            return {"connector": self.slug, "submitted": True, "status": "ACTIVE", "sitemap_url": sitemap_url}
        except Exception as exc:
            return {"connector": self.slug, "submitted": False, "status": "ERROR", "error": str(exc)}

    def fetch_search_keywords(
        self,
        start_date: str,
        end_date: str,
        row_limit: int = 25,
        access_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Consulta termos reais de busca orgânica via Search Analytics API oficial."""
        tok = (access_token or settings.GSC_ACCESS_TOKEN or "").strip()
        site_url = settings.GSC_SITE_URL.strip()
        if not tok or not site_url:
            return {
                "connector": self.slug,
                "status": "BLOQUEADA POR AUTORIZAÇÃO",
                "rows": [],
            }

        encoded_site = quote(site_url, safe="")
        endpoint = f"{self.search_analytics_base}/{encoded_site}/searchAnalytics/query"
        headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": ["query", "page"],
            "rowLimit": min(100, max(1, row_limit)),
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(endpoint, json=body, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            return {
                "connector": self.slug,
                "status": "ACTIVE",
                "rows": data.get("rows", []),
            }
        except Exception as exc:
            return {"connector": self.slug, "status": "ERROR", "error": str(exc), "rows": []}


class GoogleAnalyticsConnector:
    """Conector H — Google Analytics 4 Data API v1beta & Measurement Protocol."""

    slug = "ga4"
    name = "Google Analytics 4"
    data_api_base = "https://analyticsdata.googleapis.com/v1beta/properties"
    mp_collect_url = "https://www.google-analytics.com/mp/collect"

    def check_status(self, db_token: Optional[str] = None) -> Dict[str, Any]:
        tok = (db_token or settings.GA4_ACCESS_TOKEN or "").strip()
        prop_id = settings.GA4_PROPERTY_ID.strip()
        mp_ready = bool(settings.GA4_MEASUREMENT_ID.strip() and settings.GA4_API_SECRET.strip())
        authorized = bool((tok and prop_id) or mp_ready)
        return {
            "connector": self.name,
            "slug": self.slug,
            "status_indicator": "ACTIVE" if authorized else "AUTHORIZATION_REQUIRED",
            "authorization_block_status": "OPERACIONAL" if authorized else "BLOQUEADA POR AUTORIZAÇÃO",
            "has_credentials": authorized,
            "property_id": prop_id or None,
            "measurement_protocol_ready": mp_ready,
            "official_endpoints": [
                "POST https://analyticsdata.googleapis.com/v1beta/properties/{propertyId}:runReport",
                "POST https://www.google-analytics.com/mp/collect",
            ],
        }

    def fetch_organic_report(self, access_token: Optional[str] = None) -> Dict[str, Any]:
        """Consulta sessões e eventos reais via GA4 Data API quando autorizado."""
        tok = (access_token or settings.GA4_ACCESS_TOKEN or "").strip()
        prop_id = settings.GA4_PROPERTY_ID.strip()
        if not tok or not prop_id:
            return {
                "connector": self.slug,
                "status": "BLOQUEADA POR AUTORIZAÇÃO",
                "rows": [],
            }

        endpoint = f"{self.data_api_base}/{prop_id}:runReport"
        headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
        body: Dict[str, List[Dict[str, str]]] = {
            "dateRanges": [{"startDate": "7daysAgo", "endDate": "today"}],
            "dimensions": [{"name": "pagePath"}],
            "metrics": [{"name": "sessions"}, {"name": "engagedSessions"}],
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(endpoint, json=body, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            return {"connector": self.slug, "status": "ACTIVE", "rows": data.get("rows", [])}
        except Exception as exc:
            return {"connector": self.slug, "status": "ERROR", "error": str(exc), "rows": []}

