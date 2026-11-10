"""Testes de Painel Principal sem dados fictícios ('AGUARDANDO DADOS REAIS')."""

from fastapi.testclient import TestClient


def test_fresh_dashboard_displays_waiting_real_data_and_zero_fake_numbers(client: TestClient):
    resp_json = client.get("/api/dashboard/indicators")
    assert resp_json.status_code == 200
    data = resp_json.json()

    assert data["status_banner"] == "AGUARDANDO DADOS REAIS"
    assert data["confirmed_revenue_brl"] == 0.0
    assert data["pending_commissions_brl"] == 0.0
    assert data["approved_commissions_brl"] == 0.0
    assert data["cancelled_commissions_brl"] == 0.0
    assert data["registered_clicks"] == 0
    assert data["confirmed_conversions"] == 0
    assert data["best_marketplace"] == "AGUARDANDO DADOS REAIS"
    assert data["best_category"] == "AGUARDANDO DADOS REAIS"
    assert data["best_product"] == "AGUARDANDO DADOS REAIS"
    assert data["revenue_chart_status"] == "AGUARDANDO DADOS REAIS"

    resp_html = client.get("/")
    assert resp_html.status_code == 200
    assert "AGUARDANDO DADOS REAIS" in resp_html.text
    assert "UNION MONEY AI" in resp_html.text

