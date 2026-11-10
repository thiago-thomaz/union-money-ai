# Política de Integrações e Conformidade — UNION MONEY AI

## 1. Mercado Livre Brasil
- **API Oficial:** Utiliza `https://api.mercadolibre.com` mediante configuração de `ML_ACCESS_TOKEN` (OAuth 2.0 oficial).
- **Programa de Afiliados:** Suporta links oficiais `/sec/...` gerados na central de afiliados do Mercado Livre ou parametrização `matt_tool` autorizada.
- **Ausência de Token:** Não realiza scraping proibido. Informa `MISSING_CREDENTIALS` e habilita importação manual de links e produtos verificados.

## 2. Amazon Brasil
- **Programa de Associados:** Suporta geração direta de links com `AMAZON_PARTNER_TAG` (`https://www.amazon.com.br/dp/{ASIN}?tag={tag}`).
- **PA-API 5.0 / Creators API:** A consulta automatizada de catálogo na Amazon exige elegibilidade da conta de Associado (vendas qualificadas mínimas) e chaves `AMAZON_ACCESS_KEY` / `AMAZON_SECRET_KEY`. Sem essas chaves, o conector informa explicitamente `ELIGIBILITY_REQUIRED` ou `MISSING_CREDENTIALS`.

## 3. Shopee Brasil
- **Shopee Affiliate Open API:** Suporta consultas autenticadas via assinatura SHA256 (`SHOPEE_APP_ID` + `SHOPEE_APP_SECRET`) no endpoint GraphQL oficial (`https://open-api.affiliate.shopee.com.br/graphql`).
- **Importação Manual:** Quando sem chaves de Open API, opera com importação manual de links oficiais (`s.shopee.com.br`) gerados pelo afiliado.

