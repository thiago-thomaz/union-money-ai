"""Suíte de Testes Automatizados da Parte 3 — Financeiro, Segurança, Conformidade, LGPD, Autonomia, Backup/Restore e Escala (Seção 11, Grupos A–I)."""

from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.config import settings
from app.core.compliance import UnionCompliance
from app.core.security import (
    EndpointRateLimiter,
    create_session_token,
    detect_sql_injection_pattern,
    generate_csrf_token,
    hash_password,
    mask_secret,
    sanitize_input,
    scan_codebase_for_hardcoded_secrets,
    verify_csrf_token,
    verify_password,
    verify_session_token,
)
from app.finance.growth_manager import UnionGrowthManager
from scripts.backup_db import create_sqlite_backup, verify_backup_integrity
from scripts.init_database import initialize_environment
from scripts.restore_db import restore_sqlite_backup


def test_group_a_and_e_compliance_models_and_pending_external_integrations(db_session: Session):
    """Testa tabelas da Parte 3 e garante que integrações externas sem credenciais fiquem como PENDENTE (nunca APROVADA)."""
    comp = UnionCompliance(db_session)
    checklist = comp.list_checklist()
    assert len(checklist) >= 7

    by_slug = {c["target_slug"]: c for c in checklist}
    # Site próprio deve estar APROVADA
    assert by_slug["site"]["integration_status"] == "APROVADA"
    assert by_slug["site"]["authorized_to_operate"] is True

    # Canais e marketplaces externos sem credenciais reais configuradas devem aparecer como PENDENTE
    for ext_slug in ("mercadolivre", "amazon", "shopee", "youtube", "instagram", "pinterest"):
        assert by_slug[ext_slug]["integration_status"] == "PENDENTE"
        assert by_slug[ext_slug]["authorized_to_operate"] is False

    # Tentar aprovar canal externo sem credenciais ainda deve mantê-lo PENDENTE
    updated = comp.verify_or_update_policy("youtube", terms_accepted=True, mark_verified_now=True)
    assert updated["integration_status"] == "PENDENTE"


def test_group_f_union_finance_ai_five_stages_and_csv_import_and_reconciliation(client: TestClient):
    """Testa UNION FINANCE AI: separação de 5 estágios, caixa recebido estrito (somente PAID), importação CSV e conciliação."""
    # Cadastra um produto real de teste para vincular às comissões do CSV
    prod_res = client.post(
        "/api/products",
        json={
            "marketplace_id": 1,
            "category_id": 1,
            "title": "Monitor Gamer 27 IPS 144Hz Full HD",
            "price": 1000.00,
            "original_price": 1250.00,
            "announced_commission_rate": 8.0,
            "rating": 4.8,
            "review_count": 320,
            "sales_rank_indicator": 85.0,
            "competition_level": "LOW",
            "in_stock": True,
            "product_url": "https://www.mercadolivre.com.br/p/MLB123456",
            "affiliate_url": "https://www.mercadolivre.com.br/sec/MLB123456",
            "data_source": "CSV_FINANCE_TEST",
        },
    )
    assert prod_res.status_code == 201
    prod_id = prod_res.json()["id"]

    # 1. Importa CSV oficial com 4 pedidos em diferentes estágios (PENDING, APPROVED, CANCELLED, PAID)
    csv_payload = "\n".join(
        [
            "external_reference,date,order_value,commission_amount,status,product_id",
            f"ORD-CSV-101,2026-11-01,1000.00,80.00,PENDING,{prod_id}",
            f"ORD-CSV-102,2026-11-02,1000.00,80.00,APPROVED,{prod_id}",
            f"ORD-CSV-103,2026-11-03,1000.00,80.00,CANCELLED,{prod_id}",
            f"ORD-CSV-104,2026-11-04,1000.00,95.00,PAID,{prod_id}",
            # Linha duplicada idêntica no mesmo lote deve ser ignorada
            f"ORD-CSV-104,2026-11-04,1000.00,95.00,PAID,{prod_id}",
        ]
    )
    imp_res = client.post(
        "/api/finance/import-csv",
        json={"marketplace_slug": "mercadolivre", "csv_content": csv_payload},
    )
    assert imp_res.status_code == 200
    imp_data = imp_res.json()
    assert imp_data["imported_count"] == 4
    assert imp_data["duplicate_skipped_count"] == 1
    assert imp_data["is_valid_import"] is True

    # 2. Verifica os 5 estágios e garante que SOMENTE comissões PAID entram no caixa recebido (cash_received_brl)
    ind_res = client.get("/api/finance/indicators")
    assert ind_res.status_code == 200
    ind = ind_res.json()
    stages = ind["five_stage_separation"]

    assert stages["stage_1_potential_commission_brl"] >= 80.0  # Comissão potencial do produto em catálogo
    assert stages["stage_2_attributed_commission_brl"] == 80.0  # ORD-CSV-101 (PENDING)
    assert stages["stage_3_approved_commission_brl"] == 80.0  # ORD-CSV-102 (APPROVED)
    assert stages["stage_4_cancelled_commission_brl"] == 80.0  # ORD-CSV-103 (CANCELLED)
    assert stages["stage_5_paid_commission_brl"] == 95.0  # Somente ORD-CSV-104 (PAID)
    assert ind["cash_received_brl"] == 95.0

    # 3. Reimporta CSV conciliando ORD-CSV-102 de APPROVED para PAID
    csv_reconcile = "\n".join(
        [
            "external_reference,date,order_value,commission_amount,status,product_id",
            f"ORD-CSV-102,2026-11-05,1000.00,80.00,PAID,{prod_id}",
        ]
    )
    imp_res2 = client.post(
        "/api/finance/import-csv",
        json={"marketplace_slug": "mercadolivre", "csv_content": csv_reconcile},
    )
    assert imp_res2.status_code == 200
    assert imp_res2.json()["updated_reconciled_count"] == 1

    ind_after = client.get("/api/finance/indicators").json()
    assert ind_after["paid_commissions_brl"] == 175.0  # 95 + 80
    assert ind_after["cash_received_brl"] == 175.0

    # 4. Executa conciliação financeira explícita
    rec_res = client.post("/api/finance/reconcile")
    assert rec_res.status_code == 200
    assert rec_res.json()["status"] == "RECONCILED"


def test_group_f_wealth_simulator_and_growth_manager(client: TestClient, db_session: Session):
    """Testa UNION WEALTH SIMULATOR (Metas A e B em 12, 24, 36 e 60 meses) e UNION GROWTH MANAGER."""
    for scen in ("CONSERVADOR", "MODERADO", "AGRESSIVO"):
        sim_res = client.get(f"/api/finance/wealth-simulator?scenario={scen}")
        assert sim_res.status_code == 200
        sim = sim_res.json()
        assert sim["is_realized_result"] is False
        assert sim["goals"]["goal_a_patrimony_target_brl"] == 1_000_000.0
        assert sim["goals"]["goal_b_revenue_target_brl"] == 1_000_000.0
        assert set(sim["projections"].keys()) == {"12_months", "24_months", "36_months", "60_months"}

    # Testa simulação customizada verificando a fórmula matemática exata do Mês 1
    custom_res = client.post(
        "/api/finance/wealth-simulator",
        json={
            "scenario": "MODERADO",
            "custom_vars": {
                "monthly_visitors": 10000.0,
                "ctr_pct": 5.0,  # 500 cliques
                "conversion_rate_pct": 2.0,  # 10 vendas
                "average_ticket_brl": 200.0,
                "average_commission_pct": 10.0,  # R$ 20 por venda -> R$ 200 brutos
                "cancellation_rate_pct": 0.0,
                "monthly_expenses_brl": 50.0,
                "tax_rate_pct": 0.0,
                "monthly_growth_rate_pct": 0.0,
            },
        },
    )
    assert custom_res.status_code == 200
    m1 = custom_res.json()["base_month_1_formula_breakdown"]
    assert m1["clicks"] == 500.0
    assert m1["estimated_sales"] == 10.0
    assert m1["valid_estimated_commission_brl"] == 200.0
    assert m1["estimated_operational_result_brl"] == 150.0

    # Testa UNION GROWTH MANAGER
    gm_res = client.get("/api/finance/growth-manager")
    assert gm_res.status_code == 200
    gm = gm_res.json()
    assert gm["auto_spend_allowed"] is False
    assert gm["human_approval_required"] is True
    assert gm["recommendation_only"] is True
    assert len(gm["allocations"]) == 7

    # Verifica que caixa zero/negativo jamais gera alocação positiva
    zero_rec = UnionGrowthManager(db_session).recommend_reinvestment(override_received_cash_brl=-100.0)
    assert zero_rec["allocatable_cash_brl"] == 0.0
    for item in zero_rec["allocations"].values():
        assert item["recommended_brl"] == 0.0


def test_group_g_security_csrf_xss_ratelimit_secrets_and_lgpd(client: TestClient):
    """Testa controles de segurança (Bcrypt, Sessão, CSRF, XSS, SQLi, Rate Limit, Segredos) e LGPD."""
    # 1. Hash e verificação de senha
    pw_hash = hash_password("SenhaForte#2026")
    assert verify_password("SenhaForte#2026", pw_hash) is True
    assert verify_password("Errada", pw_hash) is False

    # 2. Token de sessão assinado
    tok = create_session_token("admin_union", is_admin=True, ttl_seconds=3600)
    parsed = verify_session_token(tok)
    assert parsed is not None
    assert parsed["username"] == "admin_union"
    assert parsed["is_admin"] is True
    assert verify_session_token(tok + "tampered") is None

    # 3. Proteção CSRF
    csrf = generate_csrf_token("sess-123")
    assert verify_csrf_token(csrf, "sess-123") is True
    assert verify_csrf_token(csrf, "other-sess") is False

    # 4. Sanitização XSS e detecção SQL Injection
    dirty = '<script>alert("xss")</script><b onclick="evil()">Oferta</b>'
    clean = sanitize_input(dirty)
    assert "<script>" not in clean
    assert "onclick" not in clean
    assert detect_sql_injection_pattern("1 OR 1=1 --") is True
    assert detect_sql_injection_pattern("Fone Bluetooth JBL") is False

    # 5. Mascaramento e varredura de segredos hardcoded
    assert mask_secret("SUPER_SECRET_TOKEN_99") == "SUP***99"
    scan = scan_codebase_for_hardcoded_secrets(settings.base_dir / "app")
    assert scan["hardcoded_secrets_found"] == 0
    assert scan["status"] == "CLEAN"

    # 6. Rate Limiter
    limiter = EndpointRateLimiter(max_requests=2, window_seconds=60)
    assert limiter.check_allowed("client-1")["allowed"] is True
    assert limiter.check_allowed("client-1")["allowed"] is True
    assert limiter.check_allowed("client-1")["allowed"] is False

    # 7. LGPD: Consentimento, Exclusão de Dados e Incidentes de Segurança
    c_res = client.post(
        "/api/lgpd/consent",
        json={
            "subject_identifier": "visitante.lgpd@exemplo.com.br",
            "purpose": "NEWSLETTER_OFERTAS",
            "consent_granted": True,
        },
    )
    assert c_res.status_code == 201

    del_res = client.delete("/api/lgpd/subject/visitante.lgpd@exemplo.com.br")
    assert del_res.status_code == 200
    assert del_res.json()["consents_deleted"] >= 1

    inc_res = client.post(
        "/api/lgpd/incidents",
        json={
            "severity": "LOW",
            "incident_type": "RATE_LIMIT_TRIGGERED",
            "description": "Bloqueio preventivo de excesso de requisições em endpoint sensível.",
            "mitigation_applied": "IP temporariamente limitado pelo EndpointRateLimiter.",
        },
    )
    assert inc_res.status_code == 201
    assert inc_res.json()["resolved"] is True


def test_group_h_autonomy_levels_emergency_stop_routines_and_backup_restore(
    client: TestClient, db_session: Session, tmp_path: Path
):
    """Testa Níveis de Autonomia 1/2/3, Travas Humanas, STOP ALL AUTOMATIONS, Rotinas e Backup/Restore."""
    # 1. Testa Nível 1 (Assistido): exige aprovação até para o site próprio
    client.put("/api/autonomy/config", json={"level": "LEVEL_1_ASSISTED"})
    ev1 = client.post(
        "/api/autonomy/evaluate",
        json={"action_type": "PUBLISH_CONTENT", "target_channel": "SITE", "content_quality_score": 90.0},
    ).json()
    assert ev1["autonomous_execution_allowed"] is False
    assert ev1["requires_human_approval"] is True

    # 2. Testa Nível 2 (Semiautomático): permite site próprio (score >= 70), mas exige aprovação em canal externo
    client.put("/api/autonomy/config", json={"level": "LEVEL_2_SEMIAUTOMATIC"})
    ev2_site = client.post(
        "/api/autonomy/evaluate",
        json={"action_type": "PUBLISH_CONTENT", "target_channel": "SITE", "content_quality_score": 88.0},
    ).json()
    assert ev2_site["autonomous_execution_allowed"] is True

    ev2_ext = client.post(
        "/api/autonomy/evaluate",
        json={"action_type": "PUBLISH_CONTENT", "target_channel": "YOUTUBE", "content_quality_score": 88.0},
    ).json()
    assert ev2_ext["autonomous_execution_allowed"] is False
    assert ev2_ext["requires_human_approval"] is True

    # 3. Testa Nível 3 (Autônomo Controlado): ainda exige aprovação humana obrigatória para as 7 ações restritas e score < 70
    client.put("/api/autonomy/config", json={"level": "LEVEL_3_CONTROLLED_AUTONOMOUS"})
    for restricted in (
        "PAID_EXPENSE",
        "NEW_INTEGRATION",
        "CREDENTIAL_CHANGE",
        "DAILY_LIMIT_EXCEEDED",
        "LOW_QUALITY_CONTENT",
        "UNVERIFIED_EXTERNAL_CHANNEL",
        "MASS_DELETION",
    ):
        ev_r = client.post(
            "/api/autonomy/evaluate",
            json={"action_type": restricted, "target_channel": "SITE", "content_quality_score": 95.0},
        ).json()
        assert ev_r["autonomous_execution_allowed"] is False
        assert ev_r["requires_human_approval"] is True

    ev_low_score = client.post(
        "/api/autonomy/evaluate",
        json={"action_type": "PUBLISH_CONTENT", "target_channel": "SITE", "content_quality_score": 62.0},
    ).json()
    assert ev_low_score["autonomous_execution_allowed"] is False

    # 4. Testa botão de emergência STOP ALL AUTOMATIONS
    stop_res = client.post(
        "/api/security/stop-all-automations",
        json={"actor": "admin_test", "reason": "Teste automatizado de parada de emergência"},
    )
    assert stop_res.status_code == 200
    assert stop_res.json()["emergency_stop"] is True
    assert stop_res.json()["dashboard_accessible"] is True

    # Com STOP ALL AUTOMATIONS ativo, o painel continua acessível, mas rotinas e autopilot são bloqueados
    dash_page = client.get("/")
    assert dash_page.status_code == 200
    routine_blocked = client.post("/api/autonomy/routines/every_6_hours/run").json()
    assert routine_blocked["status"] == "SKIPPED_EMERGENCY_STOP"

    # Retoma automações e executa rotinas
    res_resume = client.post("/api/security/resume-automations")
    assert res_resume.status_code == 200
    assert res_resume.json()["emergency_stop"] is False

    r_6h = client.post("/api/autonomy/routines/every_6_hours/run")
    assert r_6h.status_code == 200
    assert r_6h.json()["status"] == "COMPLETED"

    r_monthly = client.post("/api/autonomy/routines/monthly/run")
    assert r_monthly.status_code == 200
    assert r_monthly.json()["status"] == "COMPLETED"

    # 5. Testa Backup completo, verificação de integridade (PRAGMA + SHA256), limpeza e Restauração
    bkp_file = create_sqlite_backup(target_dir=tmp_path, db=db_session, backup_type="BEFORE_UPDATE")
    check = verify_backup_integrity(bkp_file)
    assert check["is_valid"] is True
    assert check["integrity_check"] == "ok"
    assert check["sha256"] is not None

    # Verifica que o JSON de configurações exportado não contém segredos
    exported_settings = list(tmp_path.glob("union_settings_*.json"))
    assert len(exported_settings) == 1
    settings_text = exported_settings[0].read_text(encoding="utf-8")
    assert '"secrets_included": false' in settings_text.lower()
    assert settings.SECRET_KEY not in settings_text

    # Restaura em um arquivo de banco isolado no tmp_path
    restored_target = tmp_path / "restored_test.db"
    restore_res = restore_sqlite_backup(
        backup_path=bkp_file,
        target_db_path=restored_target,
        expected_sha256=check["sha256"],
    )
    assert restore_res["status"] == "RESTORED"
    assert restore_res["integrity_check"] == "ok"


def test_group_i_ui_pages_and_init_script(client: TestClient):
    """Testa carregamento das interfaces web (Painel, Financeiro, Configurações, Site Público e Páginas Legais) e script de init."""
    init_res = initialize_environment()
    assert init_res["status"] == "INITIALIZED"
    assert init_res["dependencies_ok"] is True

    for route in (
        "/",
        "/finance",
        "/settings",
        "/autopilot",
        "/ofertas",
        "/ofertas/privacidade",
        "/ofertas/termos",
        "/ofertas/transparencia",
        "/ofertas/aviso-afiliados",
    ):
        resp = client.get(route)
        assert resp.status_code == 200, f"Falha ao carregar rota {route}"
        assert "STOP ALL AUTOMATIONS" in resp.text or "UNION OFERTAS" in resp.text
