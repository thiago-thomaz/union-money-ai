"""Análise de Tendências e Relação Preço/Utilidade."""

from typing import Any, Dict, List


def evaluate_price_utility_ratio(price: float, original_price: float | None, rating: float | None) -> float:
    """Calcula índice de utilidade percebida vs preço (0 a 100)."""
    if price <= 0:
        return 0.0

    # Faixas de ticket de maior liquidez no varejo brasileiro de afiliados (R$ 35 a R$ 450)
    if 35.0 <= price <= 250.0:
        ticket_score = 85.0
    elif 250.0 < price <= 600.0:
        ticket_score = 72.0
    elif price < 35.0:
        ticket_score = 60.0
    else:
        ticket_score = 50.0

    discount_bonus = 0.0
    if original_price and original_price > price:
        discount_pct = ((original_price - price) / original_price) * 100.0
        discount_bonus = min(15.0, discount_pct * 0.4)

    rating_bonus = 0.0
    if rating and rating >= 4.0:
        rating_bonus = (rating - 4.0) * 10.0

    return round(min(100.0, max(0.0, ticket_score + discount_bonus + rating_bonus - 5.0)), 2)


def summarize_category_momentum(products_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Sumariza sinais de demanda e disponibilidade de uma lista de produtos."""
    if not products_data:
        return {
            "status": "AGUARDANDO DADOS REAIS",
            "average_demand_index": None,
            "in_stock_ratio": None,
            "sample_size": 0,
        }

    demands = [p["demand_index"] for p in products_data if p.get("demand_index") is not None]
    stocks = [1 if p.get("in_stock") else 0 for p in products_data if p.get("in_stock") is not None]

    return {
        "status": "ANALISADO",
        "average_demand_index": round(sum(demands) / len(demands), 2) if demands else None,
        "in_stock_ratio": round((sum(stocks) / len(stocks)) * 100.0, 2) if stocks else None,
        "sample_size": len(products_data),
    }

