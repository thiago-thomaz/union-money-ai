# Arquitetura Técnica — UNION MONEY AI (Parte 1)

## Visão Geral Modular
A arquitetura do **UNION MONEY AI** foi construída em Python 3.12 com separação estrita de responsabilidades:

1. **`app/core/`**: Segurança (`bcrypt`, HMAC, anti-bot fingerprinting), permissões RBAC, logging rotativo (`logs/union_money_ai.log`), barramento de eventos interno e agendador nativo (`APScheduler` — sem n8n).
2. **`app/models/`**: 20 entidades relacionais em SQLAlchemy 2.0 (compatível com SQLite e PostgreSQL), incluindo trilha imutável de auditoria financeira (`FinancialHistory` + `change_history` JSON).
3. **`app/integrations/`**: Conectores independentes para **Mercado Livre**, **Amazon Brasil** e **Shopee Brasil** + conectores sociais (**YouTube**, **Instagram**, **Pinterest**), com rate limiting por janela deslizante e fluxo de importação manual autorizada.
4. **`app/intelligence/`**:
   - **Product Opportunity Score (0 a 100)** com 8 dimensões de pesos configuráveis, indicador de confiança (`confidence_score`) e separação entre dados `VERIFIED`, `ESTIMATED` e `UNAVAILABLE`.
   - **Motor de Aprendizado Comercial** baseado em estatística determinística real e mecanismo de testes A/B com cálculo de significância estatística (Teste Z).
5. **`app/content_engine/`**: Produção local de artigos SEO, roteiros de vídeo, legendas com aviso de transparência (`#afiliado`), miniaturas gráficas (`Pillow`) e renderização de vídeo (`FFmpeg`).
6. **`app/marketing/` & `app/finance/`**: Gerenciador de links rastreáveis (`/r/{short_code}`), gerador de Landing Pages HTML5, fluxo de caixa realizado, reconciliação automática de comissões aprovadas e relatórios em PDF (`ReportLab`).

