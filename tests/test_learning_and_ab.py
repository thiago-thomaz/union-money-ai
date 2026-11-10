"""Testes do Motor de Aprendizado Comercial e Experimentação A/B."""

from sqlalchemy.orm import Session
from app.intelligence.recommendation import (
    CommercialLearningEngine,
    evaluate_ab_experiment,
)
from app.marketing.campaign_manager import create_ab_experiment
from app.services.campaign_service import record_variant_event


def test_commercial_learning_engine_uses_deterministic_mode_when_low_volume(db_session: Session):
    engine = CommercialLearningEngine(db_session)
    report = engine.generate_learning_report()
    assert report["engine_mode"] == "DETERMINISTIC_STATISTICS_AND_RULES"
    assert report["metrics"]["confirmed_conversions"] == 0
    assert any("AGUARDANDO DADOS REAIS" in r for r in report["recommendations"])


def test_ab_experiment_statistical_winner_evaluation(db_session: Session):
    exp = create_ab_experiment(
        db=db_session,
        name="Teste de Headline Fone Bluetooth",
        dimension="TITLE",
        variants_data=[
            {"variant_key": "A", "headline_or_cta": "Fone Bluetooth em Oferta"},
            {"variant_key": "B", "headline_or_cta": "Análise Fone Bluetooth: Vale a Pena em 2026?"},
        ],
    )

    # Sem amostras suficientes -> COLLECTING_SAMPLES
    res_initial = evaluate_ab_experiment(db_session, exp.id)
    assert res_initial["conclusion"] == "COLLECTING_SAMPLES"

    # Registra dados estatisticamente significativos para a Variante B
    from app.models.campaign import ExperimentVariant
    variants = db_session.query(ExperimentVariant).filter(ExperimentVariant.experiment_id == exp.id).all()
    var_a = next(v for v in variants if v.variant_key == "A")
    var_b = next(v for v in variants if v.variant_key == "B")

    record_variant_event(db_session, var_a.id, impressions_delta=200, clicks_delta=6, conversions_delta=0)
    record_variant_event(db_session, var_b.id, impressions_delta=200, clicks_delta=32, conversions_delta=4)

    res_final = evaluate_ab_experiment(db_session, exp.id)
    assert res_final["conclusion"] == "WINNER_CONFIRMED"
    assert res_final["winning_variant_id"] == var_b.id
    assert res_final["confidence_level"] >= 90.0

