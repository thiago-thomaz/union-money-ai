"""UNION WEALTH SIMULATOR — Simulador Matemático de Crescimento rumo a R$ 1.000.000 (Seção 2).

Separa rigorosamente:
- Indicador A: Meta de R$ 1.000.000 de PATRIMÔNIO acumulado (aportes + resultado líquido retido).
- Indicador B: Meta de R$ 1.000.000 de RECEITA bruta acumulada de comissões.

Regras:
- Resultados são simulações matemáticas baseadas nas premissas informadas, jamais promessas de ganho.
- Não assume crescimento exponencial automático (utiliza progressão aritmética controlada quando há taxa mensal).
- Compara resultado previsto versus resultado efetivamente realizado no banco de dados.
"""

from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from app.config import settings
from app.finance.union_finance_ai import UnionFinanceAI


SCENARIO_PRESETS: Dict[str, Dict[str, float]] = {
    "CONSERVADOR": {
        "monthly_visitors": 5000.0,
        "ctr_pct": 4.0,
        "conversion_rate_pct": 1.5,
        "average_ticket_brl": 180.0,
        "average_commission_pct": 8.0,
        "cancellation_rate_pct": 10.0,
        "monthly_expenses_brl": 0.0,
        "tax_rate_pct": 6.0,
        "reinvestment_rate_pct": 20.0,
        "monthly_growth_rate_pct": 2.0,
        "initial_patrimony_brl": 0.0,
        "monthly_contribution_brl": 0.0,
    },
    "MODERADO": {
        "monthly_visitors": 15000.0,
        "ctr_pct": 5.5,
        "conversion_rate_pct": 2.2,
        "average_ticket_brl": 220.0,
        "average_commission_pct": 9.5,
        "cancellation_rate_pct": 8.0,
        "monthly_expenses_brl": 50.0,
        "tax_rate_pct": 6.0,
        "reinvestment_rate_pct": 30.0,
        "monthly_growth_rate_pct": 5.0,
        "initial_patrimony_brl": 0.0,
        "monthly_contribution_brl": 0.0,
    },
    "AGRESSIVO": {
        "monthly_visitors": 45000.0,
        "ctr_pct": 7.0,
        "conversion_rate_pct": 3.0,
        "average_ticket_brl": 280.0,
        "average_commission_pct": 11.0,
        "cancellation_rate_pct": 5.0,
        "monthly_expenses_brl": 150.0,
        "tax_rate_pct": 6.0,
        "reinvestment_rate_pct": 40.0,
        "monthly_growth_rate_pct": 8.0,
        "initial_patrimony_brl": 0.0,
        "monthly_contribution_brl": 0.0,
    },
}


class UnionWealthSimulator:
    """Simulador matemático auditável para acompanhamento das Metas A (Patrimônio) e B (Receita)."""

    PATRIMONY_GOAL_BRL = float(settings.LONG_TERM_PATRIMONY_GOAL_BRL)
    REVENUE_GOAL_BRL = 1_000_000.00
    HORIZONS_MONTHS = (12, 24, 36, 60)

    def __init__(self, db: Session) -> None:
        self.db = db

    def simulate(
        self,
        scenario: str = "MODERADO",
        custom_vars: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """Executa a simulação para 12, 24, 36 e 60 meses e compara com o realizado."""
        scen_key = scenario.upper().strip()
        if scen_key not in SCENARIO_PRESETS:
            scen_key = "MODERADO"

        premises = dict(SCENARIO_PRESETS[scen_key])
        if custom_vars:
            for k, v in custom_vars.items():
                if k in premises and v is not None:
                    premises[k] = float(v)

        visitors_base = max(0.0, premises["monthly_visitors"])
        ctr_ratio = max(0.0, premises["ctr_pct"]) / 100.0
        conv_ratio = max(0.0, premises["conversion_rate_pct"]) / 100.0
        avg_ticket = max(0.0, premises["average_ticket_brl"])
        avg_comm_pct = max(0.0, premises["average_commission_pct"]) / 100.0
        avg_comm_brl = round(avg_ticket * avg_comm_pct, 2)
        cancel_ratio = min(1.0, max(0.0, premises["cancellation_rate_pct"]) / 100.0)
        expenses = max(0.0, premises["monthly_expenses_brl"])
        tax_ratio = min(1.0, max(0.0, premises["tax_rate_pct"]) / 100.0)
        reinvest_ratio = min(1.0, max(0.0, premises["reinvestment_rate_pct"]) / 100.0)
        growth_linear_ratio = max(0.0, premises["monthly_growth_rate_pct"]) / 100.0
        initial_patrimony = max(0.0, premises["initial_patrimony_brl"])
        monthly_contribution = max(0.0, premises["monthly_contribution_brl"])

        # Fórmulas básicas exigidas na Seção 2 (Mês 1 base)
        base_clicks = round(visitors_base * ctr_ratio, 2)
        base_sales = round(base_clicks * conv_ratio, 2)
        base_gross_commission = round(base_sales * avg_comm_brl, 2)
        base_valid_commission = round(base_gross_commission * (1.0 - cancel_ratio), 2)
        base_taxes = round(base_valid_commission * tax_ratio, 2)
        base_operational_result = round(base_valid_commission - expenses - base_taxes, 2)

        projections_by_horizon: Dict[str, Dict[str, Any]] = {}
        accumulated_revenue = 0.0
        accumulated_patrimony = initial_patrimony
        accumulated_reinvestment = 0.0

        for month in range(1, 61):
            # Crescimento aritmético linear (não assume crescimento exponencial automático)
            multiplier = 1.0 + (growth_linear_ratio * (month - 1))
            m_visitors = visitors_base * multiplier
            m_clicks = m_visitors * ctr_ratio
            m_sales = m_clicks * conv_ratio
            m_gross_comm = m_sales * avg_comm_brl
            m_valid_comm = m_gross_comm * (1.0 - cancel_ratio)
            m_taxes = m_valid_comm * tax_ratio
            m_op_result = m_valid_comm - expenses - m_taxes

            m_reinvest = max(0.0, m_op_result * reinvest_ratio) if m_op_result > 0 else 0.0
            accumulated_revenue += m_valid_comm
            accumulated_reinvestment += m_reinvest
            accumulated_patrimony += m_op_result + monthly_contribution

            if month in self.HORIZONS_MONTHS:
                projections_by_horizon[f"{month}_months"] = {
                    "months": month,
                    "monthly_visitors_at_end": round(m_visitors, 0),
                    "monthly_clicks_at_end": round(m_clicks, 2),
                    "monthly_estimated_sales_at_end": round(m_sales, 2),
                    "monthly_estimated_commission_brl": round(m_valid_comm, 2),
                    "monthly_operational_result_brl": round(m_op_result, 2),
                    "accumulated_revenue_brl": round(accumulated_revenue, 2),
                    "accumulated_patrimony_brl": round(accumulated_patrimony, 2),
                    "accumulated_reinvestment_brl": round(accumulated_reinvestment, 2),
                    "goal_a_patrimony_progress_pct": round(
                        (max(0.0, accumulated_patrimony) / self.PATRIMONY_GOAL_BRL) * 100.0, 4
                    ),
                    "goal_b_revenue_progress_pct": round(
                        (max(0.0, accumulated_revenue) / self.REVENUE_GOAL_BRL) * 100.0, 4
                    ),
                }

        # Comparação com o resultado efetivamente realizado no banco de dados
        finance_ai = UnionFinanceAI(self.db)
        realized = finance_ai.get_full_indicators()
        realized_revenue_paid = realized["paid_commissions_brl"]
        realized_revenue_confirmed = realized["approved_commissions_brl"]
        realized_patrimony_cash = realized["net_cash_received_brl"]

        return {
            "is_realized_result": False,
            "simulation_disclaimer": (
                "IMPORTANTE: Os resultados abaixo são simulações matemáticas baseadas nas premissas "
                "informadas, NÃO promessas de ganhos. Crescimento linear (não exponencial)."
            ),
            "scenario": scen_key,
            "premises_used": {
                **premises,
                "average_commission_brl": avg_comm_brl,
            },
            "base_month_1_formula_breakdown": {
                "clicks": base_clicks,
                "estimated_sales": base_sales,
                "gross_estimated_commission_brl": base_gross_commission,
                "valid_estimated_commission_brl": base_valid_commission,
                "taxes_brl": base_taxes,
                "expenses_brl": expenses,
                "estimated_operational_result_brl": base_operational_result,
            },
            "goals": {
                "goal_a_patrimony_target_brl": self.PATRIMONY_GOAL_BRL,
                "goal_b_revenue_target_brl": self.REVENUE_GOAL_BRL,
                "note": "Patrimônio acumulado (Meta A) não se confunde com faturamento/receita acumulada (Meta B).",
            },
            "projections": projections_by_horizon,
            "comparison_projected_vs_realized": {
                "projected_month_1_commission_brl": base_valid_commission,
                "projected_month_1_operational_result_brl": base_operational_result,
                "realized_paid_revenue_brl": realized_revenue_paid,
                "realized_confirmed_revenue_brl": realized_revenue_confirmed,
                "realized_net_patrimony_cash_brl": realized_patrimony_cash,
                "difference_revenue_vs_month_1_brl": round(realized_revenue_paid - base_valid_commission, 2),
                "difference_patrimony_vs_month_1_brl": round(realized_patrimony_cash - base_operational_result, 2),
                "goal_a_realized_patrimony_progress_pct": round(
                    (max(0.0, realized_patrimony_cash) / self.PATRIMONY_GOAL_BRL) * 100.0, 4
                ),
                "goal_b_realized_revenue_progress_pct": round(
                    (max(0.0, realized_revenue_paid) / self.REVENUE_GOAL_BRL) * 100.0, 4
                ),
            },
        }

