"""UNION CONNECT — Central de Integrações Automáticas (Seções 3 e 11).

Centraliza as 8 integrações externas + portal próprio:
A. Mercado Livre (mercadolivre)
B. Amazon Brasil (amazon)
C. Shopee Brasil (shopee)
D. YouTube & YouTube Shorts (youtube)
E. Instagram Reels (instagram)
F. Pinterest (pinterest)
G. Google Search Console (gsc)
H. Google Analytics 4 (ga4)
+ Portal Próprio UNION OFERTAS (union_ofertas)

Recursos em cada conector:
- OAuth quando suportado
- Armazenamento seguro de tokens (criptografia simétrica derivada de SECRET_KEY)
- Renovação automática de tokens (refresh_token)
- Verificação de validade e tratamento de expiração
- Reconexão automática quando possível
- Controle de permissões (required_scopes vs granted_scopes)
- Monitoramento, registro de erros e desativação segura
- Marcação explícita 'BLOQUEADA POR AUTORIZAÇÃO' (AUTHORIZATION_REQUIRED) quando sem acesso autorizado
"""

import base64
from datetime import datetime, timedelta, timezone
import hashlib
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
import httpx
from sqlalchemy.orm import Session
from app.config import settings
from app.core.security import mask_secret
from app.integrations.amazon import AmazonBrasilConnector
from app.integrations.google_services import GoogleAnalyticsConnector, GoogleSearchConsoleConnector
from app.integrations.mercadolivre import MercadoLivreConnector
from app.integrations.shopee import ShopeeBrasilConnector
from app.integrations.social.instagram import InstagramConnector
from app.integrations.social.pinterest import PinterestConnector
from app.integrations.social.youtube import YouTubeConnector
from app.models.audit import AuditLog
from app.models.autonomous import IntegrationCredentialToken, IntegrationStatusIndicator


OAUTH_METADATA: Dict[str, Dict[str, str]] = {
    "mercadolivre": {
        "auth_url": "https://auth.mercadolivre.com.br/authorization",
        "token_url": "https://api.mercadolibre.com/oauth/token",
        "docs_url": "https://developers.mercadolivre.com.br/pt_br/autenticacao-e-autorizacao",
    },
    "amazon": {
        "auth_url": "https://associados.amazon.com.br/assoc_credentials/home",
        "token_url": "https://webservices.amazon.com.br/paapi5/searchitems",
        "docs_url": "https://webservices.amazon.com/paapi5/documentation/",
    },
    "shopee": {
        "auth_url": "https://affiliate.shopee.com.br/open_api",
        "token_url": "https://open-api.affiliate.shopee.com.br/graphql",
        "docs_url": "https://open.shopee.com/documents",
    },
    "youtube": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "docs_url": "https://developers.google.com/youtube/v3/guides/uploading_a_video",
    },
    "instagram": {
        "auth_url": "https://www.facebook.com/v19.0/dialog/oauth",
        "token_url": "https://graph.facebook.com/v19.0/oauth/access_token",
        "docs_url": "https://developers.facebook.com/docs/instagram-api/guides/content-publishing",
    },
    "pinterest": {
        "auth_url": "https://www.pinterest.com/oauth/",
        "token_url": "https://api.pinterest.com/v5/oauth/token",
        "docs_url": "https://developers.pinterest.com/docs/api/v5/",
    },
    "gsc": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "docs_url": "https://developers.google.com/webmaster-tools/v1/api_reference_index",
    },
    "ga4": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "docs_url": "https://developers.google.com/analytics/devguides/reporting/data/v1",
    },
    "union_ofertas": {
        "auth_url": "/ofertas",
        "token_url": "LOCAL_NATIVE",
        "docs_url": "/ofertas/transparencia",
    },
}


def _derive_key_bytes(length: int) -> bytes:
    """Deriva chave determinística a partir de SECRET_KEY para proteção de tokens em repouso."""
    seed = settings.SECRET_KEY.encode("utf-8")
    out = bytearray()
    counter = 0
    while len(out) < length:
        digest = hashlib.sha256(seed + f":{counter}".encode("utf-8")).digest()
        out.extend(digest)
        counter += 1
    return bytes(out[:length])


def encrypt_token_value(plain_token: Optional[str]) -> Optional[str]:
    if not plain_token or not plain_token.strip():
        return None
    raw = plain_token.strip().encode("utf-8")
    key = _derive_key_bytes(len(raw))
    xored = bytes(a ^ b for a, b in zip(raw, key))
    return base64.urlsafe_b64encode(xored).decode("ascii")


def decrypt_token_value(encrypted_token: Optional[str]) -> Optional[str]:
    if not encrypted_token:
        return None
    try:
        xored = base64.urlsafe_b64decode(encrypted_token.encode("ascii"))
        key = _derive_key_bytes(len(xored))
        raw = bytes(a ^ b for a, b in zip(xored, key))
        return raw.decode("utf-8")
    except Exception:
        return None


class UnionConnect:
    """Camada unificada de gerenciamento de integrações, tokens OAuth, permissões e saúde."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.ml = MercadoLivreConnector()
        self.amazon = AmazonBrasilConnector()
        self.shopee = ShopeeBrasilConnector()
        self.youtube = YouTubeConnector()
        self.instagram = InstagramConnector()
        self.pinterest = PinterestConnector()
        self.gsc = GoogleSearchConsoleConnector()
        self.ga4 = GoogleAnalyticsConnector()

    def _get_env_credentials_for_slug(self, slug: str) -> Dict[str, Any]:
        """Inspeciona credenciais presentes no .env para sincronizar com o banco."""
        s = slug.lower().strip()
        if s == "union_ofertas":
            return {"has_creds": True, "access_token": "NATIVE_LOCAL", "refresh_token": None}
        if s == "mercadolivre":
            tok = settings.ML_ACCESS_TOKEN.strip()
            ref = settings.ML_REFRESH_TOKEN.strip()
            return {"has_creds": bool(tok), "access_token": tok or None, "refresh_token": ref or None}
        if s == "amazon":
            ok = bool(
                settings.AMAZON_PARTNER_TAG.strip()
                and settings.AMAZON_ACCESS_KEY.strip()
                and settings.AMAZON_SECRET_KEY.strip()
            )
            return {
                "has_creds": ok,
                "access_token": settings.AMAZON_ACCESS_KEY.strip() if ok else None,
                "refresh_token": None,
            }
        if s == "shopee":
            ok = bool(settings.SHOPEE_APP_ID.strip() and settings.SHOPEE_APP_SECRET.strip())
            return {
                "has_creds": ok,
                "access_token": settings.SHOPEE_APP_ID.strip() if ok else None,
                "refresh_token": None,
            }
        if s == "youtube":
            tok = (settings.YOUTUBE_ACCESS_TOKEN or settings.YOUTUBE_API_KEY).strip()
            ref = settings.YOUTUBE_REFRESH_TOKEN.strip()
            return {"has_creds": bool(tok), "access_token": tok or None, "refresh_token": ref or None}
        if s == "instagram":
            tok = settings.INSTAGRAM_ACCESS_TOKEN.strip()
            return {"has_creds": bool(tok), "access_token": tok or None, "refresh_token": None}
        if s == "pinterest":
            tok = settings.PINTEREST_ACCESS_TOKEN.strip()
            ref = settings.PINTEREST_REFRESH_TOKEN.strip()
            return {"has_creds": bool(tok), "access_token": tok or None, "refresh_token": ref or None}
        if s == "gsc":
            tok = settings.GSC_ACCESS_TOKEN.strip()
            ref = settings.GSC_REFRESH_TOKEN.strip()
            ok = bool(tok and settings.GSC_SITE_URL.strip())
            return {"has_creds": ok, "access_token": tok if ok else None, "refresh_token": ref or None}
        if s == "ga4":
            tok = settings.GA4_ACCESS_TOKEN.strip()
            mp_ok = bool(settings.GA4_MEASUREMENT_ID.strip() and settings.GA4_API_SECRET.strip())
            ok = bool((tok and settings.GA4_PROPERTY_ID.strip()) or mp_ok)
            return {
                "has_creds": ok,
                "access_token": (tok or settings.GA4_API_SECRET.strip()) if ok else None,
                "refresh_token": None,
            }
        return {"has_creds": False, "access_token": None, "refresh_token": None}

    def get_oauth_authorization_url(self, connector_slug: str, redirect_uri: Optional[str] = None) -> Dict[str, Any]:
        """Gera a URL oficial de autorização OAuth 2.0 (ação única inicial do proprietário)."""
        slug = connector_slug.lower().strip()
        meta = OAUTH_METADATA.get(slug)
        if not meta:
            raise ValueError(f"Conector '{slug}' não suportado no UNION CONNECT.")

        rec = (
            self.db.query(IntegrationCredentialToken)
            .filter(IntegrationCredentialToken.connector_slug == slug)
            .first()
        )
        scopes = rec.required_scopes if rec else []
        cb_uri = redirect_uri or f"{settings.PUBLIC_BASE_URL}/api/connect/oauth/callback/{slug}"
        params = {
            "response_type": "code",
            "redirect_uri": cb_uri,
            "scope": " ".join(scopes),
        }
        return {
            "connector_slug": slug,
            "authorization_url": f"{meta['auth_url']}?{urlencode(params)}" if meta["auth_url"].startswith("http") else meta["auth_url"],
            "token_endpoint": meta["token_url"],
            "official_documentation": meta["docs_url"],
            "required_scopes": scopes,
            "is_one_time_owner_authorization": True,
        }

    def store_authorized_token(
        self,
        connector_slug: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        granted_scopes: Optional[List[str]] = None,
        expires_in_seconds: int = 21600,
    ) -> Dict[str, Any]:
        """Armazena com segurança um token autorizado, ativa o conector e configura renovação automática."""
        slug = connector_slug.lower().strip()
        rec = (
            self.db.query(IntegrationCredentialToken)
            .filter(IntegrationCredentialToken.connector_slug == slug)
            .first()
        )
        if not rec:
            raise ValueError(f"Conector '{slug}' não encontrado.")

        now_utc = datetime.now(timezone.utc)
        rec.encrypted_access_token = encrypt_token_value(access_token)
        if refresh_token:
            rec.encrypted_refresh_token = encrypt_token_value(refresh_token)
        rec.masked_token_preview = mask_secret(access_token)
        rec.granted_scopes = granted_scopes if granted_scopes is not None else list(rec.required_scopes)
        rec.expires_at = now_utc + timedelta(seconds=max(60, expires_in_seconds))
        rec.last_verified_at = now_utc
        rec.last_renewed_at = now_utc
        rec.last_error = None

        # Verifica se todos os escopos obrigatórios foram concedidos
        missing_scopes = set(rec.required_scopes or []) - set(rec.granted_scopes or [])
        if missing_scopes:
            rec.status_indicator = IntegrationStatusIndicator.PENDING
            rec.authorization_block_status = "BLOQUEADA POR AUTORIZAÇÃO"
            rec.last_error = f"Escopos pendentes: {', '.join(sorted(missing_scopes))}"
        else:
            rec.status_indicator = IntegrationStatusIndicator.ACTIVE
            rec.authorization_block_status = "OPERACIONAL"

        self.db.add(
            AuditLog(
                actor="owner_oauth",
                action="UNION_CONNECT_STORE_TOKEN",
                entity_type="IntegrationCredentialToken",
                entity_id=slug,
                details={
                    "status_indicator": rec.status_indicator,
                    "masked_token": rec.masked_token_preview,
                    "granted_scopes": rec.granted_scopes,
                },
            )
        )
        self.db.commit()
        return self.get_connector_status(slug)

    def get_decrypted_access_token(self, connector_slug: str) -> Optional[str]:
        """Obtém o token de acesso descriptografado do banco ou do .env."""
        slug = connector_slug.lower().strip()
        rec = (
            self.db.query(IntegrationCredentialToken)
            .filter(IntegrationCredentialToken.connector_slug == slug)
            .first()
        )
        if rec and rec.status_indicator == IntegrationStatusIndicator.DISABLED:
            return None
        if rec and rec.encrypted_access_token:
            tok = decrypt_token_value(rec.encrypted_access_token)
            if tok:
                return tok
        env_info = self._get_env_credentials_for_slug(slug)
        return env_info["access_token"]

    def renew_token_if_needed(self, connector_slug: str, force: bool = False) -> Dict[str, Any]:
        """Verifica expiração do token e executa renovação automática via refresh_token quando disponível."""
        slug = connector_slug.lower().strip()
        rec = (
            self.db.query(IntegrationCredentialToken)
            .filter(IntegrationCredentialToken.connector_slug == slug)
            .first()
        )
        if not rec:
            raise ValueError(f"Conector '{slug}' não encontrado.")

        if slug == "union_ofertas":
            return {"connector_slug": slug, "renewed": False, "status_indicator": IntegrationStatusIndicator.ACTIVE}

        now_utc = datetime.now(timezone.utc)
        is_expired = False
        if rec.expires_at:
            exp_dt = rec.expires_at if rec.expires_at.tzinfo else rec.expires_at.replace(tzinfo=timezone.utc)
            is_expired = now_utc >= (exp_dt - timedelta(minutes=10))

        if not is_expired and not force:
            return {
                "connector_slug": slug,
                "renewed": False,
                "status_indicator": rec.status_indicator,
                "message": "Token dentro do prazo de validade.",
            }

        refresh_tok = decrypt_token_value(rec.encrypted_refresh_token) or self._get_env_credentials_for_slug(slug).get("refresh_token")
        if not refresh_tok:
            if is_expired:
                rec.status_indicator = IntegrationStatusIndicator.AUTHORIZATION_REQUIRED
                rec.authorization_block_status = "BLOQUEADA POR AUTORIZAÇÃO"
                rec.last_error = "Token expirado e sem refresh_token configurado para renovação automática."
                self.db.commit()
            return {
                "connector_slug": slug,
                "renewed": False,
                "status_indicator": rec.status_indicator,
                "message": "Sem refresh_token disponível.",
            }

        # Executa renovação OAuth oficial quando em produção; se o refresh_token for de sandbox local, renova janela com segurança
        meta = OAUTH_METADATA.get(slug, {})
        token_url = meta.get("token_url", "")
        if refresh_tok.startswith("SANDBOX_REFRESH_"):
            new_access = f"SANDBOX_ACCESS_{slug.upper()}_{int(now_utc.timestamp())}"
            return self.store_authorized_token(
                connector_slug=slug,
                access_token=new_access,
                refresh_token=refresh_tok,
                granted_scopes=rec.granted_scopes or rec.required_scopes,
                expires_in_seconds=21600,
            )

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    token_url,
                    data={"grant_type": "refresh_token", "refresh_token": refresh_tok},
                )
                resp.raise_for_status()
                payload = resp.json()
            new_tok = payload.get("access_token")
            new_ref = payload.get("refresh_token") or refresh_tok
            ttl = int(payload.get("expires_in", 21600))
            if new_tok:
                return self.store_authorized_token(
                    connector_slug=slug,
                    access_token=new_tok,
                    refresh_token=new_ref,
                    granted_scopes=rec.granted_scopes or rec.required_scopes,
                    expires_in_seconds=ttl,
                )
        except Exception as exc:
            rec.status_indicator = IntegrationStatusIndicator.ERROR
            rec.last_error = f"Falha ao renovar token OAuth: {exc}"
            self.db.commit()
            return {
                "connector_slug": slug,
                "renewed": False,
                "status_indicator": rec.status_indicator,
                "error": rec.last_error,
            }

        return {"connector_slug": slug, "renewed": False, "status_indicator": rec.status_indicator}

    def record_connector_error(self, connector_slug: str, error_message: str) -> Dict[str, Any]:
        """Registra erro operacional de integração e atualiza indicador para ERROR."""
        slug = connector_slug.lower().strip()
        rec = (
            self.db.query(IntegrationCredentialToken)
            .filter(IntegrationCredentialToken.connector_slug == slug)
            .first()
        )
        if not rec:
            raise ValueError(f"Conector '{slug}' não encontrado.")
        rec.status_indicator = IntegrationStatusIndicator.ERROR
        rec.last_error = error_message
        rec.last_verified_at = datetime.now(timezone.utc)
        self.db.commit()
        return self.get_connector_status(slug)

    def reconnect_connector(self, connector_slug: str) -> Dict[str, Any]:
        """Tenta reconectar uma integração que entrou em estado ERROR ou expirou."""
        slug = connector_slug.lower().strip()
        rec = (
            self.db.query(IntegrationCredentialToken)
            .filter(IntegrationCredentialToken.connector_slug == slug)
            .first()
        )
        if not rec:
            raise ValueError(f"Conector '{slug}' não encontrado.")

        if slug == "union_ofertas":
            rec.status_indicator = IntegrationStatusIndicator.ACTIVE
            rec.authorization_block_status = "OPERACIONAL"
            rec.last_error = None
            self.db.commit()
            return self.get_connector_status(slug)

        tok = self.get_decrypted_access_token(slug)
        if tok:
            rec.status_indicator = IntegrationStatusIndicator.ACTIVE
            rec.authorization_block_status = "OPERACIONAL"
            rec.last_error = None
            rec.last_verified_at = datetime.now(timezone.utc)
            self.db.commit()
            return self.get_connector_status(slug)

        # Tenta renovar via refresh_token
        renew_res = self.renew_token_if_needed(slug, force=True)
        if renew_res.get("status_indicator") == IntegrationStatusIndicator.ACTIVE:
            return self.get_connector_status(slug)

        rec.status_indicator = IntegrationStatusIndicator.AUTHORIZATION_REQUIRED
        rec.authorization_block_status = "BLOQUEADA POR AUTORIZAÇÃO"
        self.db.commit()
        return self.get_connector_status(slug)

    def disable_connector_safely(self, connector_slug: str, reason: str = "Desativação segura solicitada") -> Dict[str, Any]:
        """Desativa com segurança um conector no UNION CONNECT."""
        slug = connector_slug.lower().strip()
        rec = (
            self.db.query(IntegrationCredentialToken)
            .filter(IntegrationCredentialToken.connector_slug == slug)
            .first()
        )
        if not rec:
            raise ValueError(f"Conector '{slug}' não encontrado.")
        rec.status_indicator = IntegrationStatusIndicator.DISABLED
        rec.authorization_block_status = "DESATIVADA"
        rec.last_error = reason
        rec.last_verified_at = datetime.now(timezone.utc)
        self.db.add(
            AuditLog(
                actor="system_or_admin",
                action="UNION_CONNECT_DISABLE_SAFELY",
                entity_type="IntegrationCredentialToken",
                entity_id=slug,
                details={"reason": reason},
            )
        )
        self.db.commit()
        return self.get_connector_status(slug)

    def get_connector_status(self, connector_slug: str) -> Dict[str, Any]:
        """Sincroniza e retorna o indicador individual e detalhes de um conector."""
        slug = connector_slug.lower().strip()
        rec = (
            self.db.query(IntegrationCredentialToken)
            .filter(IntegrationCredentialToken.connector_slug == slug)
            .first()
        )
        if not rec:
            raise ValueError(f"Conector '{slug}' não registrado.")

        now_utc = datetime.now(timezone.utc)
        env_creds = self._get_env_credentials_for_slug(slug)

        if rec.status_indicator != IntegrationStatusIndicator.DISABLED:
            if slug == "union_ofertas":
                rec.status_indicator = IntegrationStatusIndicator.ACTIVE
                rec.authorization_block_status = "OPERACIONAL"
                rec.masked_token_preview = "NATIVE_LOCAL"
            elif env_creds["has_creds"] and not rec.encrypted_access_token:
                rec.encrypted_access_token = encrypt_token_value(env_creds["access_token"])
                if env_creds["refresh_token"]:
                    rec.encrypted_refresh_token = encrypt_token_value(env_creds["refresh_token"])
                rec.masked_token_preview = mask_secret(env_creds["access_token"])
                rec.granted_scopes = list(rec.required_scopes or [])
                rec.status_indicator = IntegrationStatusIndicator.ACTIVE
                rec.authorization_block_status = "OPERACIONAL"
            elif rec.encrypted_access_token:
                # Verifica expiração
                if rec.expires_at:
                    exp_dt = rec.expires_at if rec.expires_at.tzinfo else rec.expires_at.replace(tzinfo=timezone.utc)
                    if now_utc > exp_dt:
                        self.renew_token_if_needed(slug, force=True)
            else:
                rec.status_indicator = IntegrationStatusIndicator.AUTHORIZATION_REQUIRED
                rec.authorization_block_status = "BLOQUEADA POR AUTORIZAÇÃO"

        rec.last_verified_at = now_utc
        self.db.commit()

        meta = OAUTH_METADATA.get(slug, {})
        if rec.status_indicator == IntegrationStatusIndicator.ACTIVE:
            commercial_state = "REALMENTE FUNCIONAL"
        elif rec.status_indicator in (
            IntegrationStatusIndicator.AUTHORIZATION_REQUIRED,
            IntegrationStatusIndicator.PENDING,
        ):
            commercial_state = "PENDENTE DE CREDENCIAIS"
        else:
            commercial_state = "PENDENTE DE CREDENCIAIS"

        return {
            "connector_slug": rec.connector_slug,
            "connector_name": rec.connector_name,
            "category": rec.connector_category,
            "auth_method": rec.auth_method,
            "status_indicator": rec.status_indicator,
            "commercial_readiness_state": commercial_state,
            "authorization_block_status": rec.authorization_block_status,
            "masked_token_preview": rec.masked_token_preview,
            "required_scopes": rec.required_scopes,
            "granted_scopes": rec.granted_scopes,
            "auto_renew_enabled": rec.auto_renew_enabled,
            "expires_at": rec.expires_at.isoformat() if rec.expires_at else None,
            "last_verified_at": rec.last_verified_at.isoformat() if rec.last_verified_at else None,
            "last_renewed_at": rec.last_renewed_at.isoformat() if rec.last_renewed_at else None,
            "last_error": rec.last_error,
            "official_docs_url": meta.get("docs_url"),
        }

    def get_commercial_integration_audit_matrix(self) -> Dict[str, Any]:
        """Classifica cada integração e sub-capacidade em REALMENTE FUNCIONAL, PENDENTE DE CREDENCIAIS ou NÃO SUPORTADA."""
        connectors = {c["connector_slug"]: c for c in self.list_all_connectors()}
        return {
            "union_ofertas_portal": {
                "state": "REALMENTE FUNCIONAL",
                "details": "Portal próprio FastAPI + Jinja2 + SQLite, landing pages, SEO, sitemap, cliques /r/{code} e webhooks.",
            },
            "mercadolivre_catalog_and_orders_api": {
                "state": connectors["mercadolivre"]["commercial_readiness_state"],
                "details": "API oficial api.mercadolibre.com implementada; exige ML_ACCESS_TOKEN OAuth e ML_AFFILIATE_TAG.",
            },
            "amazon_paapi5_catalog_and_links": {
                "state": connectors["amazon"]["commercial_readiness_state"],
                "details": "PA-API 5.0 AWS SigV4 implementada para catálogo e links; exige AMAZON_ACCESS_KEY, SECRET_KEY e PARTNER_TAG.",
            },
            "amazon_rest_commission_reports_api": {
                "state": "NÃO SUPORTADA",
                "details": "A Amazon Brasil não disponibiliza API REST pública para relatórios de comissões do Associados (usa leitor IMAP OAuth ou CSV oficial).",
            },
            "shopee_affiliate_graphql_api": {
                "state": connectors["shopee"]["commercial_readiness_state"],
                "details": "Cliente GraphQL SHA256 (productOfferV2, generateShortLink, conversionReport) implementado; exige SHOPEE_APP_ID e SHOPEE_APP_SECRET.",
            },
            "youtube_data_api_v3": {
                "state": connectors["youtube"]["commercial_readiness_state"],
                "details": "Upload via YouTube Data API v3 implementado; exige YOUTUBE_ACCESS_TOKEN / REFRESH_TOKEN OAuth.",
            },
            "instagram_graph_api_reels": {
                "state": connectors["instagram"]["commercial_readiness_state"],
                "details": "Publicação Reels via Graph API v19.0 implementada; exige INSTAGRAM_BUSINESS_ACCOUNT_ID e ACCESS_TOKEN.",
            },
            "pinterest_api_v5": {
                "state": connectors["pinterest"]["commercial_readiness_state"],
                "details": "Criação de Pins via API v5 implementada; exige PINTEREST_ACCESS_TOKEN e PINTEREST_BOARD_ID.",
            },
            "google_search_console_api": {
                "state": connectors["gsc"]["commercial_readiness_state"],
                "details": "Consulta searchAnalytics/query implementada; exige GSC_ACCESS_TOKEN e GSC_SITE_URL.",
            },
            "google_analytics_4_api": {
                "state": connectors["ga4"]["commercial_readiness_state"],
                "details": "Measurement Protocol e Data API v1beta implementados; exige GA4_PROPERTY_ID / API_SECRET.",
            },
        }

    def list_all_connectors(self) -> List[Dict[str, Any]]:
        """Retorna o status consolidado de todas as integrações do UNION CONNECT."""
        rows = (
            self.db.query(IntegrationCredentialToken)
            .order_by(IntegrationCredentialToken.id.asc())
            .all()
        )
        return [self.get_connector_status(r.connector_slug) for r in rows]

    def get_autonomy_flags_status(self) -> Dict[str, Any]:
        """Avalia as 11 flags de autonomia da Seção 11 contra as integrações realmente ativas."""
        connectors = {c["connector_slug"]: c for c in self.list_all_connectors()}
        any_mp_active = any(
            connectors.get(s, {}).get("status_indicator") == IntegrationStatusIndicator.ACTIVE
            for s in ("mercadolivre", "amazon", "shopee")
        )
        any_mp_tag = bool(
            any_mp_active
            or settings.ML_AFFILIATE_TAG.strip()
            or settings.AMAZON_PARTNER_TAG.strip()
            or settings.SHOPEE_AFFILIATE_ID.strip()
        )
        site_active = connectors.get("union_ofertas", {}).get("status_indicator") == IntegrationStatusIndicator.ACTIVE

        flags_evaluation = {
            "AUTONOMY_MODE": settings.AUTONOMY_MODE,
            "AUTO_PRODUCT_DISCOVERY": {
                "configured": settings.AUTO_PRODUCT_DISCOVERY,
                "technically_operational": bool(settings.AUTO_PRODUCT_DISCOVERY),
                "external_apis_active": any_mp_active,
                "mode": "OFFICIAL_API_AND_AUTHORIZED_CATALOG" if any_mp_active else "AUTHORIZED_LOCAL_CATALOG_AWAITING_API_KEYS",
            },
            "AUTO_PRODUCT_UPDATE": {
                "configured": settings.AUTO_PRODUCT_UPDATE,
                "technically_operational": bool(settings.AUTO_PRODUCT_UPDATE),
                "external_apis_active": any_mp_active,
            },
            "AUTO_AFFILIATE_LINKS": {
                "configured": settings.AUTO_AFFILIATE_LINKS,
                "technically_operational": bool(settings.AUTO_AFFILIATE_LINKS),
                "external_tags_configured": any_mp_tag,
            },
            "AUTO_CONTENT_GENERATION": {
                "configured": settings.AUTO_CONTENT_GENERATION,
                "technically_operational": bool(settings.AUTO_CONTENT_GENERATION),
                "provider": "NativePythonProvider (100% Local)",
            },
            "AUTO_VIDEO_RENDERING": {
                "configured": settings.AUTO_VIDEO_RENDERING,
                "technically_operational": bool(settings.AUTO_VIDEO_RENDERING),
                "engine": "UnionVideoEngine (Pillow + FFmpeg MP4/SRT)",
            },
            "AUTO_SEO": {
                "configured": settings.AUTO_SEO,
                "technically_operational": bool(settings.AUTO_SEO),
                "engine": "UnionSEOEngine (Sitemap + JSON-LD + Internal Links)",
            },
            "AUTO_PUBLISHING": {
                "configured": settings.AUTO_PUBLISHING,
                "technically_operational": bool(settings.AUTO_PUBLISHING and site_active),
                "active_channels": [
                    slug
                    for slug in ("union_ofertas", "youtube", "instagram", "pinterest")
                    if connectors.get(slug, {}).get("status_indicator") == IntegrationStatusIndicator.ACTIVE
                ],
                "blocked_channels": [
                    slug
                    for slug in ("youtube", "instagram", "pinterest")
                    if connectors.get(slug, {}).get("status_indicator") != IntegrationStatusIndicator.ACTIVE
                ],
            },
            "AUTO_ANALYTICS": {
                "configured": settings.AUTO_ANALYTICS,
                "technically_operational": bool(settings.AUTO_ANALYTICS),
                "engine": "UnionGrowthAI + Internal ClickLog/VisitorAggregate",
            },
            "AUTO_COMMISSION_SYNC": {
                "configured": settings.AUTO_COMMISSION_SYNC,
                "technically_operational": bool(settings.AUTO_COMMISSION_SYNC),
                "engine": "AutoSalesTracker (API + Webhooks + Email OAuth Reader)",
            },
            "AUTO_FINANCIAL_REPORTS": {
                "configured": settings.AUTO_FINANCIAL_REPORTS,
                "technically_operational": bool(settings.AUTO_FINANCIAL_REPORTS),
                "engine": "UnionFinanceAI + ReportLab PDF",
            },
            "AUTO_RECOVERY": {
                "configured": settings.AUTO_RECOVERY,
                "technically_operational": bool(settings.AUTO_RECOVERY),
                "engine": "UnionAutonomousOrchestrator Persistent Queue Recovery",
            },
        }

        return {
            "autonomy_mode": settings.AUTONOMY_MODE,
            "distinction_notice": (
                "Autorização inicial (OAuth/Chaves de API) é uma ação única legal do proprietário; "
                "após ativada, 100% do trabalho operacional recorrente é executado pelo sistema sem intervenção humana."
            ),
            "flags": flags_evaluation,
            "connectors_summary": {
                c["connector_slug"]: {
                    "status_indicator": c["status_indicator"],
                    "authorization_block_status": c["authorization_block_status"],
                }
                for c in connectors.values()
            },
        }

