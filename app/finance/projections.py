"""Estimativas Estatísticas e Projeções (JAMAIS apresentadas como resultados realizados)."""

from typing import Any, Dict
from sqlalchemy.orm import Session
from app.finance.cashflow import get_cashflow_summary
from app.finance.revenue import get_revenue_by_period


def get_transparent_projections(db: Session) -> Dict[str, Any]:
    """Retorna estimativa estatística claramente separada de resultados realizados."""
    by_period = get_revenue_by_period(db)
    summary = get_cashflow_summary(db)

    if len(by_period) < 3:
        return {
            "is_realized_result": False,
            "status": "AGUARDANDO DADOS REAIS",
            "disclaimer": "Projeções exigem no mínimo 3 períodos distintos com receita confirmada e nunca representam garantia de ganho.",
            "daily_average_confirmed_brl": None,
            "estimated_30d_pace_brl": None,
        }

    total_rev = sum(item["confirmed_revenue_brl"] for item in by_period)
    days_with_data = len(by_period)
    daily_avg = round(total_rev / days_with_data, 2)

    return {
        "is_realized_result": False,
        "status": "ESTIMATIVA_ESTATISTICA_NAO_REALIZADA",
        "disclaimer": (
            "ATENÇÃO: Estes números são apenas extrapolação aritmética do ritmo passado e "
            "NÃO representam faturamento garantido ou resultado realizado."
        ),
        "realized_net_cashflow_brl": summary["net_cashflow_brl"],
        "daily_average_confirmed_brl": daily_avg,
        "estimated_30d_pace_brl": round(daily_avg * 30.0, 2),
    }

