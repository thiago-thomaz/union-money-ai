# UNION MONEY AI — FASE 5.1: AUTONOMIA CLOUD DEFINITIVA E VALIDAÇÃO COMERCIAL

**Data da Auditoria e Validação:** `2026-11-10`  
**URL Oficial em Produção (HTTPS):** `https://afiliados.projetosunion.cloud`  
**Repositório GitHub:** `https://github.com/thiago-thomaz/union-money-ai` (`branch: main`)  
**Infraestrutura Cloud:** VPS Linux (`72.62.13.62`) gerenciada via Coolify (`App UUID: q8xnbh2ncefepqe6nhpqsgju`)

---

## 1. RESPOSTAS DIRETAS ÀS 8 PERGUNTAS OBRIGATÓRIAS (ETAPA 7)

### 1.1. O sistema depende do computador local?
**NÃO (`depends_on_local_pc: false`).**  
Toda a execução da aplicação web FastAPI, do portal público `UNION OFERTAS` (`/ofertas`), do `UNION AUTONOMOUS ORCHESTRATOR` (APScheduler + fila persistente `PersistentOrchestratorQueue`), da geração de vídeos/imagens (FFmpeg + Pillow) e das rotinas de backup ocorre exclusivamente nos containers Linux da VPS (`72.62.13.62`). O computador Windows e o Antigravity podem permanecer 100% desligados sem qualquer impacto na operação.

### 1.2. O deploy automático funciona?
**SIM — COMPROVADO POR TESTE CONTROLADO DE PUSH SEM COMANDO MANUAL.**  
- **Webhook GitHub Configurado:** Hook ID `709965809` ativo em `thiago-thomaz/union-money-ai` apontando para `http://72.62.13.62:8000/webhooks/source/github/events/manual` (`events: ["push"]`).
- **Evidência Real de Push-Deploy Automático (Etapa 1 e Etapa 6):**
  - Commit enviado ao GitHub (`git push origin main`): `e312ec073292febb038c1a8ab4c420e66c650c9b`
  - Deployment iniciado automaticamente pelo Coolify via Webhook: `ez2gzz6d92jrpo7rnysfdow3` (`is_webhook: true`, `is_api: false`, `status: "finished"`)
  - Pipeline executada na nuvem: Build Docker (`python:3.11-slim` + FFmpeg + SQLite3) $\rightarrow$ `scripts/cloud_entrypoint.py` (migrações seguras + verificação de integridade SQLite WAL + backup preventivo + health gate) $\rightarrow$ Healthcheck HTTP interno (`GET http://localhost:8000/health` $\rightarrow$ `healthy`) $\rightarrow$ Rolling Update concluído sem downtime.
  - Em caso de falha nos critérios críticos de saúde pós-deploy, `CloudDeployRegistry.verify_post_deploy_and_register()` aciona rollback automático restaurando o snapshot pré-deploy de `/app/backups`.

### 1.3. Os dados persistem após reinício?
**SIM — COMPROVADO POR TESTE REAL DE REINICIALIZAÇÃO DE CONTAINER.**  
- **4 Volumes Docker Persistentes Montados no Host da VPS:**
  1. `/app/data` (`q8xnbh2ncefepqe6nhpqsgju-sqlite-data`) — Banco SQLite3 em modo `WAL` (`union_money.db`).
  2. `/app/storage` (`q8xnbh2ncefepqe6nhpqsgju-media-storage`) — Vídeos MP4 (`9:16` e `16:9`), legendas `.srt`, thumbnails, infográficos e relatórios PDF.
  3. `/app/logs` (`q8xnbh2ncefepqe6nhpqsgju-app-logs`) — Logs estruturados de auditoria e execução.
  4. `/app/backups` (`q8xnbh2ncefepqe6nhpqsgju-union-money-ai-backups`, UUID `sese7kl6lgmbu903lr8ymqhx`) — Volume dedicado e fisicamente separado de `/app/data` para snapshots `.db` verificados via SHA-256 e `PRAGMA integrity_check`.
- **Teste de Reinicialização e Liderança (`deployment_uuid: fhfskd93eg9u91oae0thglmd`):**
  - O container foi reiniciado na VPS. Durante a janela de transição entre o container antigo (`c3db90411bc5:pid-1`) e o novo (`023d14b9c790:pid-1`), o `SchedulerLeaderLock` bloqueou execução duplicada (`duplicate_scheduler_prevented: true`) e, após a expiração do lease anterior, transferiu automaticamente a liderança (`is_leader: true`, `leader_id: "023d14b9c790:pid-1"`), preservando 100% do histórico de deploys, configurações criptografadas e backups em `/app/backups`.

### 1.4. O scheduler roda na nuvem?
**SIM (`scheduler_running: true`, `status: ACTIVE`).**  
O `UNION AUTONOMOUS ORCHESTRATOR` e o `UNION AUTOPILOT` iniciam automaticamente no lifespan do container em produção e no `scripts/cloud_entrypoint.py`, protegidos por eleição de líder (`SchedulerLeaderLock`) e chaves de idempotência (`idempotency_key`) para impedir tarefas duplicadas. Jobs interrompidos em estado `RUNNING` por reinício de container são automaticamente recuperados por `CloudTaskWorker.recover_stalled_jobs()` com backoff exponencial.

### 1.5. Quais integrações estão conectadas?
Auditoria em tempo real via `GET https://afiliados.projetosunion.cloud/api/integrations/phase5-audit` (utilizando exclusivamente os 4 estados permitidos):

| Plataforma / Canal | Estado Atual em Produção | Detalhamento Técnico Real |
| :--- | :--- | :--- |
| **Portal UNION OFERTAS (`/ofertas`)** | `REALMENTE CONECTADO` | Motor nativo FastAPI + Jinja2 + Sitemap XML + Schema.org JSON-LD + Shortlinks `/r/{code}` operando 24/7 na nuvem. |
| **Mercado Livre Brasil** | `CREDENCIAIS AUSENTES` | Conector OAuth 2.0 (`exchange_oauth_code` + auto-refresh) e busca `/sites/MLB/search` prontos; aguarda `ML_AFFILIATE_TAG` / `ML_CLIENT_ID` em `/integrations`. |
| **Amazon Brasil (Associados)** | `CREDENCIAIS AUSENTES` | Assinatura AWS SigV4 (`AWS4-HMAC-SHA256`) para PA-API 5.0 e gerador `/dp/{ASIN}?tag=` prontos; subfunção de relatório REST de comissões classificada como `API NÃO DISPONÍVEL` (limitação oficial da Amazon Brasil, suprida por leitor OAuth de e-mail ou CSV oficial). |
| **Shopee Brasil (Open API)** | `CREDENCIAIS AUSENTES` | Cliente GraphQL (`productOfferV2`, `generateShortLink`, `conversionReport`) com assinatura `SHA256` pronto; aguarda `SHOPEE_AFFILIATE_ID` / `SHOPEE_APP_ID` em `/integrations`. |
| **YouTube / Instagram / Pinterest** | `CREDENCIAIS AUSENTES` | Clientes REST oficiais prontos; enquanto não autorizados, o sistema prioriza automaticamente o portal próprio `UNION OFERTAS` sem exigir downloads ou uploads manuais. |
| **Google Search Console / GA4** | `CREDENCIAIS AUSENTES` | Opcionais; o rastreamento interno de visitantes e cliques válidos anti-bot já opera nativamente no banco SQLite WAL. |

### 1.6. Quantos produtos reais foram descobertos?
**`0` produtos comerciais reais no banco de produção (`real_active_products: 0`)** até que ao menos uma credencial/tag de marketplace seja inserida em `https://afiliados.projetosunion.cloud/integrations`.  
- O sistema **não fabrica produtos fictícios** no banco de produção.
- No teste automatizado de integração em banco temporário isolado (`POST /api/cloud/verify-integration-flow`), o pipeline completo descobre, pontua (`score: 70.41`), gera link de afiliado válido (`/r/PiymY40u`), produz artigo + vídeo e publica sem poluir o banco comercial de produção (`isolated_from_production_db: true`).

### 1.7. Quantas publicações reais foram feitas?
**`0` publicações comerciais em produção (`portal_publications: 0`)** enquanto `real_active_products == 0`.  
- Assim que a primeira tag/credencial de afiliado for salva em `/integrations`, o ciclo imediato (`trigger_immediate_cycle: true`) descobre oportunidades e publica automaticamente no portal público `https://afiliados.projetosunion.cloud/ofertas` sem intervenção humana.

### 1.8. Qual é a receita real confirmada?
**`R$ 0,00` (`confirmed_revenue_brl: 0.0`, `cash_received_brl: 0.0`, `confirmed_real_conversions: 0`).**  
- Conforme auditado na **Etapa 5 (Auditoria Financeira Real)** em [`cashflow.py`](file:///c:/Users/Thiago%20Thomaz/OneDrive/Documentos/AntiGravity%20-%20Projetos/2027/Afiliados%20projeto%20milionario/union_money_ai/app/finance/cashflow.py), [`union_finance_ai.py`](file:///c:/Users/Thiago%20Thomaz/OneDrive/Documentos/AntiGravity%20-%20Projetos/2027/Afiliados%20projeto%20milionario/union_money_ai/app/finance/union_finance_ai.py) e [`reporting_service.py`](file:///c:/Users/Thiago%20Thomaz/OneDrive/Documentos/AntiGravity%20-%20Projetos/2027/Afiliados%20projeto%20milionario/union_money_ai/app/services/reporting_service.py), há separação estrita no banco e na API (`strict_financial_separation`) entre:
  1. **Dados sintéticos/teste (`test_synthetic_data_brl`)** — jamais contabilizados como venda real ou receita recebida (`test_synthetic_included_in_revenue: false`).
  2. **Conversões pendentes (`pending_conversions_count`)** — aguardando confirmação da plataforma.
  3. **Conversões aprovadas (`approved_conversions_count`)** — confirmadas pela plataforma.
  4. **Comissões estimadas (`estimated_commissions_brl`)** — potencial calculado sobre o catálogo ativo.
  5. **Comissões confirmadas (`confirmed_commissions_brl`)** — status `APPROVED` aguardando repasse bancário.
  6. **Valores efetivamente pagos (`effectively_paid_brl` / `cash_received_brl`)** — exclusivamente comissões reais com status `PAID`.

---

## 2. MATRIZ CLARA: O QUE DEPENDE DO PROPRIETÁRIO VS. APROVAÇÃO DAS PLATAFORMAS (ETAPA 3)

### 2.1. O que depende exclusivamente da autorização inicial única do proprietário (em `https://afiliados.projetosunion.cloud/integrations`)
1. **Amazon Brasil (Ativação Imediata de Links):**
   - Informar `AMAZON_PARTNER_TAG` (ex.: `seutag-20`) no formulário seguro de `/integrations`. Isso ativa imediatamente a geração de links canônicos `https://www.amazon.com.br/dp/{ASIN}?tag={AMAZON_PARTNER_TAG}`.
2. **Shopee Brasil (Ativação Imediata de Links):**
   - Informar `SHOPEE_AFFILIATE_ID` em `/integrations` para parametzação imediata de ofertas da Shopee.
3. **Mercado Livre Brasil:**
   - Informar `ML_AFFILIATE_TAG`, `ML_CLIENT_ID` e `ML_CLIENT_SECRET` em `/integrations` e clicar uma única vez em **Autorizar OAuth 2.0** (`https://afiliados.projetosunion.cloud/api/connect/oauth/callback/mercadolivre`).
4. **Canais Sociais (Opcional — Portal `UNION OFERTAS` já está ativo):**
   - Autorizar OAuth 2.0 para YouTube (`YOUTUBE_CLIENT_ID`/`SECRET`), Instagram Graph API (`INSTAGRAM_ACCESS_TOKEN`) e Pinterest API v5 (`PINTEREST_ACCESS_TOKEN`) caso deseje distribuição social além do portal próprio `/ofertas`.

### 2.2. O que depende de aprovação externa das plataformas (Regras Oficiais de Terceiros)
1. **Amazon Product Advertising API 5.0 (`AMAZON_ACCESS_KEY` e `AMAZON_SECRET_KEY`):**
   - A Amazon Brasil exige contratualmente **3 vendas qualificadas nos primeiros 180 dias** no Programa de Associados para liberar acesso às chaves da PA-API 5.0.
   - A Amazon Brasil **não disponibiliza API REST pública** para relatórios de comissões (`API NÃO DISPONÍVEL`); o sistema contorna isso legitimamente via leitor OAuth de e-mails de confirmação ou importação de CSV oficial.
2. **Shopee Affiliate Open API (`SHOPEE_APP_ID` e `SHOPEE_APP_SECRET`):**
   - Exige aprovação da conta no Programa de Afiliados Shopee Brasil e liberação de acesso à Open API GraphQL no painel `https://affiliate.shopee.com.br/open_api`.
3. **Meta / Google / Pinterest Developer Apps:**
   - Exigem aprovação dos respectivos aplicativos nas plataformas de desenvolvedor para escopos de publicação direta (`instagram_content_publish`, `youtube.upload`, `pins:write`).

---

## 3. RESULTADO DA SUÍTE DE TESTES OPERACIONAIS (ETAPA 6)

- **Suíte Automatizada Completa (`pytest -v`):** **`40 passed, 0 failed, 0 errors`** em `93.10s`.
- **Teste de Integração End-to-End Isolado (`POST /api/cloud/verify-integration-flow`):** **`all_8_stages_passed: true`**, `isolated_from_production_db: true`, `fabricated_conversions_count: 0`.
- **Teste de Ciclo de Backup e Restauração (`POST /api/cloud/backup/verify-cycle`):** **`backup_verified: true`**, `is_separate_from_primary_data_dir: true` (`/app/backups` separado de `/app/data`), `restore_test_passed: true`.
- **Teste de Push-Deploy Automático GitHub $\rightarrow$ Coolify:** Commit `e312ec073292febb038c1a8ab4c420e66c650c9b` $\rightarrow$ Deployment `ez2gzz6d92jrpo7rnysfdow3` (`is_webhook: true`, `is_api: false`, `status: finished`).
- **Teste de Reinicialização e Persistência de Container:** Deployment `fhfskd93eg9u91oae0thglmd` (`status: finished`) com preservação integral do banco SQLite WAL, histórico de deploys, backups e transição limpa do `SchedulerLeaderLock` para `023d14b9c790:pid-1`.
