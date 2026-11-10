"""UNION GROWTH MANAGER — Motor de Reinvestimento e Recomendação de Alocação de Caixa Recebido (Seção 3).

Regras estritas:
1. Não gasta dinheiro automaticamente (auto_spend_allowed = False).
2. Apenas recomenda alocação (recommendation_only = True).
3. Exige aprovação humana para qualquer despesa (human_approval_required = True).
4. Não compromete caixa inexistente (opera estritamente sobre o saldo líquido de comissões PAID).
"""

from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from app.finance.union_finance_ai import UnionFinanceAI
from app.models.audit import AuditLog, SystemSetting


DEFAULT_GROWTH_ALLOCATIONS: Dict[str, float] = {
    "cash_reserve_pct": 30.0,
    "infrastructure_pct": 10.0,
    "content_production_pct": 20.0,
    "organic_growth_pct": 15.0,
    "optional_tools_pct": 5.0,
    "tax_reserve_pct": 10.0,
    "available_profit_pct": 10.0,
}


class UnionGrowthManager:
    """Motor consultivo de distribuição do caixa efetivamente recebido."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_allocation_weights(self) -> Dict[str, float]:
        """Obtém os percentuais de alocação configurados (normalizados para somar 100%)."""
        setting = (
            self.db.query(SystemSetting)
            .filter(SystemSetting.key == "growth_manager_allocations")
            .first()
        )
        raw = dict(DEFAULT_GROWTH_ALLOCATIONS)
        if setting and isinstance(setting.value_json, dict):
            for k in raw:
                if k in setting.value_json and float(setting.value_json[k]) >= 0:
                    raw[k] = float(setting.value_json[k])

        total = sum(raw.values())
        if total <= 0:
            return dict(DEFAULT_GROWTH_ALLOCATIONS)
        return {k: round((v / total) * 100.0, 2) for k, v in raw.items()}

    def update_allocation_weights(self, new_weights: Dict[str, float], actor: str = "admin") -> Dict[str, float]:
        """Atualiza os percentuais de recomendação de reinvestimento."""
        clean: Dict[str, float] = {}
        for k in DEFAULT_GROWTH_ALLOCATIONS:
            val = float(new_weights.get(k, DEFAULT_GROWTH_ALLOCATIONS[k]))
            if val < 0:
                raise ValueError(f"O percentual de '{k}' não pode ser negativo.")
            clean[k] = val

        if sum(clean.values()) <= 0:
            raise ValueError("A soma dos percentuais de alocação deve ser maior que zero.")

        setting = (
            self.db.query(SystemSetting)
            .filter(SystemSetting.key == "growth_manager_allocations")
            .first()
        )
        if not setting:
            setting = SystemSetting(
                key="growth_manager_allocations",
                value_json=clean,
                description="Alocação recomendada pelo UNION GROWTH MANAGER (%)",
            )
            self.db.add(setting)
        else:
            setting.value_json = clean

        self.db.add(
            AuditLog(
                actor=actor,
                action="UPDATE_GROWTH_ALLOCATIONS",
                entity_type="SystemSetting",
                entity_id="growth_manager_allocations",
                details=clean,
            )
        )
        self.db.commit()
        return self.get_allocation_weights()

    def recommend_reinvestment(self, override_received_cash_brl: Optional[float] = None) -> Dict[str, Any]:
        """Gera recomendação de distribuição exclusivamente sobre o caixa líquido efetivamente recebido."""
        finance = UnionFinanceAI(self.db).get_full_indicators()
        realized_net_cash = (
            float(override_received_cash_brl)
            if override_received_cash_brl is not None
            else float(finance["net_cash_received_brl"])
        )
        # Jamais compromete caixa inexistente ou negativo
        allocatable_cash = max(0.0, realized_net_cash)
        weights = self.get_allocation_weights()

        categories_breakdown = {
            "reserva_de_caixa": {
                "percentage": weights["cash_reserve_pct"],
                "recommended_brl": round(allocatable_cash * (weights["cash_reserve_pct"] / 100.0), 2),
                "description": "Colchão de liquidez e segurança operacional.",
            },
            "infraestrutura": {
                "percentage": weights["infrastructure_pct"],
                "recommended_brl": round(allocatable_cash * (weights["infrastructure_pct"] / 100.0), 2),
                "description": "Domínio, hospedagem, armazenamento e backups.",
            },
            "producao_de_conteudo": {
                "percentage": weights["content_production_pct"],
                "recommended_brl": round(allocatable_cash * (weights["content_production_pct"] / 100.0), 2),
                "description": "Expansão de pautas, mídia e ativos editoriais.",
            },
            "crescimento_organico": {
                "percentage": weights["organic_growth_pct"],
                "recommended_brl": round(allocatable_cash * (weights["organic_growth_pct"] / 100.0), 2),
                "description": "SEO, distribuição orgânica e construção de audiência.",
            },
            "ferramentas_opcionais": {
                "percentage": weights["optional_tools_pct"],
                "recommended_brl": round(allocatable_cash * (weights["optional_tools_pct"] / 100.0), 2),
                "description": "Utilitários complementares mediante aprovação manual.",
            },
            "reserva_de_impostos": {
                "percentage": weights["tax_reserve_pct"],
                "recommended_brl": round(allocatable_cash * (weights["tax_reserve_pct"] / 100.0), 2),
                "description": "Provisão tributária e obrigações fiscais.",
            },
            "lucro_disponivel": {
                "percentage": weights["available_profit_pct"],
                "recommended_brl": round(allocatable_cash * (weights["available_profit_pct"] / 100.0), 2),
                "description": "Resultado livre para acumulação patrimonial.",
            },
        }

        return {
            "status": "RECOMMENDATION_READY" if allocatable_cash > 0 else "NO_ALLOCATABLE_CASH",
            "realized_net_cash_received_brl": round(realized_net_cash, 2),
            "allocatable_cash_brl": round(allocatable_cash, 2),
            "auto_spend_allowed": False,
            "recommendation_only": True,
            "human_approval_required": True,
            "can_commit_non_existent_cash": False,
            "allocations": categories_breakdown,
            "governance_notice": (
                "Nenhuma despesa é executada automaticamente. Qualquer alocação exige "
                "aprovação humana explícita e saldo líquido efetivamente pago (PAID)."
            ),
        }

