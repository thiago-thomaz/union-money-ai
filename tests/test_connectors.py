"""Testes dos Conectores de Marketplaces (Mercado Livre, Amazon Brasil, Shopee Brasil)."""

import pytest
from app.core.exceptions import CredentialsMissingError, RateLimitExceededError
from app.integrations.amazon import AmazonBrasilConnector
from app.integrations.mercadolivre import MercadoLivreConnector
from app.integrations.shopee import ShopeeBrasilConnector


def test_connectors_never_fake_api_when_credentials_missing():
    ml = MercadoLivreConnector()
    amz = AmazonBrasilConnector()
    shp = ShopeeBrasilConnector()

    assert ml.check_availability()["availability_status"] == "MISSING_CREDENTIALS"
    assert amz.check_availability()["availability_status"] in ("MISSING_CREDENTIALS", "ELIGIBILITY_REQUIRED")
    assert shp.check_availability()["availability_status"] == "MISSING_CREDENTIALS"

    with pytest.raises(CredentialsMissingError):
        ml.search_products("notebook")

    with pytest.raises(CredentialsMissingError):
        amz.search_products("kindle")

    with pytest.raises(CredentialsMissingError):
        shp.search_products("airfryer")


def test_connectors_affiliate_link_builders_and_manual_import():
    ml = MercadoLivreConnector()
    amz = AmazonBrasilConnector()
    shp = ShopeeBrasilConnector()

    ml_link = ml.build_affiliate_link("https://www.mercadolivre.com.br/p/MLB12345", affiliate_tag="minhatag")
    assert "matt_tool=minhatag" in ml_link

    amz_link = amz.build_affiliate_link("https://www.amazon.com.br/dp/B08N5WRWNW", affiliate_tag="associado-20")
    assert amz_link == "https://www.amazon.com.br/dp/B08N5WRWNW?tag=associado-20"

    shp_link = shp.build_affiliate_link("https://shopee.com.br/produto-i.123.456", affiliate_tag="998877")
    assert "af_siteid=998877" in shp_link

    norm = amz.normalize_manual_import(
        {
            "title": "Echo Dot 5a Geração",
            "product_url": "https://www.amazon.com.br/dp/B09B8V1LZ3",
            "affiliate_tag": "meuassoc-20",
            "price": 349.00,
        }
    )
    assert norm["affiliate_url"] == "https://www.amazon.com.br/dp/B09B8V1LZ3?tag=meuassoc-20"
    assert norm["data_source"] == "MANUAL_VERIFIED"
    assert norm["is_synthetic_test"] is False


def test_connector_rate_limiter_enforces_limits():
    ml = MercadoLivreConnector(rate_limit_per_minute=2)
    ml.enforce_rate_limit()
    ml.enforce_rate_limit()
    with pytest.raises(RateLimitExceededError):
        ml.enforce_rate_limit()

