"""Testes de APIs REST, CRUD de Produtos, Cliques Anti-Bot, Conteúdo e Fluxo Financeiro."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.affiliate import AffiliateLink
from app.models.marketplace import Category, Marketplace


def test_full_product_crud_content_click_and_conversion_flow(client: TestClient, db_session: Session):
    mp = db_session.query(Marketplace).filter(Marketplace.slug == "mercadolivre").first()
    cat = db_session.query(Category).filter(Category.slug == "cozinha").first()
    assert mp and cat

    # 1. CREATE Product via API
    create_resp = client.post(
        "/api/products",
        json={
            "title": "Fritadeira Elétrica Airfryer 4L Inox",
            "marketplace_id": mp.id,
            "category_id": cat.id,
            "price": 299.90,
            "original_price": 399.90,
            "announced_commission_rate": 10.0,
            "rating": 4.8,
            "review_count": 210,
            "demand_index": 88.0,
            "competition_index": 25.0,
            "content_potential_index": 90.0,
            "in_stock": True,
            "product_url": "https://www.mercadolivre.com.br/airfryer-4l",
            "affiliate_url": "https://mercadolivre.com/sec/airfryer4l",
        },
    )
    assert create_resp.status_code == 201
    prod_data = create_resp.json()
    product_id = prod_data["id"]
    assert prod_data["opportunity_score"] is not None
    assert prod_data["opportunity_score"] >= 75.0

    # 2. READ Product
    get_resp = client.get(f"/api/products/{product_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["title"] == "Fritadeira Elétrica Airfryer 4L Inox"

    # 3. UPDATE Product
    put_resp = client.put(
        f"/api/products/{product_id}",
        json={"price": 279.90, "announced_commission_rate": 12.0},
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["price"] == 279.90

    # 4. Generate Content (Article & Thumbnail)
    art_resp = client.post(
        "/api/content/generate",
        json={"product_id": product_id, "content_type": "ARTICLE"},
    )
    assert art_resp.status_code == 201
    content_id = art_resp.json()["id"]

    thumb_resp = client.post(
        "/api/content/generate",
        json={"product_id": product_id, "content_type": "THUMBNAIL"},
    )
    assert thumb_resp.status_code == 201
    assert thumb_resp.json()["media_path"] is not None

    # 5. Publish Content to Landing Page
    pub_resp = client.post(
        "/api/publications",
        json={"content_id": content_id, "channel": "LANDING_PAGE"},
    )
    assert pub_resp.status_code == 201
    assert pub_resp.json()["status"] == "PUBLISHED"

    # 6. Tracked Link Click: Human vs Bot; Cliques NUNCA são contabilizados como vendas
    link = db_session.query(AffiliateLink).filter(AffiliateLink.product_id == product_id).first()
    assert link is not None

    # Bot click (não deve contar nos cliques humanos válidos)
    bot_click = client.get(
        f"/r/{link.short_code}",
        headers={"user-agent": "Googlebot/2.1 (+http://www.google.com/bot.html)"},
        follow_redirects=False,
    )
    assert bot_click.status_code == 302

    dash_after_bot = client.get("/api/dashboard/indicators").json()
    assert dash_after_bot["registered_clicks"] == 0
    assert dash_after_bot["confirmed_conversions"] == 0

    # Human click
    human_click = client.get(
        f"/r/{link.short_code}",
        headers={"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0"},
        follow_redirects=False,
    )
    assert human_click.status_code == 302

    dash_after_human = client.get("/api/dashboard/indicators").json()
    assert dash_after_human["registered_clicks"] == 1
    assert dash_after_human["confirmed_conversions"] == 0
    assert dash_after_human["confirmed_revenue_brl"] == 0.0

    # 7. Record Confirmed Conversion with Approved Commission
    conv_resp = client.post(
        "/api/finance/conversions",
        json={
            "product_id": product_id,
            "source": "MERCADOLIVRE_OFFICIAL_REPORT",
            "order_value": 279.90,
            "commission_amount": 33.59,
            "commission_status": "APPROVED",
            "external_reference": "MLB-ORDER-777",
        },
    )
    assert conv_resp.status_code == 201

    dash_final = client.get("/api/dashboard/indicators").json()
    assert dash_final["confirmed_conversions"] == 1
    assert dash_final["approved_commissions_brl"] == 33.59
    assert dash_final["confirmed_revenue_brl"] == 33.59
    assert "Mercado Livre" in dash_final["best_marketplace"]
    assert "Cozinha" in dash_final["best_category"]

    # 8. DELETE Product (Soft Delete)
    del_resp = client.delete(f"/api/products/{product_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "DELETED"

