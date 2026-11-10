"""Autonomia Operacional (Níveis 1, 2 e 3) e Rotinas Operacionais Configuráveis (Seções 8 e 9)."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from app.automation.autopilot import UnionAutopilot
from app.core.compliance import UnionCompliance
from app.core.emergency import is_emergency_stopped
from app.core.monitoring import SystemMonitor
from app.finance.growth_manager import UnionGrowthManager
from app.finance.union_finance_ai import UnionFinanceAI
from app.finance.wealth_simulator import UnionWealthSimulator
from app.intelligence.opportunity import list_ranked_opportunities, score_and_update_product
from app.intelligence.recommendation import CommercialLearningEngine
from app.marketing.campaign_manager import apply_campaign_optimization_rules
from app.marketing.link_manager import UnionLinkManager
from app.models.affiliate import AffiliateLink
from app.models.audit import AuditLog, SystemSetting
from app.models.product import Product
from app.services.reporting_service import generate_pdf_executive_report
from scripts.backup_db import create_sqlite_backup


AUTONOMY_LEVELS = {
    "LEVEL_1_ASSISTED": {
        "level": 1,
        "code": "LEVEL_1_ASSISTED",
        "name": "Nível 1 — Assistido",
        "description": "O sistema sugere produtos, pautas e conteúdos. O administrador aprova tudo.",
        "auto_publish_own_site": False,
        "auto_publish_external_channels": False,
    },
    "LEVEL_2_SEMIAUTOMATIC": {
        "level": 2,
        "code": "LEVEL_2_SEMIAUTOMATIC",
        "name": "Nível 2 — Semiautomático",
        "description": "O sistema descobre produtos, gera conteúdos e agenda publicações no site próprio. Canais externos exigem aprovação.",
        "auto_publish_own_site": True,
        "auto_publish_external_channels": False,
    },
    "LEVEL_3_CONTROLLED_AUTONOMOUS": {
        "level": 3,
        "code": "LEVEL_3_CONTROLLED_AUTONOMOUS",
        "name": "Nível 3 — Autônomo Controlado",
        "description": "Opera automaticamente dentro de limites pré-aprovados, mantendo bloqueio humano obrigatório nas 7 ações restritas.",
        "auto_publish_own_site": True,
        "auto_publish_external_channels": True,
    },
}

MANDATORY_HUMAN_APPROVAL_ACTIONS = {
    "PAID_EXPENSE": "Gastos pagos ou compromissos financeiros",
    "NEW_INTEGRATION": "Ativação de novas integrações externas",
    "CREDENTIAL_CHANGE": "Alteração de credenciais ou chaves de API",
    "DAILY_LIMIT_EXCEEDED": "Mudança ou extrapolação de limites diários",
    "LOW_QUALITY_CONTENT": "Publicação de conteúdos com Content Quality Score < 70",
    "UNVERIFIED_EXTERNAL_CHANNEL": "Publicação em canais externos não verificados ou sem credenciais",
    "MASS_DELETION": "Exclusão em massa de registros",
}

DEFAULT_ROUTINE_INTERVALS = {
    "every_6_hours_minutes": 360,
    "daily_minutes": 1440,
    "weekly_minutes": 10080,
    "monthly_minutes": 43200,
}


class AutonomyManager:
    """Gerencia os 3 níveis de autonomia e impõe as travas humanas obrigatórias mesmo no Nível 3."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_config(self) -> Dict[str, Any]:
        setting = self.db.query(SystemSetting).filter(SystemSetting.key == "autonomy_config").first()
        base = {
            "level": "LEVEL_2_SEMIAUTOMATIC",
            "emergency_stop": False,
            "daily_publication_limit": 20,
            "require_human_approval_for": list(MANDATORY_HUMAN_APPROVAL_ACTIONS.keys()),
        }
        if setting and isinstance(setting.value_json, dict):
            base.update(setting.value_json)
        # Garante que as 7 travas obrigatórias estejam sempre presentes
        base["require_human_approval_for"] = list(MANDATORY_HUMAN_APPROVAL_ACTIONS.keys())
        level_code = str(base.get("level", "LEVEL_2_SEMIAUTOMATIC")).upper()
        if level_code not in AUTONOMY_LEVELS:
            level_code = "LEVEL_2_SEMIAUTOMATIC"
        base["level"] = level_code
        base["level_metadata"] = AUTONOMY_LEVELS[level_code]
        return base

    def set_level(
        self,
        level_code: str,
        daily_publication_limit: Optional[int] = None,
        actor: str = "admin",
    ) -> Dict[str, Any]:
        code = level_code.upper().strip()
        if code not in AUTONOMY_LEVELS:
            raise ValueError(f"Nível de autonomia inválido: {level_code}")

        setting = self.db.query(SystemSetting).filter(SystemSetting.key == "autonomy_config").first()
        cfg = self.get_config()
        cfg.pop("level_metadata", None)
        cfg["level"] = code
        if daily_publication_limit is not None and daily_publication_limit >= 1:
            cfg["daily_publication_limit"] = int(daily_publication_limit)
        cfg["require_human_approval_for"] = list(MANDATORY_HUMAN_APPROVAL_ACTIONS.keys())

        if not setting:
            setting = SystemSetting(
                key="autonomy_config",
                value_json=cfg,
                description="Configuração de nível de autonomia operacional e botão de emergência",
            )
            self.db.add(setting)
        else:
            setting.value_json = cfg

        self.db.add(
            AuditLog(
                actor=actor,
                action="UPDATE_AUTONOMY_LEVEL",
                entity_type="SystemSetting",
                entity_id="autonomy_config",
                details={"level": code, "daily_publication_limit": cfg["daily_publication_limit"]},
            )
        )
        self.db.commit()
        return self.get_config()

    def evaluate_action_permission(
        self,
        action_type: str,
        target_channel: str = "SITE",
        content_quality_score: float = 100.0,
    ) -> Dict[str, Any]:
        """Avalia se uma ação pode ser executada autonomamente ou se exige aprovação humana obrigatória."""
        cfg = self.get_config()
        level_code = cfg["level"]
        act = action_type.upper().strip()

        if cfg.get("emergency_stop"):
            return {
                "autonomous_execution_allowed": False,
                "requires_human_approval": True,
                "reason": "Botão de emergência STOP ALL AUTOMATIONS está ativo.",
                "autonomy_level": level_code,
            }

        # 1. Verifica as 7 ações que SEMPRE exigem aprovação humana (mesmo no Nível 3)
        if act in MANDATORY_HUMAN_APPROVAL_ACTIONS:
            return {
                "autonomous_execution_allowed": False,
                "requires_human_approval": True,
                "reason": f"Trava obrigatória de segurança ({act}): {MANDATORY_HUMAN_APPROVAL_ACTIONS[act]}",
                "autonomy_level": level_code,
            }

        # 2. Conteúdo com nota baixa (< 70) sempre exige aprovação humana
        if content_quality_score < 70.0:
            return {
                "autonomous_execution_allowed": False,
                "requires_human_approval": True,
                "reason": f"Content Quality Score ({content_quality_score}) abaixo do mínimo de 70 pontos.",
                "autonomy_level": level_code,
            }

        # 3. Canais externos não verificados sempre exigem aprovação humana
        chan_slug = target_channel.lower().strip()
        if chan_slug != "site":
            checklist = {c["target_slug"]: c for c in UnionCompliance(self.db).list_checklist()}
            chan_policy = checklist.get(chan_slug)
            if not chan_policy or not chan_policy["authorized_to_operate"]:
                return {
                    "autonomous_execution_allowed": False,
                    "requires_human_approval": True,
                    "reason": f"Canal externo '{target_channel}' pendente de credenciais ou verificação periódica.",
                    "autonomy_level": level_code,
                }

        # 4. Regras específicas dos Níveis 1, 2 e 3
        if level_code == "LEVEL_1_ASSISTED":
            return {
                "autonomous_execution_allowed": False,
                "requires_human_approval": True,
                "reason": "Nível 1 (Assistido): toda publicação ou execução final exige aprovação do administrador.",
                "autonomy_level": level_code,
            }

        if level_code == "LEVEL_2_SEMIAUTOMATIC":
            if chan_slug == "site":
                return {
                    "autonomous_execution_allowed": True,
                    "requires_human_approval": False,
                    "reason": "Nível 2 (Semiautomático): publicação autorizada no site próprio (UNION OFERTAS).",
                    "autonomy_level": level_code,
                }
            return {
                "autonomous_execution_allowed": False,
                "requires_human_approval": True,
                "reason": "Nível 2 (Semiautomático): canais externos exigem aprovação humana.",
                "autonomy_level": level_code,
            }

        # LEVEL_3_CONTROLLED_AUTONOMOUS (quando passou por todas as 7 travas e verificações de conformidade)
        return {
            "autonomous_execution_allowed": True,
            "requires_human_approval": False,
            "reason": "Nível 3 (Autônomo Controlado): ação dentro dos limites e políticas verificadas.",
            "autonomy_level": level_code,
        }


class OperationalRoutineManager:
    """Executa e configura as rotinas operacionais de 6h, diária, semanal e mensal (Seção 9)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_intervals(self) -> Dict[str, int]:
        setting = (
            self.db.query(SystemSetting)
            .filter(SystemSetting.key == "operational_routine_intervals")
            .first()
        )
        base = dict(DEFAULT_ROUTINE_INTERVALS)
        if setting and isinstance(setting.value_json, dict):
            for k, v in setting.value_json.items():
                if k in base and int(v) > 0:
                    base[k] = int(v)
        return base

    def update_intervals(self, new_intervals: Dict[str, int], actor: str = "admin") -> Dict[str, int]:
        base = dict(DEFAULT_ROUTINE_INTERVALS)
        for k, v in new_intervals.items():
            if k in base and int(v) > 0:
                base[k] = int(v)
        setting = (
            self.db.query(SystemSetting)
            .filter(SystemSetting.key == "operational_routine_intervals")
            .first()
        )
        if not setting:
            setting = SystemSetting(
                key="operational_routine_intervals",
                value_json=base,
                description="Frequências configuráveis das rotinas operacionais (6h, diária, semanal, mensal)",
            )
            self.db.add(setting)
        else:
            setting.value_json = base

        self.db.add(
            AuditLog(
                actor=actor,
                action="UPDATE_OPERATIONAL_ROUTINE_INTERVALS",
                entity_type="SystemSetting",
                entity_id="operational_routine_intervals",
                details=base,
            )
        )
        self.db.commit()
        return base

    def run_routine(self, period: str) -> Dict[str, Any]:
        """Executa uma das 4 rotinas operacionais: every_6_hours, daily, weekly ou monthly."""
        if is_emergency_stopped(self.db):
            return {
                "period": period,
                "status": "SKIPPED_EMERGENCY_STOP",
                "message": "Rotina suspensa porque STOP ALL AUTOMATIONS está ativo.",
            }

        p = period.lower().strip()
        now_iso = datetime.now(timezone.utc).isoformat()

        if p in ("every_6_hours", "6h"):
            # A cada 6 horas: verificar links, disponibilidade de produtos e erros
            link_review = UnionLinkManager.review_all_links(self.db)
            products = self.db.query(Product).filter(Product.is_active.is_(True), Product.is_synthetic_test.is_(False)).all()
            in_stock_count = sum(1 for pr in products if pr.in_stock)
            diag = SystemMonitor.run_full_diagnostics(self.db)
            return {
                "period": "every_6_hours",
                "executed_at": now_iso,
                "status": "COMPLETED",
                "links_checked": link_review["total_reviewed"],
                "valid_links": link_review["valid_active"],
                "active_products_checked": len(products),
                "in_stock_products": in_stock_count,
                "application_status": diag["application_status"],
            }

        if p == "daily":
            # Diariamente: descobrir oportunidades, atualizar pontuações, produzir conteúdos,
            # publicar no site próprio (conforme nível de autonomia), atualizar métricas e executar backup
            autonomy = AutonomyManager(self.db).get_config()
            auto_pub_site = autonomy["level_metadata"]["auto_publish_own_site"]
            cycle_res = UnionAutopilot.run_full_cycle(self.db, auto_publish_site=auto_pub_site)
            backup_path = create_sqlite_backup(db=self.db)
            return {
                "period": "daily",
                "executed_at": now_iso,
                "status": "COMPLETED",
                "autonomy_level": autonomy["level"],
                "autopilot_cycle": cycle_res,
                "backup_path": str(backup_path),
            }

        if p == "weekly":
            # Semanalmente: analisar produtos vencedores, pausar produtos fracos, revisar campanhas e gerar relatório semanal
            products = self.db.query(Product).filter(Product.is_active.is_(True), Product.is_synthetic_test.is_(False)).all()
            for pr in products:
                score_and_update_product(self.db, pr)
            winners = list_ranked_opportunities(self.db, min_score=75.0, limit=10)
            weak_paused = [
                pr.id
                for pr in products
                if (pr.opportunity_score is not None and pr.opportunity_score < 40.0) or not pr.in_stock
            ]
            camp_opt = apply_campaign_optimization_rules(self.db)
            learning = CommercialLearningEngine(self.db).generate_learning_report()
            pdf_path = generate_pdf_executive_report(self.db)
            return {
                "period": "weekly",
                "executed_at": now_iso,
                "status": "COMPLETED",
                "winning_products_count": len(winners),
                "weak_or_out_of_stock_flagged": weak_paused,
                "campaign_optimization": camp_opt,
                "learning_summary": learning["engine_mode"],
                "weekly_report_pdf": str(pdf_path),
            }

        if p == "monthly":
            # Mensalmente: consolidar comissões, comparar meta de R$ 1 milhão, recomendar reinvestimento e gerar relatório executivo PDF
            finance_ai = UnionFinanceAI(self.db)
            reconciliation = finance_ai.reconcile_commissions()
            wealth_comp = UnionWealthSimulator(self.db).simulate(scenario="MODERADO")
            growth_rec = UnionGrowthManager(self.db).recommend_reinvestment()
            pdf_path = generate_pdf_executive_report(self.db)
            return {
                "period": "monthly",
                "executed_at": now_iso,
                "status": "COMPLETED",
                "commission_reconciliation": reconciliation,
                "million_goal_comparison": wealth_comp["comparison_projected_vs_realized"],
                "reinvestment_recommendation": growth_rec,
                "executive_report_pdf": str(pdf_path),
            }

        raise ValueError(f"Período de rotina operacional desconhecido: {period}")

