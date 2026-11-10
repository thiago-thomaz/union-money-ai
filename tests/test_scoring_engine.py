"""Testes do Motor de Pontuação (Product Opportunity Score 0 a 100)."""

from app.intelligence.product_scoring import (
    ProductOpportunityScorer,
    ProductScoringInput,
    ScoreClassification,
)


def test_scorer_does_not_assign_score_when_insufficient_data():
    scorer = ProductOpportunityScorer()
    # Sem comissão e sem dados mínimos
    inp = ProductScoringInput(
        price=120.0,
        in_stock=True,
        announced_commission_rate=None,
        effective_commission_rate=None,
    )
    res = scorer.evaluate(inp)
    assert res.sufficient_data is False
    assert res.score is None
    assert res.classification == ScoreClassification.INSUFFICIENT.value


def test_scorer_high_priority_opportunity_and_data_separation():
    scorer = ProductOpportunityScorer()
    inp = ProductScoringInput(
        price=250.0,
        original_price=380.0,
        in_stock=True,
        announced_commission_rate=12.0,
        effective_commission_rate=15.0,
        rating=4.9,
        review_count=450,
        demand_index=95.0,
        competition_index=10.0,
        content_potential_index=95.0,
        utility_score=95.0,
        verification_map={
            "price": "VERIFIED",
            "in_stock": "VERIFIED",
            "effective_commission_rate": "VERIFIED",
            "rating": "VERIFIED",
            "demand_index": "VERIFIED",
            "competition_index": "VERIFIED",
            "content_potential_index": "VERIFIED",
        },
    )
    res = scorer.evaluate(inp)
    assert res.sufficient_data is True
    assert res.score is not None
    assert res.score >= 90.0
    assert res.classification == "oportunidade prioritária"
    assert res.commission_basis == "EFFECTIVE_REALIZED"
    assert res.effective_vs_announced_gap_pct == 3.0
    assert res.confidence_score == 100.0
    assert "price" in res.data_separation["verified"]


def test_scorer_out_of_stock_caps_at_discard():
    scorer = ProductOpportunityScorer()
    inp = ProductScoringInput(
        price=150.0,
        original_price=200.0,
        in_stock=False,
        announced_commission_rate=14.0,
        rating=4.8,
        review_count=100,
        demand_index=85.0,
        competition_index=20.0,
        content_potential_index=80.0,
    )
    res = scorer.evaluate(inp)
    assert res.sufficient_data is True
    assert res.score is not None
    assert res.score <= 39.0
    assert res.classification == "descartar"


def test_scorer_custom_configurable_weights():
    custom = {
        "demand_potential": 40.0,
        "offer_quality": 10.0,
        "estimated_commission": 20.0,
        "competition": 5.0,
        "review_quality": 5.0,
        "content_potential": 10.0,
        "data_reliability": 5.0,
        "availability": 5.0,
    }
    scorer = ProductOpportunityScorer(custom_weights=custom)
    assert round(sum(scorer.weights.values()), 2) == 100.0
    assert scorer.weights["demand_potential"] == 40.0

