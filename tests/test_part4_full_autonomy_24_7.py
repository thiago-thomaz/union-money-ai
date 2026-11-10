"""Suíte de Testes da Fase 4 — Autonomia Total e Operação Comercial 24/7 (Seção 14).

Separa claramente:
1. Testes unitários (UNION CONNECT, OAuth criptografado, renovação de token, links oficiais, travas do Growth AI)
2. Testes simulados / sandbox (Descoberta incremental autônoma, suspensão de produtos inválidos, pipeline de 9 estados)
3. Testes de publicação e prontidão de API real (Publicação imediata no UNION OFERTAS vs BLOQUEADA POR AUTORIZAÇÃO em canais externos sem credencial)
4. Testes financeiros automáticos (Webhooks assinados HMAC-SHA256, sincronização automática sem CSV manual, estados POTENTIAL -> PAID)
5. Testes de recuperação e infraestrutura 24/7 (Fila persistente, idempotência, recuperação pós-queda e detecção Local vs VPS)
6. Teste de fluxo completo E2E de 10 estágios:
   DESCOBERTA -> SELEÇÃO -> LINK -> CONTEÚDO -> PUBLICAÇÃO -> CLIQUES -> CONVERSÃO -> COMISSÃO -> CONCILIAÇÃO -> RELATÓRIO
"""

import hashlib
import hmac
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.automation.autonomous_orchestrator import UnionAutonomousOrchestrator
from app.config import settings
from app.content_engine.autonomous_pipeline import AutonomousContentPipeline
from app.finance.auto_sales_tracker import AutoSalesTracker
from app.finance.union_finance_ai import UnionFinanceAI
from app.integrations.union_connect import UnionConnect
from app.intelligence.autonomous_discovery import AutonomousProductDiscovery
from app.intelligence.opportunity import score_and_update_product
from app.intelligence.union_growth_ai import UnionGrowthAI
from app.marketing.link_manager import UnionLinkManager
from app.models.autonomous import (
    IntegrationStatusIndicator,
    PersistentOrchestratorQueue,
    PipelineStage,
)
from app.models.click import ClickLog
from app.models.marketplace import Category, Marketplace
from app.models.product import Product
from scripts.keep_alive_runner import (
    inspect_execution_infrastructure,
    run_supervisor_health_and_recovery_tick,
)


# ==============================================================================
# 1. TESTES UNITÁRIOS (UNION CONNECT, OAUTH, ESCOPOS E TRAVAS DE SEGURANÇA)
# ==============================================================================

def test_unit_union_connect_lifecycle_and_encrypted_tokens(
    client: TestClient, db_session: Session
) -> None:
    """Valida OAuth URL, armazenamento criptografado, renovação, reconexão e desativação segura."""
    connect = UnionConnect(db_session)
    all_connectors = connect.list_all_connectors()
    slugs = {c["connector_slug"] for c in all_connectors}
    assert {
        "mercadolivre",
        "amazon",
        "shopee",
        "youtube",
        "instagram",
        "pinterest",
        "gsc",
        "ga4",
        "union_ofertas",
    }.issubset(slugs)

    # Portal próprio UNION OFERTAS deve estar sempre ACTIVE e REALMENTE FUNCIONAL
    union_portal = next(c for c in all_connectors if c["connector_slug"] == "union_ofertas")
    assert union_portal["status_indicator"] == IntegrationStatusIndicator.ACTIVE
    assert union_portal["commercial_readiness_state"] == "REALMENTE FUNCIONAL"

    # Matriz de auditoria comercial explícita (REALMENTE FUNCIONAL | PENDENTE DE CREDENCIAIS | NÃO SUPORTADA)
    matrix = connect.get_commercial_integration_audit_matrix()
    assert matrix["union_ofertas_portal"]["state"] == "REALMENTE FUNCIONAL"
    assert matrix["amazon_rest_commission_reports_api"]["state"] == "NÃO SUPORTADA"
    assert matrix["mercadolivre_catalog_and_orders_api"]["state"] in (
        "PENDENTE DE CREDENCIAIS",
        "REALMENTE FUNCIONAL",
    )

    # Gerar URL OAuth para YouTube
    oauth_info = connect.get_oauth_authorization_url("youtube")
    assert oauth_info["is_one_time_owner_authorization"] is True
    assert "accounts.google.com" in oauth_info["authorization_url"]

    # Armazenar token criptografado com escopos obrigatórios
    yt_status = connect.get_connector_status("youtube")
    required_scopes = yt_status["required_scopes"]
    stored = connect.store_authorized_token(
        connector_slug="youtube",
        access_token="SANDBOX_ACCESS_YOUTUBE_001",
        refresh_token="SANDBOX_REFRESH_YOUTUBE_001",
        granted_scopes=required_scopes,
        expires_in_seconds=120,
    )
    assert stored["status_indicator"] == IntegrationStatusIndicator.ACTIVE
    assert stored["authorization_block_status"] == "OPERACIONAL"

    # Verificar descriptografia em memória e renovação automática via refresh_token
    assert connect.get_decrypted_access_token("youtube") == "SANDBOX_ACCESS_YOUTUBE_001"
    renewed = connect.renew_token_if_needed("youtube", force=True)
    assert renewed["status_indicator"] == IntegrationStatusIndicator.ACTIVE

    # Registrar erro e testar reconexão automática
    err_state = connect.record_connector_error("youtube", "Timeout temporário na API")
    assert err_state["status_indicator"] == IntegrationStatusIndicator.ERROR
    reconnected = connect.reconnect_connector("youtube")
    assert reconnected["status_indicator"] == IntegrationStatusIndicator.ACTIVE

    # Desativação segura
    disabled = connect.disable_connector_safely("youtube", reason="Teste de desativação segura")
    assert disabled["status_indicator"] == IntegrationStatusIndicator.DISABLED
    assert connect.get_decrypted_access_token("youtube") is None


def test_unit_autonomy_flags_and_growth_ai_safety_constraints(
    client: TestClient, db_session: Session
) -> None:
    """Garante que AUTONOMY_MODE=FULL e que o UNION GROWTH AI jamais gasta dinheiro automaticamente."""
    resp = client.get("/api/connect/autonomy-flags")
    assert resp.status_code == 200
    data = resp.json()
    assert data["autonomy_mode"] == "FULL"
    flags = data["flags"]
    assert flags["AUTO_PRODUCT_DISCOVERY"]["configured"] is True
    assert flags["AUTO_AFFILIATE_LINKS"]["configured"] is True
    assert flags["AUTO_CONTENT_GENERATION"]["configured"] is True
    assert flags["AUTO_PUBLISHING"]["configured"] is True
    assert flags["AUTO_COMMISSION_SYNC"]["configured"] is True

    growth = UnionGrowthAI(db_session)
    assert growth.SAFETY_CONSTRAINTS["auto_increase_financial_investment"] is False
    assert growth.SAFETY_CONSTRAINTS["auto_buy_traffic"] is False
    assert growth.SAFETY_CONSTRAINTS["auto_hire_tools"] is False
    assert growth.SAFETY_CONSTRAINTS["auto_make_payments"] is False


# ==============================================================================
# 2. TESTES SIMULADOS / SANDBOX (DESCOBERTA INCREMENTAL E SUSPENSÃO AUTOMÁTICA)
# ==============================================================================

def test_sandbox_autonomous_discovery_and_invalid_product_suspension(
    db_session: Session,
) -> None:
    """Testa descoberta incremental sem formulário manual e suspensão automática de produto inválido."""
    discovery = AutonomousProductDiscovery(db_session)
    report = discovery.ingest_authorized_items_incrementally(
        items=[
            {
                "external_id": "MLB-AUTO-DISC-101",
                "title": "Fone de Ouvido Bluetooth ANC Pro Sem Fio",
                "description": "Fone com cancelamento ativo de ruído e bateria de 30 horas.",
                "price": 249.90,
                "original_price": 349.90,
                "in_stock": True,
                "rating": 4.8,
                "review_count": 320,
                "announced_commission_rate": 10.0,
                "product_url": "https://www.mercadolivre.com.br/p/MLB101010",
                "affiliate_url": "https://www.mercadolivre.com.br/p/MLB101010?matt_tool=union123",
            },
            {
                "external_id": "MLB-INVALID-ZERO",
                "title": "Item Inválido Preço Zero",
                "price": 0.0,
                "product_url": "https://www.mercadolivre.com.br/p/MLB000",
            },
        ],
        marketplace_slug="mercadolivre",
    )
    assert report["created_count"] == 1
    assert report["rejected_invalid_count"] == 1
    assert report["links_processed"] == 1

    # Insere um produto sem estoque para validar suspensão automática
    mkt = db_session.query(Marketplace).first()
    cat = db_session.query(Category).first()
    invalid_prod = Product(
        marketplace_id=mkt.id,
        category_id=cat.id,
        external_id="OUT-OF-STOCK-999",
        title="Produto Esgotado Teste Automático",
        product_url="https://www.mercadolivre.com.br/p/MLB999999",
        price=199.0,
        announced_commission_rate=8.0,
        estimated_commission_value=15.92,
        in_stock=False,
        is_active=True,
    )
    db_session.add(invalid_prod)
    db_session.commit()
    db_session.refresh(invalid_prod)

    susp_report = discovery.suspend_invalid_or_uninteresting_products()
    assert invalid_prod.id in susp_report["suspended_out_of_stock_ids"]
    db_session.refresh(invalid_prod)
    assert invalid_prod.is_active is False


# ==============================================================================
# 3. TESTES DE PUBLICAÇÃO E PRONTIDÃO DE API REAL (12 PASSOS + BLOQUEIO HONESTO)
# ==============================================================================

def test_publishing_and_api_readiness_honest_authorization_blocking(
    db_session: Session,
) -> None:
    """Garante publicação real imediata no UNION OFERTAS e bloqueio explícito em API externa sem token."""
    discovery = AutonomousProductDiscovery(db_session)
    discovery.ingest_authorized_items_incrementally(
        items=[
            {
                "external_id": "MLB-PUB-TEST-201",
                "title": "Notebook Gamer RTX 4060 16GB RAM SSD 1TB",
                "description": "Notebook gamer de alta performance com tela 144Hz.",
                "price": 5499.00,
                "original_price": 6299.00,
                "in_stock": True,
                "rating": 4.9,
                "review_count": 210,
                "announced_commission_rate": 7.0,
                "product_url": "https://www.mercadolivre.com.br/p/MLB201201",
                "affiliate_url": "https://www.mercadolivre.com.br/p/MLB201201?matt_tool=union123",
            }
        ],
        marketplace_slug="mercadolivre",
    )
    product = db_session.query(Product).filter(Product.is_active.is_(True)).first()
    assert product is not None

    pipeline_svc = AutonomousContentPipeline(db_session)
    res = pipeline_svc.execute_for_product(
        product=product,
        target_channels=["UNION_OFERTAS", "INSTAGRAM_REELS", "PINTEREST"],
    )
    assert res["current_state"] == PipelineStage.MONITORING
    stage_names = [s["stage"] for s in res["state_history"]]
    assert PipelineStage.DISCOVERY in stage_names
    assert PipelineStage.QUALITY_CHECK in stage_names
    assert PipelineStage.SEO in stage_names
    assert PipelineStage.PUBLISHED in stage_names
    assert PipelineStage.MONITORING in stage_names

    by_channel = {r["channel"]: r for r in res["publications"]}

    # Canal próprio deve estar PUBLISHED com URL acessível
    assert by_channel["UNION_OFERTAS"]["published"] is True
    assert by_channel["UNION_OFERTAS"]["status"] == "PUBLISHED"
    assert "/ofertas/artigos/" in by_channel["UNION_OFERTAS"]["published_url"]

    # Canais externos sem OAuth ativo devem reportar BLOQUEADA POR AUTORIZAÇÃO (nunca fingir postagem)
    for ext_ch in ("INSTAGRAM_REELS", "PINTEREST"):
        assert by_channel[ext_ch]["published"] is False
        assert by_channel[ext_ch]["status"] == "BLOQUEADA POR AUTORIZAÇÃO"
        assert by_channel[ext_ch]["connector_status_indicator"] == IntegrationStatusIndicator.AUTHORIZATION_REQUIRED


# ==============================================================================
# 4. TESTES FINANCEIROS AUTOMÁTICOS (WEBHOOK ASSINADO E CONCILIAÇÃO SEM CSV)
# ==============================================================================

def test_financial_auto_sync_signed_webhook_without_manual_csv(
    client: TestClient, db_session: Session
) -> None:
    """Valida ingestão automática de venda e comissão paga via Webhook assinado HMAC-SHA256."""
    discovery = AutonomousProductDiscovery(db_session)
    discovery.ingest_authorized_items_incrementally(
        items=[
            {
                "external_id": "MLB-WH-TEST-301",
                "title": "Smartwatch GPS AMOLED Resistente à Água",
                "description": "Smartwatch com monitoramento cardíaco e GPS integrado.",
                "price": 450.00,
                "original_price": 599.00,
                "in_stock": True,
                "rating": 4.7,
                "review_count": 180,
                "announced_commission_rate": 8.0,
                "product_url": "https://www.mercadolivre.com.br/p/MLB301301",
                "affiliate_url": "https://www.mercadolivre.com.br/p/MLB301301?matt_tool=union123",
            }
        ],
        marketplace_slug="mercadolivre",
    )
    product = db_session.query(Product).filter(Product.is_active.is_(True)).first()
    assert product is not None

    payload = {
        "external_reference": "AUTO-WH-ORDER-2026-001",
        "product_id": product.id,
        "order_value": 450.00,
        "commission_amount": 36.00,
        "status": "PAID",
    }
    raw_str = f"mercadolivre:{payload['external_reference']}:{payload['status']}:{payload['commission_amount']}"
    sig = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        raw_str.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    resp = client.post(
        "/api/webhooks/conversions/mercadolivre",
        json=payload,
        headers={"X-Hub-Signature-256": sig},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] in ("CREATED", "UPDATED_STATE")
    assert data["status"] == "PAID"
    assert data["entered_cash_received"] is True

    # Verifica se entrou no caixa recebido da Central Financeira
    fin = UnionFinanceAI(db_session).get_full_indicators()
    assert fin["paid_commissions_brl"] >= 36.00
    assert fin["cash_received_brl"] >= 36.00


# ==============================================================================
# 5. TESTES DE RECUPERAÇÃO E INFRAESTRUTURA 24/7
# ==============================================================================

def test_recovery_and_infrastructure_persistent_queue_and_supervisor(
    db_session: Session,
) -> None:
    """Testa fila persistente, idempotência, recuperação de job travado e diagnóstico Local vs VPS."""
    orchestrator = UnionAutonomousOrchestrator(db_session)

    # Cria um job simulando travamento em RUNNING antes de queda de energia
    stuck_job = PersistentOrchestratorQueue(
        cycle_type="EVERY_6_HOURS",
        task_name="simulated_interrupted_job",
        idempotency_key="stuck:job:001",
        status="RUNNING",
        attempt_count=1,
        max_attempts=3,
        locked_by="crashed-worker-pid-111",
    )
    db_session.add(stuck_job)
    db_session.commit()

    recovery = orchestrator.recover_persistent_queue()
    assert recovery["status"] == "OK"
    assert recovery["recovered_jobs"] >= 1
    db_session.refresh(stuck_job)
    assert stuck_job.status == "RECOVERED"
    assert stuck_job.locked_by is None

    # Testa retry automático com recuperação de falha transitória (falha na tentativa 1, sucesso na tentativa 2)
    state_counter = {"calls": 0}

    def _flaky_task():
        state_counter["calls"] += 1
        if state_counter["calls"] == 1:
            raise RuntimeError("Falha transitória simulada na primeira tentativa")
        return {"recovered_on_attempt": state_counter["calls"]}

    retry_res = orchestrator.enqueue_or_execute_job(
        cycle_type="every_6_hours",
        task_name="flaky_self_healing_task",
        idempotency_key="retry:test:001",
        fn=_flaky_task,
        max_attempts=3,
    )
    assert retry_res["status"] == "COMPLETED"
    assert retry_res["attempts"] == 2
    assert retry_res["result"]["recovered_on_attempt"] == 2

    # Testa idempotência (segunda chamada com mesma chave não reexecuta)
    dup_res = orchestrator.enqueue_or_execute_job(
        cycle_type="every_6_hours",
        task_name="flaky_self_healing_task",
        idempotency_key="retry:test:001",
        fn=_flaky_task,
        max_attempts=3,
    )
    assert dup_res["status"] == "SKIPPED_DUPLICATE"
    assert state_counter["calls"] == 2

    # Verifica diagnóstico transparente de infraestrutura
    infra = inspect_execution_infrastructure()
    assert infra["infrastructure_option"] in (
        "OPCAO_1_COMPUTADOR_LOCAL",
        "OPCAO_2_VPS_OU_SERVIDOR_ATIVO",
    )
    assert "transparency_notice" in infra
    assert infra["database_healthy"] is True

    tick = run_supervisor_health_and_recovery_tick()
    assert tick["status"] == "HEALTHY"
    assert tick["backup"]["is_valid"] is True


# ==============================================================================
# 6. TESTE DE FLUXO COMPLETO DE PONTA A PONTA (10 ESTÁGIOS SEM AÇÃO HUMANA)
# ==============================================================================

def test_end_to_end_10_stages_autonomous_flow(
    client: TestClient, db_session: Session
) -> None:
    """Executa o fluxo autônomo completo de 10 estágios:
    1. DESCOBERTA -> 2. SELEÇÃO -> 3. LINK -> 4. CONTEÚDO -> 5. PUBLICAÇÃO ->
    6. CLIQUES -> 7. CONVERSÃO -> 8. COMISSÃO -> 9. CONCILIAÇÃO -> 10. RELATÓRIO.
    """
    # 1. DESCOBERTA (Incremental via AutonomousProductDiscovery)
    discovery = AutonomousProductDiscovery(db_session)
    disc_res = discovery.ingest_authorized_items_incrementally(
        items=[
            {
                "external_id": "MLB-MONITOR-144HZ-E2E",
                "title": "Monitor Gamer IPS 27 Polegadas 144Hz 1ms Full HD",
                "description": "Monitor gamer IPS com FreeSync, HDMI e DisplayPort.",
                "price": 1099.00,
                "original_price": 1399.00,
                "in_stock": True,
                "rating": 4.9,
                "review_count": 510,
                "announced_commission_rate": 8.0,
                "product_url": "https://www.mercadolivre.com.br/p/MLB144000",
                "affiliate_url": "https://www.mercadolivre.com.br/p/MLB144000?matt_tool=union_e2e",
            }
        ],
        marketplace_slug="mercadolivre",
    )
    assert disc_res["created_count"] >= 1 or disc_res["updated_count"] >= 1

    # 2. SELEÇÃO (Recálculo de scores e seleção da melhor oportunidade)
    best_product = (
        db_session.query(Product)
        .filter(Product.external_id == "MLB-MONITOR-144HZ-E2E")
        .first()
    )
    assert best_product is not None
    score_and_update_product(db_session, best_product)
    db_session.commit()
    assert (best_product.opportunity_score or 0.0) > 0

    # 3. LINK (Geração automática com atribuição oficial verificada)
    link_info = UnionLinkManager.auto_generate_or_update_link_for_product(
        db_session, best_product
    )
    assert link_info["short_code"] is not None
    assert link_info["internal_tracking_url"].startswith("/r/")
    assert link_info["has_official_affiliate_attribution"] is True

    # 4. CONTEÚDO & 5. PUBLICAÇÃO (Pipeline completo de 9 estados + publicação no UNION OFERTAS)
    pipeline_svc = AutonomousContentPipeline(db_session)
    pipe_res = pipeline_svc.execute_for_product(
        product=best_product,
        target_channels=["UNION_OFERTAS"],
    )
    assert pipe_res["current_state"] == PipelineStage.MONITORING
    assert pipe_res["publications"][0]["published"] is True

    # Testar atualização automática de conteúdo quando o preço muda
    best_product.price = 1049.00
    db_session.commit()
    refresh_res = pipeline_svc.refresh_outdated_contents()
    assert refresh_res["refreshed_count"] >= 1

    # 6. CLIQUES (Simula clique real de visitante humano no link curto /r/{code})
    redirect_resp = client.get(
        link_info["internal_tracking_url"],
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        follow_redirects=False,
    )
    assert redirect_resp.status_code in (302, 307)
    clicks_count = (
        db_session.query(ClickLog)
        .filter(ClickLog.product_id == best_product.id, ClickLog.is_valid_human.is_(True))
        .count()
    )
    assert clicks_count >= 1

    # 7. CONVERSÃO & 8. COMISSÃO (Via AutoSalesTracker Webhook oficial s/ CSV manual)
    tracker = AutoSalesTracker(db_session)
    wh_res = tracker.process_official_webhook(
        marketplace_slug="mercadolivre",
        payload={
            "external_reference": "E2E-ORDER-10-STAGES-001",
            "product_id": best_product.id,
            "order_value": float(best_product.price),
            "commission_amount": 83.92,
            "status": "PAID",
        },
    )
    assert wh_res["status"] == "PAID"
    assert wh_res["entered_cash_received"] is True

    # 9. CONCILIAÇÃO FINANCEIRA
    finance_ai = UnionFinanceAI(db_session)
    reconcile_res = finance_ai.reconcile_commissions()
    assert reconcile_res["status"] == "RECONCILED"

    # 10. RELATÓRIO E OTIMIZAÇÃO COMERCIAL (UNION GROWTH AI + CICLO MENSAL)
    growth_res = UnionGrowthAI(db_session).update_priorities_automatically()
    assert growth_res["status"] == "OPTIMIZED"
    assert growth_res["performance_snapshot"]["paid_commissions_total_brl"] >= 83.92

    orchestrator = UnionAutonomousOrchestrator(db_session)
    monthly_cycle = orchestrator.execute_cycle("monthly", bucket_suffix="e2e-test-bucket")
    assert monthly_cycle["cycle_type"] == "monthly"
    assert monthly_cycle["jobs"]["financial_reconciliation"]["status"] == "COMPLETED"
    assert monthly_cycle["jobs"]["financial_report_and_profitability"]["status"] == "COMPLETED"
    assert monthly_cycle["jobs"]["wealth_goal_review"]["status"] == "COMPLETED"
