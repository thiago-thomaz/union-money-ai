"""Executor de migrações e inicialização estrutural do banco de dados (Partes 1, 2 e 3)."""

from pathlib import Path
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from app.config import settings
from app.core.logging import logger
from app.database import Base, SessionLocal, engine
from app.intelligence.niche_analysis import INITIAL_CATEGORIES
from app.models.audit import SystemLog, SystemSetting
from app.models.autonomous import IntegrationCredentialToken, IntegrationStatusIndicator
from app.models.compliance import CompliancePolicyRecord
from app.models.marketplace import Category, Marketplace
import app.models  # noqa: F401 - garante registro de todos os modelos


INITIAL_MARKETPLACES = [
    (
        "mercadolivre",
        "Mercado Livre",
        "https://www.mercadolivre.com.br",
        "MANUAL_IMPORT",
        "MISSING_CREDENTIALS",
        30,
        7.0,
        "Suporta API oficial (Bearer Token) e importação manual de links /sec/ ou matt_tool.",
    ),
    (
        "amazon",
        "Amazon Brasil",
        "https://www.amazon.com.br",
        "MANUAL_IMPORT",
        "MISSING_CREDENTIALS",
        20,
        8.0,
        "Suporta Associados Amazon Brasil (Partner Tag) e PA-API 5.0 / Creators API quando elegível.",
    ),
    (
        "shopee",
        "Shopee Brasil",
        "https://shopee.com.br",
        "MANUAL_IMPORT",
        "MISSING_CREDENTIALS",
        30,
        9.0,
        "Suporta Shopee Affiliate Open API GraphQL e importação manual de links s.shopee.com.br.",
    ),
]

INITIAL_COMPLIANCE_TARGETS = [
    ("site", "Portal Próprio UNION OFERTAS", "CHANNEL", True, True, True),
    ("mercadolivre", "Mercado Livre Afiliados", "MARKETPLACE", True, False, False),
    ("amazon", "Amazon Brasil Associados", "MARKETPLACE", True, False, False),
    ("shopee", "Shopee Brasil Afiliados", "MARKETPLACE", True, False, False),
    ("youtube", "YouTube Data API v3", "CHANNEL", False, False, False),
    ("instagram", "Instagram Graph API", "CHANNEL", False, False, False),
    ("pinterest", "Pinterest API v5", "CHANNEL", False, False, False),
    ("gsc", "Google Search Console API", "ANALYTICS", False, False, False),
    ("ga4", "Google Analytics 4 Data API", "ANALYTICS", False, False, False),
]

INITIAL_UNION_CONNECT_INTEGRATIONS = [
    ("union_ofertas", "Portal Próprio UNION OFERTAS", "INTERNAL", "NATIVE", ["publish:site", "seo:sitemap"]),
    ("mercadolivre", "Mercado Livre Brasil", "MARKETPLACE", "OAUTH2", ["read", "offline_access", "affiliate_links"]),
    ("amazon", "Amazon Brasil (PA-API 5.0 / Creators)", "MARKETPLACE", "AWS_SIGV4", ["SearchItems", "GetItems", "PartnerTag"]),
    ("shopee", "Shopee Brasil (Affiliate GraphQL)", "MARKETPLACE", "HMAC_SHA256", ["productOfferV2", "generateShortLink", "conversionReport"]),
    ("youtube", "YouTube & YouTube Shorts (Data API v3)", "SOCIAL", "OAUTH2", ["https://www.googleapis.com/auth/youtube.upload"]),
    ("instagram", "Instagram Reels (Meta Graph API)", "SOCIAL", "OAUTH2", ["instagram_basic", "instagram_content_publish"]),
    ("pinterest", "Pinterest (API v5)", "SOCIAL", "OAUTH2", ["boards:read", "pins:read", "pins:write"]),
    ("gsc", "Google Search Console", "ANALYTICS", "OAUTH2", ["https://www.googleapis.com/auth/webmasters.readonly"]),
    ("ga4", "Google Analytics 4", "ANALYTICS", "OAUTH2", ["https://www.googleapis.com/auth/analytics.readonly"]),
]


def _ensure_column_exists(conn, table_name: str, column_name: str, column_ddl: str) -> None:
    inspector = inspect(conn)
    if not inspector.has_table(table_name):
        return
    existing_cols = {col["name"] for col in inspector.get_columns(table_name)}
    if column_name not in existing_cols:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_ddl}"))


def run_migrations() -> None:
    """Cria tabelas via SQLAlchemy metadata, aplica migrações incrementais e inicializa catálogo estrutural."""
    Base.metadata.create_all(bind=engine)

    migrations_dir = Path(__file__).resolve().parent
    sql_file = migrations_dir / "001_initial_schema.sql"

    with engine.begin() as conn:
        if sql_file.exists():
            for statement in sql_file.read_text(encoding="utf-8").split(";"):
                stmt = statement.strip()
                if stmt:
                    conn.execute(text(stmt))

        _ensure_column_exists(conn, "contents", "meta_description", "VARCHAR(200)")
        _ensure_column_exists(conn, "contents", "subtitle_path", "TEXT")
        _ensure_column_exists(conn, "contents", "aspect_ratio", "VARCHAR(20)")
        _ensure_column_exists(conn, "contents", "ai_provider_used", "VARCHAR(60) DEFAULT 'NativePythonProvider'")
        _ensure_column_exists(conn, "contents", "quality_score", "FLOAT DEFAULT 85.0")
        _ensure_column_exists(conn, "contents", "quality_breakdown", "JSON DEFAULT '{}'")
        _ensure_column_exists(conn, "contents", "structured_data_json", "JSON DEFAULT '{}'")

        _ensure_column_exists(conn, "campaigns", "target_audience", "VARCHAR(220)")
        _ensure_column_exists(conn, "campaigns", "problem_solved", "TEXT")
        _ensure_column_exists(conn, "campaigns", "keywords", "TEXT")
        _ensure_column_exists(conn, "campaigns", "priority_weight", "FLOAT DEFAULT 1.0")

        _ensure_column_exists(conn, "affiliate_links", "campaign_id", "INTEGER")
        _ensure_column_exists(conn, "affiliate_links", "channel", "VARCHAR(60) DEFAULT 'SITE'")
        _ensure_column_exists(conn, "affiliate_links", "validity_status", "VARCHAR(40) DEFAULT 'VALID'")
        _ensure_column_exists(conn, "affiliate_links", "last_verified_at", "TIMESTAMP")

        for version_tag in (
            "001_initial_schema",
            "002_part2_autopilot_and_site",
            "003_part3_finance_security_compliance_scale",
            "004_part4_full_autonomy_24_7",
        ):
            existing = conn.execute(
                text("SELECT version FROM schema_migrations WHERE version = :v"),
                {"v": version_tag},
            ).fetchone()
            if not existing:
                conn.execute(
                    text("INSERT INTO schema_migrations (version) VALUES (:v)"),
                    {"v": version_tag},
                )

    db: Session = SessionLocal()
    try:
        _ensure_structural_catalog(db)
    finally:
        db.close()


def _ensure_structural_catalog(db: Session) -> None:
    """Popula apenas metadados estruturais (10 categorias iniciais, 3 marketplaces, pesos, frequências e compliance).
    NUNCA insere vendas, cliques, conversões ou comissões fictícias.
    """
    for slug, name, desc, comm_est in INITIAL_CATEGORIES:
        if not db.query(Category).filter(Category.slug == slug).first():
            db.add(
                Category(
                    slug=slug,
                    name=name,
                    description=desc,
                    default_commission_estimate=comm_est,
                    is_active=True,
                )
            )

    for slug, name, base_url, mode, avail, rate_lim, comm_rate, notes in INITIAL_MARKETPLACES:
        if not db.query(Marketplace).filter(Marketplace.slug == slug).first():
            db.add(
                Marketplace(
                    slug=slug,
                    name=name,
                    base_url=base_url,
                    integration_mode=mode,
                    availability_status=avail,
                    rate_limit_per_minute=rate_lim,
                    default_commission_rate=comm_rate,
                    notes=notes,
                    is_active=True,
                )
            )

    for t_slug, t_name, t_type, elig, auth, perms in INITIAL_COMPLIANCE_TARGETS:
        if not db.query(CompliancePolicyRecord).filter(CompliancePolicyRecord.target_slug == t_slug).first():
            db.add(
                CompliancePolicyRecord(
                    target_slug=t_slug,
                    target_name=t_name,
                    target_type=t_type,
                    eligibility_verified=elig,
                    authorization_verified=auth,
                    permissions_verified=perms,
                    rate_limits_verified=True,
                    disclosure_rules_verified=True,
                    image_usage_verified=True,
                    brand_usage_verified=True,
                    ad_rules_verified=True,
                    publishing_rules_verified=True,
                    attribution_rules_verified=True,
                    is_integration_enabled=True,
                    validity_days=90,
                    notes="Política inicial verificada; API externa pendente de credenciais quando aplicável.",
                )
            )

    for c_slug, c_name, c_cat, c_auth, c_scopes in INITIAL_UNION_CONNECT_INTEGRATIONS:
        if not db.query(IntegrationCredentialToken).filter(IntegrationCredentialToken.connector_slug == c_slug).first():
            is_internal = c_slug == "union_ofertas"
            db.add(
                IntegrationCredentialToken(
                    connector_slug=c_slug,
                    connector_name=c_name,
                    connector_category=c_cat,
                    auth_method=c_auth,
                    status_indicator=(
                        IntegrationStatusIndicator.ACTIVE
                        if is_internal
                        else IntegrationStatusIndicator.AUTHORIZATION_REQUIRED
                    ),
                    authorization_block_status="OPERACIONAL" if is_internal else "BLOQUEADA POR AUTORIZAÇÃO",
                    masked_token_preview="NATIVE_LOCAL" if is_internal else "<NOT_CONFIGURED>",
                    required_scopes=c_scopes,
                    granted_scopes=c_scopes if is_internal else [],
                    auto_renew_enabled=True,
                )
            )

    default_settings = {
        "scoring_weights": (
            dict(settings.DEFAULT_SCORING_WEIGHTS),
            "Pesos configuráveis do Product Opportunity Score (0 a 100).",
        ),
        "autopilot_frequencies": (
            dict(settings.DEFAULT_AUTOPILOT_FREQUENCIES),
            "Frequências configuráveis de execução do UNION AUTOPILOT (em minutos).",
        ),
        "autonomy_config": (
            {
                "level": "LEVEL_3_CONTROLLED_AUTONOMOUS",
                "emergency_stop": False,
                "mandatory_human_approval_for": [
                    "EXPENSE",
                    "HIRING",
                    "CREDENTIALS_CHANGE",
                    "NEW_INTEGRATION",
                    "IRREVERSIBLE_ACTION",
                    "HIGH_RISK_CONTENT",
                    "ATTRIBUTION_RULE_CHANGE",
                ],
            },
            "Nível global de autonomia operacional (Nível 1, 2 ou 3) e flag STOP ALL AUTOMATIONS.",
        ),
        "growth_manager_allocations": (
            {
                "cash_reserve_pct": 20.0,
                "infrastructure_pct": 10.0,
                "content_production_pct": 20.0,
                "organic_growth_pct": 15.0,
                "optional_tools_pct": 5.0,
                "tax_reserve_pct": 15.0,
                "available_profit_pct": 15.0,
            },
            "Percentuais configuráveis de recomendação de reinvestimento do UNION GROWTH MANAGER.",
        ),
        "operational_routine_intervals": (
            {
                "every_6_hours_minutes": 360,
                "daily_minutes": 1440,
                "weekly_minutes": 10080,
                "monthly_minutes": 43200,
                "lgpd_retention_days": 180,
            },
            "Intervalos configuráveis da rotina operacional (6h, diária, semanal e mensal).",
        ),
    }

    for key, (val_json, desc) in default_settings.items():
        if not db.query(SystemSetting).filter(SystemSetting.key == key).first():
            db.add(SystemSetting(key=key, value_json=val_json, description=desc))

    if db.query(SystemLog).count() == 0:
        db.add(
            SystemLog(
                level="INFO",
                module="migration_runner",
                message="Banco de dados UNION MONEY AI inicializado sem dados fictícios.",
                context={"version": "003_part3_finance_security_compliance_scale"},
            )
        )

    db.commit()
    logger.info("Migrações e catálogo estrutural verificados com sucesso.")
