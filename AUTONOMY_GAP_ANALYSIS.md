# AUTONOMY GAP ANALYSIS — AUDITORIA DE DEPENDÊNCIAS MANUAIS (FASE 4)

**Data da Auditoria:** 2026-11-10  
**Projeto:** UNION MONEY AI  
**Escopo Inspecionado:** `app/integrations/`, `app/automation/`, `app/intelligence/`, `app/content_engine/`, `app/marketing/`, `app/finance/`, `app/core/`, `app/main.py`, `app/config.py`, `.env.example`.

---

## 1. Resumo da Auditoria das Fases 1 a 3

Nas Fases 1, 2 e 3, o sistema construiu a arquitetura de dados (24 tabelas), o motor de pontuação comercial (`ProductOpportunityScorer`), o motor de conteúdo e vídeo (`UnionContentEngine` e `UnionVideoEngine`), o portal público (`UNION OFERTAS`), a central financeira (`UnionFinanceAI`) e os controles de segurança/LGPD.

Entretanto, para atingir **autonomia operacional máxima pós-autorização inicial** (eliminando tarefas manuais recorrentes como cadastrar produtos, colar links, baixar/subir vídeos ou importar planilhas CSV manualmente), foram identificados **8 pontos de dependência manual** que passam a ser automatizados nesta Fase 4.

---

## 2. Mapeamento Detalhado dos 8 Gaps de Autonomia

### Gap 1 — Cadastro Manual de Produtos e Busca de Ofertas
1. **Funcionalidade atual:** `POST /api/products`, formulário HTML em `/products` e `app/intelligence/discovery.py` (`discover_from_marketplace` acionado sob demanda).
2. **Por que exige intervenção:** O fluxo de descoberta não persistia incrementalmente novos produtos elegíveis no banco nem suspendia automaticamente produtos que perderam atratividade ou ficaram sem estoque.
3. **Solução automática:** Implementar `AutonomousProductDiscovery` (`app/intelligence/autonomous_discovery.py`) integrado ao ciclo de 6 horas do `UnionAutonomousOrchestrator`, realizando busca incremental nas fontes autorizadas, categorização automática por taxonomia, deduplicação por `external_id`/URL, atualização de preços/estoque e suspensão automática de itens inválidos ou desinteressantes.
4. **API necessária:**
   - Mercado Livre: `GET https://api.mercadolibre.com/sites/MLB/search` e `GET /items/{id}`
   - Shopee Brasil: `POST https://open-api.affiliate.shopee.com.br/graphql` (`productOfferV2`)
   - Amazon Brasil: `PA-API 5.0 SearchItems / GetItems` (ou Creators API quando elegível)
5. **Permissão necessária:** Token OAuth Bearer (`read` / busca de catálogo) no Mercado Livre; `SHOPEE_APP_ID` + `SHOPEE_APP_SECRET` na Shopee; `AMAZON_ACCESS_KEY` + `AMAZON_SECRET_KEY` + `AMAZON_PARTNER_TAG` na Amazon.
6. **Teste de validação:** `test_autonomous_discovery_incremental_deduplication_and_stale_suspension` em `tests/test_part4_full_autonomy_24_7.py`.

---

### Gap 2 — Geração e Atualização Manual de Links de Afiliados
1. **Funcionalidade atual:** `create_tracked_link` em `app/marketing/link_manager.py` e formulário em `/products`.
2. **Por que exige intervenção:** Quando um produto era atualizado ou descoberto sem link parametrizado por campanha/canal, o operador precisava informar a URL de afiliado manualmente.
3. **Solução automática:** Implementar `UnionLinkManager.auto_generate_and_verify_for_product` integrado ao `UnionConnect`, consultando o mecanismo oficial de afiliados da plataforma (geração de shortlink GraphQL `generateShortLink` na Shopee, parametrização `matt_tool` / `/sec/` no Mercado Livre e `?tag=` na Amazon), vinculando campanha, validando formato e bloqueando links sem atribuição real (`AUTHORIZATION_REQUIRED` quando sem tag/credencial).
4. **API necessária:** Shopee GraphQL (`generateShortLink`), parametrizadores oficiais de Associados Amazon (`tag`) e Mercado Livre Afiliados (`matt_tool` / `/sec/`).
5. **Permissão necessária:** Conta de afiliado aprovada e tag/credencial configurada no `.env` / `UNION CONNECT`.
6. **Teste de validação:** `test_auto_affiliate_link_generation_and_no_fake_links` em `tests/test_part4_full_autonomy_24_7.py`.

---

### Gap 3 — Gestão Centralizada de Tokens OAuth, Renovação e Reconexão
1. **Funcionalidade atual:** Conectores isolados em `app/integrations/mercadolivre.py`, `amazon.py`, `shopee.py` e `app/integrations/social/` lendo apenas variáveis estáticas do `.env`.
2. **Por que exige intervenção:** Tokens OAuth que expiram (como `ML_ACCESS_TOKEN`, `YOUTUBE_ACCESS_TOKEN`, `PINTEREST_ACCESS_TOKEN`, `GSC_ACCESS_TOKEN`) exigiriam edição manual do `.env` a cada expiração.
3. **Solução automática:** Criar a central **`UNION CONNECT`** (`app/integrations/union_connect.py`) e a tabela `integration_tokens` (`IntegrationCredentialToken`) com armazenamento seguro, verificação de validade, renovação automática via `refresh_token`, controle de escopos, reconexão automática e indicadores individuais (`ACTIVE`, `AUTHORIZATION_REQUIRED`, `PENDING`, `ERROR`, `DISABLED`) para os 8 conectores (Mercado Livre, Amazon, Shopee, YouTube, Instagram, Pinterest, Google Search Console e Google Analytics 4).
4. **API necessária:** Endpoints OAuth 2.0 oficiais de cada provedor (`https://api.mercadolibre.com/oauth/token`, `https://oauth2.googleapis.com/token`, `https://graph.facebook.com/v19.0/oauth/access_token`, `https://api.pinterest.com/v5/oauth/token`).
5. **Permissão necessária:** Autorização OAuth inicial concedida uma única vez pelo proprietário da conta (`refresh_token` offline).
6. **Teste de validação:** `test_union_connect_8_connectors_token_renewal_and_authorization_states` em `tests/test_part4_full_autonomy_24_7.py`.

---

### Gap 4 — Produção de Conteúdo e Atualização de Conteúdos Antigos Sem Pipeline de 9 Estados
1. **Funcionalidade atual:** `UnionContentEngine.produce` em `app/content_engine/union_content_engine.py` gerava itens diretamente como `READY` ou `BLOCKED_LOW_QUALITY`.
2. **Por que exige intervenção:** Não havia máquina de estados persistida (`DISCOVERY -> ANALYSIS -> SCRIPT -> CONTENT -> QUALITY_CHECK -> SEO -> READY -> PUBLISHED -> MONITORING`) nem atualização automática de artigos/páginas antigas quando o preço ou estoque do produto mudava.
3. **Solução automática:** Implementar `AutonomousContentPipeline` (`app/content_engine/autonomous_pipeline.py`) com tabela `content_production_pipeline` (`ContentProductionPipeline`), executando todas as 9 etapas sem qualquer upload manual de imagem ou vídeo e atualizando automaticamente conteúdos antigos quando há variação de preço/disponibilidade.
4. **API necessária:** Execução 100% nativa local (`NativePythonProvider`, `Pillow`, `FFmpeg`, `UnionSEOEngine`) + provedores locais opcionais.
5. **Permissão necessária:** Nenhuma permissão externa exigida (100% autônomo localmente).
6. **Teste de validação:** `test_autonomous_9_stage_content_pipeline_and_stale_refresh` em `tests/test_part4_full_autonomy_24_7.py`.

---

### Gap 5 — Publicação Multicanal Sem Download/Upload Manual de Arquivos
1. **Funcionalidade atual:** `UnionDistributionEngine.publish_queue_item` em `app/marketing/distribution.py` publicava automaticamente no portal `UNION OFERTAS` (`/ofertas`), mas apenas exportava JSON local para YouTube, Instagram e Pinterest.
2. **Por que exige intervenção:** Os conectores sociais (`youtube.py`, `instagram.py`, `pinterest.py`) não possuíam validação pré-envio de dimensões/duração/disclosure nem chamadas reais de upload via API oficial quando o token OAuth estava ativo.
3. **Solução automática:** Criar `MultiChannelAutoPublisher` (`app/marketing/multichannel_publisher.py`) que valida formato, dimensões (`9:16`, `16:9`, `1:1`), duração (`<= 60s` para Shorts/Reels), descrição e aviso de afiliado, publica diretamente no `UNION OFERTAS` e realiza chamadas HTTP autenticadas para YouTube Data API v3 (`videos.insert`), Instagram Graph API (`media` + `media_publish`) e Pinterest API v5 (`pins`) quando o conector está `ACTIVE`. Quando sem autorização da plataforma, registra `BLOQUEADA POR AUTORIZAÇÃO` sem fingir publicação.
4. **API necessária:** YouTube Data API v3, Instagram Graph API, Pinterest API v5.
5. **Permissão necessária:** `youtube.upload` (Google OAuth), `instagram_content_publish` (Meta Graph OAuth), `pins:write` / `boards:read` (Pinterest OAuth).
6. **Teste de validação:** `test_multichannel_auto_publisher_validation_and_honest_auth_blocking` em `tests/test_part4_full_autonomy_24_7.py`.

---

### Gap 6 — Importação Manual de Planilhas CSV de Vendas e Comissões
1. **Funcionalidade atual:** `POST /api/finance/import-csv` e formulário em `/finance` (`UnionFinanceAI.import_official_csv_report`).
2. **Por que exige intervenção:** O operador precisava baixar o CSV no painel do marketplace e colar/enviar manualmente na tela financeira.
3. **Solução automática:** Criar `AutoSalesTracker` (`app/finance/auto_sales_tracker.py`) operando em 4 níveis automáticos:
   1. Consulta direta à API oficial de relatórios de conversão (ex.: Shopee GraphQL `conversionReport` e API de pedidos Mercado Livre).
   2. API oficial de pedidos/conversões.
   3. Endpoint receptor de Webhooks oficiais assinados (`POST /api/webhooks/conversions/{marketplace_slug}`).
   4. Leitor automático somente-leitura de relatórios oficiais recebidos por e-mail via IMAP/OAuth (`sync_official_email_reports`).
4. **API necessária:** Shopee Affiliate GraphQL (`conversionReport`), Mercado Livre Orders/Billing API, Webhooks HMAC e IMAP OAuth2 (somente leitura).
5. **Permissão necessária:** Escopo de leitura de relatórios de afiliados nas APIs ou token OAuth de leitura de caixa de entrada dedicada.
6. **Teste de validação:** `test_auto_sales_tracker_api_webhook_and_email_ingest_without_manual_csv` em `tests/test_part4_full_autonomy_24_7.py`.

---

### Gap 7 — Reajuste Manual de Prioridades Comerciais e SEO Externo
1. **Funcionalidade atual:** `CommercialLearningEngine` gerava recomendações textuais, mas exigia revisão humana para alterar prioridades de categorias, produtos e campanhas.
2. **Por que exige intervenção:** As prioridades das campanhas e produtos não eram recalculadas automaticamente a cada ciclo com base em cliques, conversões, comissões `PAID`, horários de pico e taxa de cancelamento.
3. **Solução automática:** Criar **`UNION GROWTH AI`** (`app/intelligence/union_growth_ai.py`) que analisa cliques, vendas, comissões pagas, categorias, canais, conteúdos, palavras-chave comerciais, horários de melhor desempenho e cancelamentos, reajustando automaticamente os pesos de prioridade das campanhas e pautas orgânicas sem jamais aumentar gastos ou comprar tráfego.
4. **API necessária:** Banco de dados interno + integração opcional com Google Search Console API e Google Analytics 4 Data API quando `ACTIVE`.
5. **Permissão necessária:** Opcional: `webmasters.readonly` (GSC) e `analytics.readonly` (GA4).
6. **Teste de validação:** `test_union_growth_ai_continuous_priority_updates_zero_spend` em `tests/test_part4_full_autonomy_24_7.py`.

---

### Gap 8 — Aprovação Recorrente e Fila Volátil em Reinicializações
1. **Funcionalidade atual:** `AutonomyManager` iniciava em `LEVEL_2_SEMIAUTOMATIC` ou `LEVEL_3_CONTROLLED_AUTONOMOUS` sem flags granulares `AUTO_*` por subsistema e sem fila persistente de jobs de 6h/diário/semanal/mensal.
2. **Por que exige intervenção:** Tarefas agendadas precisavam de fila persistente no banco (`PersistentOrchestratorQueue`) e ativação coordenada por `AUTONOMY_MODE=FULL` + flags técnicas `AUTO_*`.
3. **Solução automática:** Criar **`UNION AUTONOMOUS ORCHESTRATOR`** (`app/automation/autonomous_orchestrator.py`) e supervisor de execução contínua (`scripts/keep_alive_runner.py`), gerenciando ciclos de 6h, diário, semanal e mensal com fila persistente no SQLite/PostgreSQL, locks, retry com backoff, recuperação automática e distinção estrita entre **autorização única inicial** e **operação recorrente 100% automática**.
4. **API necessária:** APScheduler nativo + SQLite/PostgreSQL.
5. **Permissão necessária:** Permissão local de execução de processo Python contínuo (ou serviço systemd/Task Scheduler).
6. **Teste de validação:** `test_union_autonomous_orchestrator_cycles_queue_recovery_and_full_e2e_flow` em `tests/test_part4_full_autonomy_24_7.py`.

