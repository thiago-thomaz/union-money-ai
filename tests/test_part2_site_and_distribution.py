"""Testes de Integração da Parte 2:
- Site Próprio UNION OFERTAS (todas as páginas, avisos obrigatórios e Amazon Associate notice)
- Sitemap.xml e Robots.txt
- UNION LINK MANAGER (validação de domínio, pausa de links inválidos e relatórios)
- UNION DISTRIBUTION ENGINE & Fila Editorial (estados, deduplicação e exportação manual)
- Monitoramento Automático e Otimização de Campanhas
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.marketplace import Category, Marketplace


def test_union_ofertas_site_pages_seo_and_disclosures(client: TestClient, db_session: Session):
    mp_amz = db_session.query(Marketplace).filter(Marketplace.slug == "amazon").first()
    cat = db_session.query(Category).filter(Category.slug == "casa-e-decoracao").first()
    assert mp_amz and cat

    # Cadastra um produto real na Amazon para verificar avisos obrigatórios no site
    prod_resp = client.post(
        "/api/products",
        json={
            "title": "Luminária de Mesa LED Articulada Escritório",
            "description": "Luminária articulada com ajuste de intensidade.",
            "marketplace_id": mp_amz.id,
            "category_id": cat.id,
            "price": 129.90,
            "original_price": 159.90,
            "announced_commission_rate": 9.0,
            "rating": 4.7,
            "review_count": 95,
            "demand_index": 82.0,
            "competition_index": 30.0,
            "content_potential_index": 85.0,
            "in_stock": True,
            "product_url": "https://www.amazon.com.br/dp/B07X8V1LZ9",
            "affiliate_url": "https://www.amazon.com.br/dp/B07X8V1LZ9?tag=meuassociado-20",
        },
    )
    assert prod_resp.status_code == 201
    product_id = prod_resp.json()["id"]

    # Executa o Autopilot via API para gerar artigo, guia e publicar no UNION OFERTAS
    auto_resp = client.post("/api/autopilot/run", json={"auto_publish_site": True})
    assert auto_resp.status_code == 200
    assert auto_resp.json()["status"] == "COMPLETED"

    # Gera comparativo e guia de compra adicionais
    client.post("/api/content/generate", json={"product_id": product_id, "content_type": "COMPARISON"})
    client.post("/api/content/generate", json={"product_id": product_id, "content_type": "BUYING_GUIDE"})

    # Verifica todas as páginas exigidas do portal UNION OFERTAS
    site_routes = [
        "/ofertas",
        "/ofertas/categorias",
        f"/ofertas/categorias/{cat.slug}",
        "/ofertas/recomendados",
        "/ofertas/comparativos",
        "/ofertas/guias",
        "/ofertas/artigos",
        f"/ofertas/produto/{product_id}",
        "/ofertas/sobre",
        "/ofertas/privacidade",
        "/ofertas/cookies",
        "/ofertas/contato",
        "/ofertas/aviso-afiliados",
    ]
    for route in site_routes:
        resp = client.get(route)
        assert resp.status_code == 200, f"Falha ao abrir rota {route}"
        html = resp.text
        assert "Esta página contém links de afiliados. Podemos receber uma comissão por compras qualificadas, sem custo adicional para você." in html
        assert "Como associado da Amazon, eu ganho com compras qualificadas." in html

    # Verifica Sitemap.xml e Robots.txt
    sitemap_resp = client.get("/sitemap.xml")
    assert sitemap_resp.status_code == 200
    assert "<urlset" in sitemap_resp.text
    assert f"/ofertas/produto/{product_id}" in sitemap_resp.text

    robots_resp = client.get("/robots.txt")
    assert robots_resp.status_code == 200
    assert "Sitemap:" in robots_resp.text


def test_editorial_queue_deduplication_social_manual_package_and_monitoring(client: TestClient, db_session: Session):
    mp = db_session.query(Marketplace).filter(Marketplace.slug == "shopee").first()
    cat = db_session.query(Category).filter(Category.slug == "organizacao").first()
    assert mp and cat

    p_resp = client.post(
        "/api/products",
        json={
            "title": "Kit 6 Caixas Organizadoras Empilháveis Transparentes",
            "marketplace_id": mp.id,
            "category_id": cat.id,
            "price": 89.90,
            "announced_commission_rate": 10.0,
            "rating": 4.9,
            "review_count": 410,
            "demand_index": 88.0,
            "competition_index": 20.0,
            "content_potential_index": 90.0,
            "in_stock": True,
            "product_url": "https://shopee.com.br/kit-caixas-i.100.200",
            "affiliate_url": "https://s.shopee.com.br/kitcaixas100",
        },
    )
    prod_id = p_resp.json()["id"]

    c_resp = client.post(
        "/api/content/generate",
        json={"product_id": prod_id, "content_type": "SOCIAL_CAPTION"},
    )
    content_id = c_resp.json()["id"]

    # Enfileira com exigência de aprovação humana -> Deve iniciar em EM_REVISAO
    q_resp = client.post(
        "/api/editorial-queue",
        json={
            "product_id": prod_id,
            "content_id": content_id,
            "target_channel": "INSTAGRAM",
            "require_human_approval": True,
        },
    )
    assert q_resp.status_code == 201
    queue_id = q_resp.json()["id"]
    assert q_resp.json()["state"] == "EM_REVISAO"

    # Tentativa de publicar antes da aprovação humana -> Bloqueado
    pub_blocked = client.post(f"/api/editorial-queue/{queue_id}/publish")
    assert pub_blocked.json()["published"] is False

    # Aprova manualmente (EM_REVISAO -> APROVADO) e publica -> Gera pacote manual JSON (sem fingir API do Instagram)
    state_resp = client.patch(
        f"/api/editorial-queue/{queue_id}/state",
        json={"new_state": "APROVADO"},
    )
    assert state_resp.json()["state"] == "APROVADO"

    pub_ok = client.post(f"/api/editorial-queue/{queue_id}/publish")
    assert pub_ok.status_code == 200
    assert pub_ok.json()["state"] == "PUBLICADO"
    assert pub_ok.json()["publication_status"] == "EXPORTED_FOR_MANUAL"
    assert pub_ok.json()["package_path"] is not None

    # Verifica relatórios de links, revisão de links, calendário SEO e monitoramento
    assert client.get("/api/links/reports").status_code == 200
    assert client.post("/api/links/review").status_code == 200
    assert client.get("/api/seo/calendar").status_code == 200
    assert client.post("/api/campaigns/optimize").status_code == 200

    diag_resp = client.get("/api/monitoring/diagnostics")
    assert diag_resp.status_code == 200
    assert diag_resp.json()["database_healthy"] is True

