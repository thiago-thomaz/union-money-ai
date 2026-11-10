# UNION MONEY AI — AUDITORIA TÉCNICA, FUNCIONAL, FINANCEIRA E DE SEGURANÇA FINAL

**Data da Auditoria:** 2026-11-06  
**Versão do Sistema:** 1.0.0  
**Escopo Auditado:** Partes 1, 2 e 3 (`UNION MONEY AI`, `UNION AUTOPILOT`, `UNION CONTENT ENGINE`, `UNION VIDEO ENGINE`, `UNION SEO ENGINE`, `UNION OFERTAS`, `UNION LINK MANAGER`, `UNION DISTRIBUTION ENGINE`, `UNION FINANCE AI`, `UNION WEALTH SIMULATOR`, `UNION GROWTH MANAGER`, Segurança, Conformidade, LGPD e Escala).

---

## 1. Visão Geral do Sistema
O **UNION MONEY AI** é um sistema comercial autônomo de marketing de afiliados construído integralmente em Python (`FastAPI`, `SQLAlchemy`, `SQLite/PostgreSQL`, `Pydantic`, `Jinja2`, `APScheduler`, `HTTPX`, `Pillow`, `FFmpeg`, `ReportLab`, `Bcrypt`, `Pytest`), sem qualquer dependência de `n8n` ou de APIs de IA pagas. O sistema opera em ciclo fechado:
1. Descoberta e avaliação quantitativa de oportunidades comerciais (`ProductOpportunityScorer`, 0–100).
2. Produção editorial multimídia em 13 formatos (`UnionContentEngine` + `ContentQualityScorer` + `UnionVideoEngine` em 9:16, 16:9 e 1:1 com legendas `.srt`).
3. Distribuição orgânica no portal público próprio (`UNION OFERTAS` em `/ofertas`) e preparação de pacotes para canais externos.
4. Gestão de links rastreáveis com proteção anti-bot/anti-fraude (`UnionLinkManager`).
5. Controle financeiro de 5 estágios de comissão, conciliação e importação CSV (`UnionFinanceAI`), simulação matemática de metas (`UnionWealthSimulator`) e recomendação de reinvestimento (`UnionGrowthManager`).

---

## 2. Estrutura de Diretórios
```text
union_money_ai/
├── app/
│   ├── __init__.py
│   ├── __main__.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── dependencies.py
│   ├── core/
│   │   ├── compliance.py
│   │   ├── emergency.py
│   │   ├── exceptions.py
│   │   ├── logging.py
│   │   ├── monitoring.py
│   │   ├── privacy_lgpd.py
│   │   ├── scheduler.py
│   │   └── security.py
│   ├── models/
│   │   ├── affiliate.py
│   │   ├── audit.py
│   │   ├── autopilot.py
│   │   ├── campaign.py
│   │   ├── click.py
│   │   ├── commission.py
│   │   ├── compliance.py
│   │   ├── content.py
│   │   ├── conversion.py
│   │   ├── financial.py
│   │   ├── marketplace.py
│   │   ├── product.py
│   │   ├── publication.py
│   │   └── user.py
│   ├── intelligence/
│   │   ├── demand.py
│   │   ├── discovery.py
│   │   ├── niche_analyzer.py
│   │   ├── opportunity.py
│   │   ├── pricing.py
│   │   ├── recommendation.py
│   │   └── scoring.py
│   ├── connectors/
│   │   ├── amazon.py
│   │   ├── base.py
│   │   ├── manual_import.py
│   │   ├── mercadolivre.py
│   │   └── shopee.py
│   ├── content_engine/
│   │   ├── ai_providers.py
│   │   ├── articles.py
│   │   ├── captions.py
│   │   ├── copywriting.py
│   │   ├── quality.py
│   │   ├── scripts.py
│   │   ├── seo.py
│   │   ├── thumbnails.py
│   │   ├── union_content_engine.py
│   │   └── video.py
│   ├── marketing/
│   │   ├── analytics.py
│   │   ├── campaign_manager.py
│   │   ├── distribution.py
│   │   ├── email.py
│   │   ├── landing_pages.py
│   │   └── link_manager.py
│   ├── finance/
│   │   ├── cashflow.py
│   │   ├── commissions.py
│   │   ├── expenses.py
│   │   ├── growth_manager.py
│   │   ├── projections.py
│   │   ├── revenue.py
│   │   ├── roi.py
│   │   ├── union_finance_ai.py
│   │   └── wealth_simulator.py
│   ├── automation/
│   │   ├── autonomy.py
│   │   ├── autopilot.py
│   │   ├── content_jobs.py
│   │   ├── discovery_jobs.py
│   │   ├── financial_jobs.py
│   │   ├── monitoring_jobs.py
│   │   └── publication_jobs.py
│   ├── services/
│   │   ├── affiliate_service.py
│   │   ├── campaign_service.py
│   │   ├── content_service.py
│   │   ├── finance_service.py
│   │   ├── product_service.py
│   │   └── reporting_service.py
│   ├── api/routes/
│   │   ├── autopilot.py
│   │   ├── campaigns.py
│   │   ├── content.py
│   │   ├── dashboard.py
│   │   ├── finance.py
│   │   ├── integrations.py
│   │   ├── opportunities.py
│   │   ├── products.py
│   │   ├── publications.py
│   │   ├── security_compliance.py
│   │   ├── settings.py
│   │   └── site.py
│   ├── templates/
│   └── static/
├── migrations/
│   └── migration_runner.py
├── scripts/
│   ├── backup_db.py
│   ├── init_database.py
│   ├── restore_db.py
│   └── seed_synthetic_test_data.py
└── tests/
```

---

## 3. Módulos Implementados
- **Inteligência Comercial (`app/intelligence/`)**: `ProductOpportunityScorer` (8 dimensões configuráveis somando 100 pontos), `CommercialLearningEngine` (aprendizado por dados históricos reais + modo inicial `REGRA_INICIAL_SEM_HISTORICO`) e motor de Testes A/B (`Experiment`, `ExperimentVariant`).
- **Conectores (`app/connectors/`)**: Adaptadores para Mercado Livre, Amazon Brasil e Shopee Brasil com rate limiting por domínio, cache em memória, geração de links de afiliado, importação manual/CSV/JSON e transparência de credenciais.
- **Orquestrador (`app/automation/autopilot.py` & `autonomy.py`)**: `UnionAutopilot` com lock de concorrência, idempotência (`idempotency_key`), retry com backoff exponencial, timeout, recuperação pós-reinicialização (`RECOVERED`), `AutonomyManager` (Níveis 1, 2 e 3 + 7 travas humanas obrigatórias) e `OperationalRoutineManager` (rotinas de 6h, diária, semanal e mensal).
- **Motores de Conteúdo, Vídeo e SEO (`app/content_engine/`)**: `UnionContentEngine` (13 formatos editoriais), `ContentQualityScorer` (bloqueia publicação automática se nota < 70), `AIProviderRouter` (`NativePythonProvider` -> `LocalLLMProvider` -> `OptionalExternalProvider`), `UnionVideoEngine` (MP4 H.264 9:16, 16:9, 1:1 + `.srt`) e `UnionSEOEngine` (slugs, JSON-LD `Product`/`Article`/`FAQPage`, `sitemap.xml`, `robots.txt`).
- **Portal Público e Distribuição (`app/api/routes/site.py`, `app/marketing/`)**: Portal `UNION OFERTAS` (`/ofertas`), `UnionLinkManager` (`/r/{code}`), `UnionDistributionEngine` (fila editorial com 7 estados: `RASCUNHO`, `EM_REVISAO`, `APROVADO`, `AGENDADO`, `PUBLICADO`, `FALHOU`, `ARQUIVADO`).
- **Central Financeira (`app/finance/`)**: `UnionFinanceAI`, `UnionWealthSimulator` e `UnionGrowthManager`.
- **Segurança, Conformidade e LGPD (`app/core/`)**: `security.py`, `emergency.py`, `compliance.py` e `privacy_lgpd.py`.

---

## 4. Banco de Dados e Tabelas (24 Tabelas Relacionais)
1. `users` (`User`)
2. `marketplaces` (`Marketplace`)
3. `categories` (`Category`)
4. `affiliate_accounts` (`AffiliateAccount`)
5. `affiliate_links` (`AffiliateLink`)
6. `products` (`Product`)
7. `campaigns` (`Campaign`)
8. `experiments` (`Experiment`)
9. `experiment_variants` (`ExperimentVariant`)
10. `contents` (`ContentItem`)
11. `publications` (`Publication`)
12. `visitor_aggregates` (`VisitorAggregate`)
13. `clicks` (`ClickLog`)
14. `conversions` (`Conversion`)
15. `commissions` (`Commission`)
16. `revenues` (`RevenueRecord`)
17. `expenses` (`Expense`)
18. `financial_history` (`FinancialHistory`)
19. `system_logs` (`SystemLog`)
20. `audit_logs` (`AuditLog`)
21. `system_settings` (`SystemSetting`)
22. `autopilot_task_runs` (`AutopilotTaskRun`)
23. `editorial_queue` (`EditorialQueueItem`)
24. `system_alerts` (`SystemAlert`)
25. `compliance_policies` (`CompliancePolicyRecord`)
26. `lgpd_consents` (`ConsentRecord`)
27. `security_incidents` (`SecurityIncident`)
28. `backup_records` (`BackupRecord`)

---

## 5. Rotas e Endpoints Principais
- **Painel e Operação**: `GET /`, `GET /api/dashboard/summary`, `GET /autopilot`, `POST /api/autopilot/run-cycle`, `GET /health`
- **Produtos e Inteligência**: `GET /products`, `POST /api/products`, `GET /opportunities`, `GET /api/opportunities/ranking`, `GET /api/opportunities/learning`
- **Conteúdo, Vídeo e SEO**: `GET /content`, `POST /api/content/engine/produce`, `POST /api/content/video/render`, `GET /sitemap.xml`, `GET /robots.txt`
- **Portal Público (`UNION OFERTAS`)**: `GET /ofertas`, `GET /ofertas/categorias/{slug}`, `GET /ofertas/recomendados`, `GET /ofertas/comparativos`, `GET /ofertas/guias`, `GET /ofertas/artigos/{slug}`, `GET /ofertas/produto/{id}`, `GET /ofertas/privacidade`, `GET /ofertas/termos`, `GET /ofertas/transparencia`, `GET /ofertas/aviso-afiliados`, `GET /r/{tracking_code}`
- **Central Financeira (`UNION FINANCE AI`)**: `GET /finance`, `GET /api/finance/indicators`, `POST /api/finance/import-csv`, `POST /api/finance/reconcile`, `GET /api/finance/wealth-simulator`, `POST /api/finance/wealth-simulator`, `GET /api/finance/growth-manager`, `PUT /api/finance/growth-manager/weights`
- **Segurança, Conformidade, LGPD e Autonomia**: `POST /api/security/stop-all-automations`, `POST /api/security/resume-automations`, `POST /api/security/integrations/{slug}/disable`, `GET /api/compliance/checklist`, `PUT /api/compliance/checklist/{slug}`, `POST /api/lgpd/consent`, `DELETE /api/lgpd/subject/{identifier}`, `POST /api/lgpd/incidents`, `GET /api/autonomy/config`, `PUT /api/autonomy/config`, `POST /api/autonomy/evaluate`, `POST /api/autonomy/routines/{period}/run`, `POST /api/settings/backup`, `POST /api/settings/restore`

---

## 6. Motores de IA e Geração
- **`NativePythonProvider` (Ativo por padrão, 100% gratuito e local)**: Gera 13 formatos editoriais estruturados com base exclusivamente nos dados verificados do produto, sem inventar especificações ou afirmar testes físicos inexistentes.
- **`LocalLLMProvider` (Opcional)**: Conecta a servidor local compatível (ex.: Ollama em `127.0.0.1:11434`) somente após verificar disponibilidade de RAM (`psutil`) e resposta do endpoint, fazendo fallback transparente para `NativePythonProvider` se offline.
- **`OptionalExternalProvider` (Opcional)**: Desativado por padrão; nunca bloqueia a operação quando sem credenciais.

---

## 7. Canais de Distribuição
- **Canal Próprio (`SITE` — Portal `UNION OFERTAS`)**: **APROVADA** e 100% operacional localmente.
- **Canais Externos (`youtube`, `instagram`, `pinterest`)**: Marcados como **PENDENTE** enquanto não houver credenciais de API configuradas no `.env`. O `UnionDistributionEngine` gera pacotes completos prontos para publicação (`storage/distribution_packages/`) sem fingir postagem externa.

---

## 8. Marketplaces Suportados
1. **Mercado Livre (`mercadolivre`)**: Geração de links afiliados parametrizados, importação manual/CSV oficial e conector para API oficial (status `PENDENTE` até inserção de `MERCADOLIVRE_APP_ID` e `MERCADOLIVRE_CLIENT_SECRET`).
2. **Amazon Brasil (`amazon`)**: Inserção automática de `tag` de Associado e aviso obrigatório da Amazon, importação CSV/manual e estrutura PA-API 5.0 (status `PENDENTE` até inserção de `AMAZON_ACCESS_KEY`, `AMAZON_SECRET_KEY` e `AMAZON_PARTNER_TAG`).
3. **Shopee Brasil (`shopee`)**: Geração de deep links com `sub_id`, importação CSV/manual e conector para API de Afiliados (status `PENDENTE` até inserção de `SHOPEE_APP_ID` e `SHOPEE_SECRET`).

---

## 9. Camada Financeira (`UNION FINANCE AI`, `WEALTH SIMULATOR`, `GROWTH MANAGER`)
- **Separação Obrigatória de 5 Estágios**:
  1. `POTENTIAL` (Comissão potencial/estimada)
  2. `ATTRIBUTED` / `PENDING` (Comissão atribuída pendente)
  3. `APPROVED` (Comissão aprovada aguardando pagamento)
  4. `CANCELLED` (Comissão cancelada)
  5. `PAID` (Comissão efetivamente paga — **única que entra em `cash_received_brl`**)
- **Importação CSV Oficial e Conciliação**: Valida cabeçalhos, datas, valores numéricos, status e identificadores; ignora duplicatas exatas e concilia automaticamente mudanças de status (`PENDING` -> `APPROVED` -> `PAID`).
- **Simulador de Crescimento (`UNION WEALTH SIMULATOR`)**: Separa Meta A (R$ 1.000.000 de Patrimônio Acumulado) e Meta B (R$ 1.000.000 de Receita Bruta Acumulada), projeta 12, 24, 36 e 60 meses nos cenários Conservador, Moderado e Agressivo sem crescimento exponencial irrestrito, e compara com o realizado.
- **Motor de Reinvestimento (`UNION GROWTH MANAGER`)**: Recomenda distribuição em 7 categorias exclusivamente sobre o caixa líquido recebido (`PAID`), com `auto_spend_allowed = False` e `human_approval_required = True`.

---

## 10. Segurança e Privacidade (LGPD)
- Hash de senhas com `bcrypt`; tokens de sessão assinados com `HMAC-SHA256`; tokens `CSRF` verificados; sanitização contra `XSS`; prevenção de `SQL Injection` via SQLAlchemy ORM + validação de padrões; `EndpointRateLimiter` em rotas sensíveis; varredura de código confirmando `0` segredos hardcoded.
- Botão global de emergência **`STOP ALL AUTOMATIONS`**: suspende o agendador, move publicações pendentes para `EM_REVISAO`, preserva 100% dos dados, mantém o painel acessível e grava `AuditLog`.
- Conformidade LGPD: hash anonimizado de visitantes, registro explícito de consentimento (`ConsentRecord`), exclusão completa de dados pessoais (`DELETE /api/lgpd/subject/{identifier}`), expurgo por prazo de retenção e registro de incidentes (`SecurityIncident`).

---

## 11. Testes Executados e Resultados
- **Verificação de sintaxe (`python -m compileall`)**: 100% dos módulos compilados sem erros.
- **Suíte automatizada (`python -m pytest -v`)**: **26/26 testes aprovados (100% PASS)** cobrindo:
  - `tests/test_models_and_db.py`
  - `tests/test_dashboard_zero_fake_data.py`
  - `tests/test_scoring_engine.py`
  - `tests/test_connectors.py`
  - `tests/test_api_and_crud.py`
  - `tests/test_learning_and_ab.py`
  - `tests/test_reporting_and_backup.py`
  - `tests/test_part2_autopilot_and_engines.py`
  - `tests/test_part2_site_and_distribution.py`
  - `tests/test_part3_finance_security_scale.py` (Grupos A–I da Parte 3)

---

## 12. Limitações Atuais
- As APIs externas dos marketplaces (Mercado Livre, Amazon PA-API 5.0, Shopee Open API) e das redes sociais (YouTube, Instagram, Pinterest) exigem credenciais comerciais próprias do operador no arquivo `.env`. Enquanto não configuradas, operam de forma transparente via importação oficial CSV/manual e pacotes de publicação assistida.
- A narração em áudio nos vídeos MP4 utiliza trilha limpa ou TTS quando disponível localmente; os vídeos já incluem legendas sincronizadas `.srt` e quadros visuais completos renderizados via `Pillow` + `FFmpeg`.

---

## 13. Credenciais Opcionais Pendentes (`.env`)
- `MERCADOLIVRE_APP_ID`, `MERCADOLIVRE_CLIENT_SECRET`, `MERCADOLIVRE_AFFILIATE_TAG`
- `AMAZON_ACCESS_KEY`, `AMAZON_SECRET_KEY`, `AMAZON_PARTNER_TAG`
- `SHOPEE_APP_ID`, `SHOPEE_SECRET`, `SHOPEE_AFFILIATE_ID`
- `LOCAL_LLM_ENDPOINT`, `LOCAL_LLM_MODEL` (opcional, para LLM local como Ollama)

---

## 14. Como Iniciar o Sistema
```bash
cd union_money_ai
python -m scripts.init_database
python -m app.main
```
Acesse `http://127.0.0.1:8000` (Painel Administrativo) e `http://127.0.0.1:8000/ofertas` (Portal Público `UNION OFERTAS`).

---

## 15. Como Fazer Backup e Restaurar
- **Backup**: `python -m scripts.backup_db` (gera `.db` consistente via `sqlite3.backup`, valida `PRAGMA integrity_check` + `SHA-256`, e exporta configurações sem segredos e manifesto de conteúdos em `data/backups/`).
- **Restauração**: `python -m scripts.restore_db data/backups/<arquivo_backup.db>` (verifica `PRAGMA integrity_check` e `SHA-256` antes de restaurar).

---

## 16. Como Operar no Dia a Dia
1. Cadastre produtos manualmente ou importe relatórios/catálogos em `/products` ou `/integrations`.
2. Execute o `UNION AUTOPILOT` em `/autopilot` (ou deixe as rotinas automáticas rodarem em Nível 2 Semiautomático para publicar no portal `/ofertas`).
3. Importe os relatórios CSV oficiais de comissões dos marketplaces em `/finance` para conciliar comissões `PENDING`, `APPROVED`, `CANCELLED` e `PAID`.
4. Consulte o `UNION WEALTH SIMULATOR` e o `UNION GROWTH MANAGER` em `/finance` para acompanhar o progresso real rumo a R$ 1.000.000 e as recomendações de alocação do caixa efetivamente pago.

---

## 17. Próximos Passos Recomendados para Escalar
1. Configurar as tags e credenciais oficiais de afiliado do Mercado Livre, Amazon Brasil e Shopee Brasil no arquivo `.env`.
2. Apontar um domínio próprio com HTTPS (via proxy reverso Nginx/Caddy) para o portal público `/ofertas` e submeter o `/sitemap.xml` ao Google Search Console.
3. Migrar `DATABASE_URL` de SQLite para PostgreSQL quando o volume de acessos simultâneos escalar.

