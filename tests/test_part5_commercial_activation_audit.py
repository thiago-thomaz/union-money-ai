"""Suíte de Testes da Fase 5 — Auditoria Comercial Real vs Testes de Integração, Painel de 4 Estados e Credenciais Runtime."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.config import settings
from app.models.audit import AuditLog


def test_phase5_platform_audit_panel_four_states_and_runtime_credentials(
    client: TestClient, db_session: Session
):
    """Verifica o painel de 4 estados da Fase 5 e a persistência criptografada de credenciais sem expor segredos."""
    old_amz_tag = settings.AMAZON_PARTNER_TAG
    old_shp_id = settings.SHOPEE_AFFILIATE_ID
    try:
        settings.AMAZON_PARTNER_TAG = ""
        settings.SHOPEE_AFFILIATE_ID = ""

        # 1. Consulta auditoria Fase 5 inicial
        audit_res = client.get("/api/integrations/phase5-audit")
        assert audit_res.status_code == 200
        audit_data = audit_res.json()
        assert set(audit_data["allowed_states"]) == {
            "REALMENTE CONECTADO",
            "AGUARDANDO AUTORIZAÇÃO",
            "CREDENCIAIS AUSENTES",
            "API NÃO DISPONÍVEL",
        }

        mp_by_slug = {m["slug"]: m for m in audit_data["marketplaces"]}
        assert mp_by_slug["amazon"]["capabilities"]["sales_and_commission_query"]["state"] == "API NÃO DISPONÍVEL"
        assert mp_by_slug["amazon"]["overall_state"] == "CREDENCIAIS AUSENTES"

        ch_by_slug = {c["slug"]: c for c in audit_data["channels_and_analytics"]}
        assert ch_by_slug["union_ofertas"]["overall_state"] == "REALMENTE CONECTADO"

        # 2. Salva AMAZON_PARTNER_TAG e SHOPEE_AFFILIATE_ID via endpoint do painel Cloud
        cfg_res = client.post(
            "/api/connect/credentials/configure",
            json={
                "credentials": {
                    "AMAZON_PARTNER_TAG": "union-teste-20",
                    "SHOPEE_AFFILIATE_ID": "99887766",
                },
                "trigger_immediate_cycle": True,
            },
        )
        assert cfg_res.status_code == 200
        cfg_data = cfg_res.json()
        assert "AMAZON_PARTNER_TAG" in cfg_data["updated_keys"]
        assert "SHOPEE_AFFILIATE_ID" in cfg_data["updated_keys"]

        # 3. Verifica que a geração automática de links para Amazon e Shopee passou para REALMENTE CONECTADO
        # e o estado geral (sem chaves PA-API / Open API) passou para AGUARDANDO AUTORIZAÇÃO
        mp_after = {m["slug"]: m for m in cfg_data["phase5_audit"]["marketplaces"]}
        assert mp_after["amazon"]["capabilities"]["auto_link_generation"]["state"] == "REALMENTE CONECTADO"
        assert mp_after["amazon"]["overall_state"] == "AGUARDANDO AUTORIZAÇÃO"
        assert mp_after["shopee"]["capabilities"]["auto_link_generation"]["state"] == "REALMENTE CONECTADO"
        assert mp_after["shopee"]["overall_state"] == "AGUARDANDO AUTORIZAÇÃO"

        # 4. Verifica que nenhum segredo em texto puro foi gravado nos logs de auditoria
        logs = db_session.query(AuditLog).all()
        for log in logs:
            assert "union-teste-20" not in str(log.details)

        # 5. Verifica renderização da página HTML /integrations com os 4 estados
        html_res = client.get("/integrations")
        assert html_res.status_code == 200
        assert "REALMENTE CONECTADO" in html_res.text
        assert "AGUARDANDO AUTORIZAÇÃO" in html_res.text
        assert "CREDENCIAIS AUSENTES" in html_res.text
        assert "API NÃO DISPONÍVEL" in html_res.text
    finally:
        settings.AMAZON_PARTNER_TAG = old_amz_tag
        settings.SHOPEE_AFFILIATE_ID = old_shp_id


def test_phase5_separated_integration_flow_vs_real_commercial_state(client: TestClient):
    """Comprova que o teste de integração de 8 estágios roda isolado sem fabricar vendas no estado comercial real."""
    # 1. Consulta estado comercial real antes do teste de integração
    before_audit = client.get("/api/cloud/commercial-vs-integration-audit")
    assert before_audit.status_code == 200
    before_state = before_audit.json()["real_commercial_production_state"]

    # 2. Executa verificação de integração de 8 estágios em banco temporário isolado
    e2e_res = client.post("/api/cloud/verify-integration-flow")
    assert e2e_res.status_code == 200
    e2e = e2e_res.json()
    assert e2e["isolated_from_production_db"] is True
    assert e2e["all_8_stages_passed"] is True
    stages = e2e["stages"]
    assert stages["1_product_discovered"]["product_id"] >= 1
    assert stages["2_opportunity_approved"]["opportunity_score"] > 0
    assert stages["3_valid_affiliate_link"]["validity_status"] == "VALID"
    assert stages["4_content_produced"]["quality_score"] >= 75.0
    assert stages["5_content_published"]["state"] == "MONITORING"
    assert stages["6_click_registered"]["is_valid_human"] is True
    assert stages["6_click_registered"]["counted_as_sale"] is False
    assert stages["7_conversion_identified"]["pending_entered_cash"] is False
    assert stages["8_commission_synced"]["final_status"] == "PAID"
    assert stages["8_commission_synced"]["paid_entered_cash"] is True
    assert stages["8_commission_synced"]["cash_received_brl"] == 423.92

    # 3. Consulta estado comercial real após o teste -> zero conversões ou produtos falsos adicionados em produção
    after_audit = client.get("/api/cloud/commercial-vs-integration-audit").json()
    after_state = after_audit["real_commercial_production_state"]
    assert after_audit["fabricated_conversions_count"] == 0
    assert after_state["real_active_products"] == before_state["real_active_products"]
    assert after_state["confirmed_real_conversions"] == before_state["confirmed_real_conversions"]
    assert after_state["cash_received_paid_commissions_brl"] == before_state["cash_received_paid_commissions_brl"]

