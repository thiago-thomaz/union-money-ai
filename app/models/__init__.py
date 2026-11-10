"""Exportação consolidada de todos os modelos relacionais do UNION MONEY AI."""

from app.models.user import User
from app.models.marketplace import Category, Marketplace
from app.models.affiliate import AffiliateAccount, AffiliateLink
from app.models.product import Product
from app.models.campaign import Campaign, Experiment, ExperimentVariant
from app.models.content import ContentItem
from app.models.publication import Publication
from app.models.click import ClickLog, VisitorAggregate
from app.models.conversion import Conversion
from app.models.commission import Commission
from app.models.financial import Expense, FinancialHistory, RevenueRecord
from app.models.audit import AuditLog, SystemLog, SystemSetting
from app.models.autopilot import (
    AutopilotTaskRun,
    EditorialQueueItem,
    EditorialState,
    SystemAlert,
)
from app.models.compliance import (
    BackupRecord,
    CompliancePolicyRecord,
    ConsentRecord,
    SecurityIncident,
)
from app.models.autonomous import (
    ContentProductionPipeline,
    IntegrationCredentialToken,
    IntegrationStatusIndicator,
    PersistentOrchestratorQueue,
    PipelineStage,
)

__all__ = [
    "User",
    "Category",
    "Marketplace",
    "AffiliateAccount",
    "AffiliateLink",
    "Product",
    "Campaign",
    "Experiment",
    "ExperimentVariant",
    "ContentItem",
    "Publication",
    "VisitorAggregate",
    "ClickLog",
    "Conversion",
    "Commission",
    "RevenueRecord",
    "Expense",
    "FinancialHistory",
    "SystemLog",
    "AuditLog",
    "SystemSetting",
    "AutopilotTaskRun",
    "EditorialQueueItem",
    "EditorialState",
    "SystemAlert",
    "CompliancePolicyRecord",
    "ConsentRecord",
    "SecurityIncident",
    "BackupRecord",
    "IntegrationStatusIndicator",
    "PipelineStage",
    "IntegrationCredentialToken",
    "ContentProductionPipeline",
    "PersistentOrchestratorQueue",
]
