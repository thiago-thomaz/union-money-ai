"""Testes Unitários e de Integração da Parte 2:
- UNION AUTOPILOT (idempotência, retry com backoff, recuperação após reinício, ciclo completo)
- Arquitetura de Provedores de IA Gratuita e Content Quality Score
- UNION CONTENT ENGINE (todos os 13 formatos)
- UNION VIDEO ENGINE (formatos 9:16, 16:9 e 1:1 + legendas .srt + validação MP4)
"""

from pathlib import Path
from sqlalchemy.orm import Session
from app.automation.autopilot import UnionAutopilot
from app.content_engine.ai_providers import (
    HardwareInspector,
    LocalLLMProvider,
    NativePythonProvider,
    OptionalExternalProvider,
    ai_provider_router,
)
from app.content_engine.quality import ContentQualityScorer
from app.content_engine.union_content_engine import UnionContentEngine
from app.content_engine.video import UnionVideoEngine
from app.models.autopilot import AutopilotTaskRun
from app.models.marketplace import Category, Marketplace
from app.services.product_service import create_product


def test_ai_providers_and_hardware_inspector_never_block():
    hw = HardwareInspector.inspect()
    assert "total_ram_gb" in hw
    assert hw["gpu_required"] is False

    native = NativePythonProvider()
    assert native.is_available() is True

    local_llm = LocalLLMProvider(endpoint_url="http://127.0.0.1:59999")
    assert local_llm.is_available() is False
    # Deve fazer fallback transparente sem levantar erro
    out = local_llm.enhance_editorial_section("Texto factual original.", {})
    assert out == "Texto factual original."

    ext = OptionalExternalProvider(endpoint_url="http://127.0.0.1:59998")
    assert ext.is_available() is False
    assert ext.enhance_editorial_section("Texto seguro.", {}) == "Texto seguro."

    status = ai_provider_router.status_report()
    assert status["active_provider"] == "NativePythonProvider"


def test_content_quality_scorer_blocks_false_personal_test_and_missing_amazon_notice():
    scorer = ContentQualityScorer(min_score=75.0)

    # 1. Texto mentindo que testou fisicamente o produto -> Deve bloquear!
    bad_eval = scorer.evaluate(
        title="Análise Teclado Mecânico",
        body="Testamos em nosso laboratório por 3 meses este teclado de R$ 250,00. Link de afiliado.",
        product_title="Teclado Mecânico RGB",
        verified_price=250.0,
        marketplace_slug="mercadolivre",
        seo_keywords="teclado mecanico",
    )
    assert bad_eval["eligible_for_auto_publish"] is False
    assert len(bad_eval["violations"]) >= 1

    # 2. Produto da Amazon sem declaração obrigatória -> Deve bloquear!
    amz_missing = scorer.evaluate(
        title="Kindle 11a Geração: Vale a Pena?",
        body="# Kindle 11a Geração\n\nPreço consultado: R$ 499,00. Sujeito a alteração. Contém link de afiliado.",
        product_title="Kindle 11a Geração",
        verified_price=499.0,
        marketplace_slug="amazon",
        seo_keywords="kindle 11a geracao",
    )
    assert amz_missing["eligible_for_auto_publish"] is False
    assert any("Amazon" in v for v in amz_missing["violations"])


def test_union_content_engine_all_13_formats_and_video_engine_ratios(db_session: Session):
    mp = db_session.query(Marketplace).filter(Marketplace.slug == "amazon").first()
    cat = db_session.query(Category).filter(Category.slug == "informatica").first()
    assert mp and cat

    prod = create_product(
        db_session,
        {
            "title": "Monitor IPS 24 Polegadas Full HD 75Hz",
            "description": "Painel IPS antirreflexo com conexões HDMI e VGA.",
            "marketplace_id": mp.id,
            "category_id": cat.id,
            "price": 649.90,
            "original_price": 799.90,
            "announced_commission_rate": 8.0,
            "rating": 4.7,
            "review_count": 180,
            "demand_index": 85.0,
            "competition_index": 25.0,
            "content_potential_index": 88.0,
            "in_stock": True,
            "product_url": "https://www.amazon.com.br/dp/B08N5WRWNW",
            "affiliate_url": "https://www.amazon.com.br/dp/B08N5WRWNW?tag=associado-20",
        },
    )

    engine = UnionContentEngine(db_session)
    for fmt in UnionContentEngine.SUPPORTED_FORMATS:
        item = engine.produce(product=prod, content_type=fmt, aspect_ratio="9:16")
        assert item.id is not None
        assert item.content_type == fmt
        assert item.quality_score >= 75.0
        assert item.status == "READY"

    # Valida geração de vídeo nos 3 formatos exigidos (9:16, 16:9, 1:1)
    for ratio in ("9:16", "16:9", "1:1"):
        vres = UnionVideoEngine.generate_video(
            product_title=prod.title,
            price=prod.price,
            marketplace_name=mp.name,
            aspect_ratio=ratio,
            category_name=cat.name,
        )
        assert vres["aspect_ratio"] == ratio
        assert vres["scenes_count"] == 7
        assert Path(vres["subtitle_path"]).exists()
        assert Path(vres["thumbnail_path"]).exists()
        if vres["validated"]:
            assert Path(vres["video_path"]).exists()
            assert UnionVideoEngine.validate_mp4_file(Path(vres["video_path"])) is True


def test_union_autopilot_idempotency_retry_recovery_and_full_cycle(db_session: Session):
    mp = db_session.query(Marketplace).filter(Marketplace.slug == "mercadolivre").first()
    cat = db_session.query(Category).filter(Category.slug == "tecnologia").first()
    assert mp and cat

    create_product(
        db_session,
        {
            "title": "Smartwatch Fitness GPS Resistente à Água",
            "marketplace_id": mp.id,
            "category_id": cat.id,
            "price": 219.90,
            "original_price": 299.90,
            "announced_commission_rate": 11.0,
            "rating": 4.8,
            "review_count": 340,
            "demand_index": 90.0,
            "competition_index": 20.0,
            "content_potential_index": 92.0,
            "in_stock": True,
            "product_url": "https://www.mercadolivre.com.br/smartwatch-gps",
            "affiliate_url": "https://mercadolivre.com/sec/smartwatchgps",
        },
    )

    # 1. Testa recuperação de tarefa interrompida (RUNNING -> RECOVERED)
    stale = AutopilotTaskRun(
        task_name="stale_task_test",
        idempotency_key="stale-key-001",
        status="RUNNING",
        attempt_count=1,
    )
    db_session.add(stale)
    db_session.commit()

    recovered_count = UnionAutopilot.recover_interrupted_tasks(db_session)
    assert recovered_count == 1
    db_session.refresh(stale)
    assert stale.status == "RECOVERED"

    # 2. Testa retry com backoff quando uma tarefa falha na 1ª tentativa e passa na 2ª
    counter = {"calls": 0}

    def _flaky_task():
        counter["calls"] += 1
        if counter["calls"] == 1:
            raise RuntimeError("Falha transitória simulada")
        return {"ok": True}

    retry_res = UnionAutopilot.execute_task_with_controls(
        db=db_session,
        task_name="flaky_test_task",
        func=_flaky_task,
        idempotency_key="idem-flaky-1",
        max_retries=2,
        backoff_base_seconds=0.01,
    )
    assert retry_res["status"] == "COMPLETED"
    assert retry_res["attempt_count"] == 2

    # 3. Testa idempotência com a mesma chave
    idem_repeat = UnionAutopilot.execute_task_with_controls(
        db=db_session,
        task_name="flaky_test_task",
        func=_flaky_task,
        idempotency_key="idem-flaky-1",
    )
    assert idem_repeat["status"] == "SKIPPED_IDEMPOTENT"

    # 4. Executa ciclo completo do UNION AUTOPILOT
    cycle = UnionAutopilot.run_full_cycle(db=db_session, idempotency_key="cycle-part2-test")
    assert cycle["status"] == "COMPLETED"
    assert cycle["result"]["products_scored"] >= 1
    assert cycle["result"]["selected_opportunities"] >= 1
    assert len(cycle["result"]["contents_produced"]) >= 1
    assert len(cycle["result"]["queue_items_published"]) >= 1

