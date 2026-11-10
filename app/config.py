"""Configurações globais do sistema UNION MONEY AI (Fases 1 a 4 — Autonomia Total)."""

from pathlib import Path
from typing import Dict
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Configurações carregadas de variáveis de ambiente ou arquivo .env."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "UNION MONEY AI"
    SITE_NAME: str = "UNION OFERTAS"
    APP_VERSION: str = "4.0.0"
    APP_ENV: str = "development"
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8000
    PUBLIC_BASE_URL: str = "http://127.0.0.1:8000"
    SECRET_KEY: str = "union-money-ai-default-local-secret-key"

    # Banco de dados (SQLite inicial; suporta PostgreSQL via URL)
    DATABASE_URL: str = f"sqlite:///{(BASE_DIR / 'data' / 'union_money_ai.db').as_posix()}"

    # Meta empresarial de longo prazo (referência informativa, não promessa)
    LONG_TERM_PATRIMONY_GOAL_BRL: float = 1_000_000.00

    # ==================================================
    # FASE 4: CONFIGURAÇÕES DE AUTONOMIA APÓS ATIVAÇÃO (Seção 11)
    # ==================================================
    AUTONOMY_MODE: str = "FULL"
    AUTO_PRODUCT_DISCOVERY: bool = True
    AUTO_PRODUCT_UPDATE: bool = True
    AUTO_AFFILIATE_LINKS: bool = True
    AUTO_CONTENT_GENERATION: bool = True
    AUTO_VIDEO_RENDERING: bool = True
    AUTO_SEO: bool = True
    AUTO_PUBLISHING: bool = True
    AUTO_ANALYTICS: bool = True
    AUTO_COMMISSION_SYNC: bool = True
    AUTO_FINANCIAL_REPORTS: bool = True
    AUTO_RECOVERY: bool = True

    # A. Credenciais Mercado Livre (OAuth 2.0 + Programa de Afiliados)
    ML_APP_ID: str = ""
    ML_CLIENT_SECRET: str = ""
    ML_ACCESS_TOKEN: str = ""
    ML_REFRESH_TOKEN: str = ""
    ML_AFFILIATE_TAG: str = ""

    # B. Credenciais Amazon Brasil (Associados + PA-API 5.0 / Creators API)
    AMAZON_PARTNER_TAG: str = ""
    AMAZON_ACCESS_KEY: str = ""
    AMAZON_SECRET_KEY: str = ""
    AMAZON_CREATORS_TOKEN: str = ""
    AMAZON_HOST: str = "webservices.amazon.com.br"
    AMAZON_REGION: str = "us-east-1"

    # C. Credenciais Shopee Brasil (Open Platform Affiliate GraphQL API)
    SHOPEE_APP_ID: str = ""
    SHOPEE_APP_SECRET: str = ""
    SHOPEE_AFFILIATE_ID: str = ""

    # D. Credenciais YouTube / YouTube Shorts (YouTube Data API v3 + OAuth 2.0)
    YOUTUBE_API_KEY: str = ""
    YOUTUBE_CLIENT_ID: str = ""
    YOUTUBE_CLIENT_SECRET: str = ""
    YOUTUBE_ACCESS_TOKEN: str = ""
    YOUTUBE_REFRESH_TOKEN: str = ""

    # E. Credenciais Instagram Reels (Instagram Graph API + OAuth)
    INSTAGRAM_APP_ID: str = ""
    INSTAGRAM_APP_SECRET: str = ""
    INSTAGRAM_ACCESS_TOKEN: str = ""
    INSTAGRAM_BUSINESS_ACCOUNT_ID: str = ""

    # F. Credenciais Pinterest (Pinterest API v5 + OAuth 2.0)
    PINTEREST_APP_ID: str = ""
    PINTEREST_APP_SECRET: str = ""
    PINTEREST_ACCESS_TOKEN: str = ""
    PINTEREST_REFRESH_TOKEN: str = ""
    PINTEREST_BOARD_ID: str = ""

    # G. Credenciais Google Search Console (Search Console API + OAuth 2.0)
    GSC_CLIENT_ID: str = ""
    GSC_CLIENT_SECRET: str = ""
    GSC_ACCESS_TOKEN: str = ""
    GSC_REFRESH_TOKEN: str = ""
    GSC_SITE_URL: str = ""

    # H. Credenciais Google Analytics 4 (GA4 Data API + Measurement Protocol)
    GA4_PROPERTY_ID: str = ""
    GA4_MEASUREMENT_ID: str = ""
    GA4_API_SECRET: str = ""
    GA4_ACCESS_TOKEN: str = ""

    # Leitura Automática Opcional de Relatórios Oficiais por E-mail (IMAP + OAuth Somente Leitura)
    REPORT_EMAIL_IMAP_HOST: str = ""
    REPORT_EMAIL_USER: str = ""
    REPORT_EMAIL_OAUTH_TOKEN: str = ""

    # Provedores de IA Gratuita / Local (Opcional; NativePythonProvider é o padrão garantido)
    LOCAL_LLM_URL: str = ""
    LOCAL_LLM_MODEL: str = "qwen2.5:1.5b"
    OPTIONAL_EXTERNAL_AI_URL: str = ""
    MIN_CONTENT_QUALITY_SCORE: float = 75.0

    # Notificações Opcionais por E-mail (SMTP configurado pelo usuário; desligado por padrão)
    SMTP_ENABLED: bool = False
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_TO_EMAIL: str = ""

    # Agendador interno APScheduler (100% nativo, sem n8n)
    ENABLE_SCHEDULER: bool = True

    # Frequências padrão do UNION AUTOPILOT (em minutos)
    DEFAULT_AUTOPILOT_FREQUENCIES: Dict[str, int] = Field(
        default_factory=lambda: {
            "discovery_minutes": 60,
            "product_update_minutes": 45,
            "content_production_minutes": 30,
            "link_review_minutes": 90,
            "campaign_monitoring_minutes": 40,
            "financial_consolidation_minutes": 30,
            "reporting_minutes": 120,
        }
    )

    # Pesos padrão do Product Opportunity Score (total = 100)
    DEFAULT_SCORING_WEIGHTS: Dict[str, float] = Field(
        default_factory=lambda: {
            "demand_potential": 20.0,
            "offer_quality": 15.0,
            "estimated_commission": 20.0,
            "competition": 10.0,
            "review_quality": 10.0,
            "content_potential": 10.0,
            "data_reliability": 10.0,
            "availability": 5.0,
        }
    )

    @property
    def base_dir(self) -> Path:
        return BASE_DIR

    @property
    def ENVIRONMENT(self) -> str:
        return self.APP_ENV

    @property
    def HOST(self) -> str:
        return self.APP_HOST

    @property
    def PORT(self) -> int:
        return self.APP_PORT

    @property
    def data_dir(self) -> Path:
        path = BASE_DIR / "data"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def logs_dir(self) -> Path:
        path = BASE_DIR / "logs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def storage_dir(self) -> Path:
        path = BASE_DIR / "storage"
        for sub in ("products", "videos", "thumbnails", "reports", "publications"):
            (path / sub).mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
