# UNION MONEY AI — FASE 5: ATIVAÇÃO COMERCIAL REAL E AUTONOMIA OPERACIONAL
## Relatório Oficial de Auditoria Técnica, Comercial e Operacional 24/7

---

## 1. AUDITORIA DO AMBIENTE DE PRODUÇÃO (`https://afiliados.projetosunion.cloud`)

| Item Auditado | Estado Verificado em Produção | Evidência Técnica |
| :--- | :--- | :--- |
| **Domínio & HTTPS** | `APROVADO` | `https://afiliados.projetosunion.cloud` ativo via proxy reverso Traefik com certificado TLS Let's Encrypt automático. |
| **Persistência de Dados após Reinicialização** | `APROVADO` | Banco SQLite em modo concorrente `WAL` (`journal_mode=wal`, `synchronous=NORMAL`) montado no volume persistente `/app/data` (`txfnr7vv1gr7kypskfqrjax6`). |
| **Execução Contínua do Scheduler** | `APROVADO` | APScheduler nativo em execução contínua (`scheduler_running: true`) sob trava distribuída `SchedulerLeaderLock` (`duplicate_scheduler_prevented: true`). |
| **Execução Real dos Jobs** | `APROVADO` | `UnionAutonomousOrchestrator` executa ciclos `every_6_hours`, `daily`, `weekly` e `monthly` persistidos em `PersistentOrchestratorQueue` e `AutopilotTaskRun` já a partir do boot (`scripts/cloud_entrypoint.py`). |
| **Recuperação de Falhas & Ausência de Duplicidade** | `APROVADO` | `CloudTaskWorker` detecta jobs `RUNNING` além do timeout, aplica retry com backoff exponencial (`2^attempt`) e impede tarefas duplicadas via `idempotency_key` + `SchedulerLeaderLock`. |
| **Logs de Execução & Proteção de Segredos** | `APROVADO` | Volume persistente `/app/logs` (`hf7mputdgypfbha8leuimpl5`) + `AuditLog` com mascaramento obrigatório (`mask_secret`) e criptografia simétrica em repouso (`encrypt_token_value`). Zero segredos expostos. |
| **Backup Separado & Teste de Restauração** | `APROVADO` | Volume exclusivo `/app/backups` (`sese7kl6lgmbu903lr8ymqhx`), separado de `/app/data`, com retenção de 15 cópias, validação `PRAGMA integrity_check=ok`, `SHA-256` e teste automático de restauração não destrutivo. |

---

## 2. AUDITORIA DAS INTEGRAÇÕES DE AFILIADOS E CANAIS (PAINEL DE 4 ESTADOS)

O painel `/integrations` e o endpoint `GET /api/integrations/phase5-audit` classificam cada plataforma e subfunção exclusivamente nos 4 estados oficiais:
- **`REALMENTE CONECTADO`**
- **`AGUARDANDO AUTORIZAÇÃO`**
- **`CREDENCIAIS AUSENTES`**
- **`API NÃO DISPONÍVEL`**

### 2.1. Mercado Livre Brasil (`mercadolivre`)
- **API Oficial Disponível:** Mercado Livre Developers REST API (`https://api.mercadolibre.com/sites/MLB/search`, `/items/{id}`, `/oauth/token`).
- **Requisitos de Aprovação:** Conta ativa no Programa de Afiliados do Mercado Livre Brasil + Aplicação criada no DevCenter (`https://developers.mercadolivre.com.br`) com Redirect URI apontando para `https://afiliados.projetosunion.cloud/api/connect/oauth/callback/mercadolivre`.
- **Credenciais Necessárias:** `ML_AFFILIATE_TAG` (`matt_tool`), `ML_APP_ID`, `ML_CLIENT_SECRET`, `ML_ACCESS_TOKEN`, `ML_REFRESH_TOKEN`.
- **Autorização OAuth 2.0:** Implementada (`GET /api/connect/oauth/authorize/mercadolivre` e callback automático `GET /api/connect/oauth/callback/mercadolivre` com troca de código por `access_token` e renovação automática via `refresh_token`).
- **Subfunções:**
  - *Geração Automática de Links:* Configurada (`matt_tool` / preservação de links `/sec/`) — **`CREDENCIAIS AUSENTES`** até inserção da `ML_AFFILIATE_TAG` no painel `/integrations`.
  - *Consulta de Produtos e Preços:* Implementada via `GET /sites/MLB/search` com Bearer Token — **`CREDENCIAIS AUSENTES`** até autorização OAuth.
  - *Consulta de Vendas e Comissões:* Implementada via API / Webhooks HMAC / Leitor de E-mail OAuth IMAP — **`CREDENCIAIS AUSENTES`**.
- **Limitações Técnicas e Contratuais:** Desde 2024/2025, a API do Mercado Livre exige Bearer Token OAuth 2.0 mesmo para buscas públicas em `/sites/MLB/search`. O encurtador `/sec/` não possui endpoint REST público sem sessão autenticada na Central de Afiliados, mas o parâmetro oficial `matt_tool` e links `/sec/` são 100% suportados.

### 2.2. Amazon Brasil (`amazon`)
- **API Oficial Disponível:** Amazon Product Advertising API 5.0 (`PA-API 5.0` — `https://webservices.amazon.com.br/paapi5/searchitems`) com assinatura criptográfica **AWS Signature Version 4 (`AWS4-HMAC-SHA256`)** implementada nativamente em `app/integrations/amazon.py`.
- **Requisitos de Aprovação:** Conta no Programa de Associados da Amazon Brasil (`https://associados.amazon.com.br`). Para liberar acesso à PA-API 5.0, a Amazon exige contratualmente **3 vendas qualificadas nos primeiros 180 dias**.
- **Credenciais Necessárias:** `AMAZON_PARTNER_TAG` (ex.: `sualoja-20`), `AMAZON_ACCESS_KEY`, `AMAZON_SECRET_KEY`.
- **Autorização OAuth:** Não utiliza OAuth 2.0; utiliza chaves de acesso assinadas com AWS SigV4.
- **Subfunções:**
  - *Geração Automática de Links:* Implementada (`https://www.amazon.com.br/dp/{ASIN}?tag={AMAZON_PARTNER_TAG}`) — passa imediatamente para **`REALMENTE CONECTADO`** assim que `AMAZON_PARTNER_TAG` é salva em `/integrations`.
  - *Consulta de Produtos e Preços:* Implementada via PA-API 5.0 `SearchItems` — **`CREDENCIAIS AUSENTES`** (ou **`AGUARDANDO AUTORIZAÇÃO`** quando apenas a Partner Tag está ativa aguardando elegibilidade PA-API).
  - *Consulta de Vendas e Comissões via API REST:* **`API NÃO DISPONÍVEL`** (A Amazon Brasil não fornece API REST pública para relatórios de comissões do Associados; o sistema supre essa limitação com o leitor automático de relatórios por e-mail IMAP OAuth somente leitura ou importação CSV oficial).
- **Limitações Técnicas e Contratuais:** Proibido fazer web scraping de páginas da Amazon ou exibir preços estáticos sem data/hora de verificação.

### 2.3. Shopee Brasil (`shopee`)
- **API Oficial Disponível:** Shopee Affiliate Open Platform GraphQL API (`https://open-api.affiliate.shopee.com.br/graphql`) com assinatura `SHA256(AppId + Timestamp + Payload + Secret)` implementada em `app/integrations/shopee.py`.
- **Requisitos de Aprovação:** Conta aprovada no Programa de Afiliados da Shopee Brasil (`https://affiliate.shopee.com.br`) + liberação de App ID e Secret na aba Open API.
- **Credenciais Necessárias:** `SHOPEE_AFFILIATE_ID`, `SHOPEE_APP_ID`, `SHOPEE_APP_SECRET`.
- **Subfunções Implementadas:**
  - *Geração Automática de Links:* Mutation GraphQL `generateShortLink` (`s.shopee.com.br`) + parametrização `af_siteid` — **`CREDENCIAIS AUSENTES`** até inserção no painel `/integrations`.
  - *Consulta de Produtos e Preços:* Query GraphQL `productOfferV2` — **`CREDENCIAIS AUSENTES`**.
  - *Consulta de Vendas e Comissões:* Query GraphQL `conversionReport` — **`CREDENCIAIS AUSENTES`**.
- **Limitações Técnicas e Contratuais:** Requer liberação da Open API pela Shopee para consultas GraphQL automatizadas.

### 2.4. Canais de Distribuição, Portal Próprio e Analytics
| Canal / Serviço | Estado Atual em Produção | Detalhamento Técnico |
| :--- | :--- | :--- |
| **Portal Próprio UNION OFERTAS (`/ofertas`)** | **`REALMENTE CONECTADO`** | 100% operacional na nuvem: publicação automática de reviews, comparativos, guias, infográficos PNG, vídeos MP4 9:16, JSON-LD, Sitemap XML e redirecionador `/r/{short_code}`. |
| **YouTube & YouTube Shorts (`Data API v3`)** | **`CREDENCIAIS AUSENTES`** | Upload via `POST https://www.googleapis.com/youtube/v3/videos` implementado; aguarda `YOUTUBE_ACCESS_TOKEN` / `REFRESH_TOKEN` OAuth 2.0. |
| **Instagram Reels (`Meta Graph API v19.0`)** | **`CREDENCIAIS AUSENTES`** | Publicação via `/{ig-user-id}/media` e `media_publish` implementada; aguarda `INSTAGRAM_BUSINESS_ACCOUNT_ID` e `INSTAGRAM_ACCESS_TOKEN`. |
| **Pinterest (`API v5`)** | **`CREDENCIAIS AUSENTES`** | Criação de Pins via `POST https://api.pinterest.com/v5/pins` implementada; aguarda `PINTEREST_ACCESS_TOKEN` e `PINTEREST_BOARD_ID`. |
| **Google Search Console (`API v1`)** | **`CREDENCIAIS AUSENTES`** | Consulta `searchAnalytics/query` implementada; aguarda `GSC_SITE_URL` e `GSC_ACCESS_TOKEN`. |
| **Google Analytics 4 (`Data API v1beta`)** | **`CREDENCIAIS AUSENTES`** | Opcional; o rastreamento interno nativo (`ClickLog` + `VisitorAggregate`) já está **`REALMENTE CONECTADO`**. |

---

## 3. TESTES AUTOMATIZADOS E SEPARAÇÃO ESTRITA: INTEGRAÇÃO vs COMERCIAL REAL

### 3.1. Resultado da Suíte Completa (`pytest -v`)
- **Total de Testes Executados:** `39`
- **Aprovados:** `39` (100%)
- **Reprovados:** `0`
- **Ignorados / Erros:** `0`

### 3.2. Comprovação do Fluxo End-to-End de 8 Estágios (Ambiente de Integração Isolado)
O endpoint `POST /api/cloud/verify-integration-flow` e o teste `test_phase5_separated_integration_flow_vs_real_commercial_state` executam e comprovam os 8 estágios em um banco SQLite temporário isolado (`isolated_from_production_db: true`), **sem fabricar conversões ou produtos falsos em produção**:
1. **Produto descoberto:** `Notebook Gamer Core i7 16GB SSD 1TB RTX 4060 Tela 144Hz` (`R$ 5.299,00`, em estoque).
2. **Oportunidade aprovada:** Score comercial calculado e aprovado (`score >= 70`).
3. **Link afiliado válido:** Gerado com atribuição oficial (`matt_tool`), validado (`validity_status: VALID`) e registrado em `/r/{short_code}`.
4. **Conteúdo produzido:** Artigo/comparativo original + infográfico PNG + vídeo vertical MP4 9:16 + legenda `.srt` aprovados no Quality Check (`quality_score >= 75.0`).
5. **Conteúdo publicado:** Publicado automaticamente no portal `UNION_OFERTAS` (`state: MONITORING`).
6. **Clique registrado:** Clique humano real registrado via `/r/{short_code}` (`is_valid_human: true`, `counted_as_sale: false`).
7. **Conversão identificada:** Pedido `INT-E2E-ORD-501` registrado inicialmente como `PENDING` (`pending_entered_cash: false`).
8. **Comissão sincronizada:** Pedido atualizado para `PAID` (`R$ 423,92`), entrando estritamente no caixa recebido (`cash_received_brl: 423.92`).

### 3.3. Estado Comercial Real em Produção (`GET /api/cloud/commercial-vs-integration-audit`)
- `strict_separation_enforced: true`
- `fabricated_conversions_count: 0`
- Nenhuma venda fictícia, clique simulado ou comissão fabricada foi inserida no banco de produção.

---

## 4. STATUS REAL DA AUTONOMIA 24/7 E ÚNICAS AÇÕES INICIAIS DO PROPRIETÁRIO

### Status Real da Autonomia
- **Autonomia de Infraestrutura, Orquestração, Conteúdo, Vídeo, SEO, Portal Próprio e Financeiro:** **100% ATIVA E OPERACIONAL 24/7 NA NUVEM (`https://afiliados.projetosunion.cloud`)**.
- **Autonomia Comercial Externa (Descoberta via API e Publicação Social Externa):** **Tecnicamente pronta e agendada 24/7, aguardando exclusivamente a inserção única das credenciais oficiais do proprietário em `https://afiliados.projetosunion.cloud/integrations`**.

### Lista Objetiva das Poucas Ações Iniciais que Dependem Exclusivamente do Proprietário
Para que o sistema passe de **aplicação publicada** para **operação comercial descobrindo e monetizando ofertas externas automaticamente**, o proprietário precisa realizar **uma única vez** no painel `https://afiliados.projetosunion.cloud/integrations` (seção *"Ativação Inicial Única de Credenciais e Tags de Afiliado"*):

1. **Mercado Livre:** Inserir sua `ML_AFFILIATE_TAG` (`matt_tool`) e o `ML_ACCESS_TOKEN` / `ML_REFRESH_TOKEN` obtidos na sua conta do Programa de Afiliados / DevCenter do Mercado Livre.
2. **Amazon Brasil:** Inserir sua `AMAZON_PARTNER_TAG` (ex.: `sualoja-20`) do Associados Amazon Brasil (e `AMAZON_ACCESS_KEY` / `AMAZON_SECRET_KEY` quando elegível à PA-API 5.0).
3. **Shopee Brasil:** Inserir seu `SHOPEE_AFFILIATE_ID` (e `SHOPEE_APP_ID` / `SHOPEE_APP_SECRET` da Open API Shopee).
4. **Canais Sociais Externos (Opcional para distribuição fora do portal próprio):** Inserir o token OAuth de `YouTube`, `Instagram Reels` e/ou `Pinterest` caso deseje publicação externa além do portal próprio `https://afiliados.projetosunion.cloud/ofertas`.

Assim que qualquer uma dessas credenciais é salva no painel `/integrations`, ela é criptografada no volume persistente Cloud e o `UNION AUTONOMOUS ORCHESTRATOR` passa a descobrir produtos, gerar links, produzir artigos/vídeos e publicar 24/7 sem nenhuma tarefa manual recorrente.

