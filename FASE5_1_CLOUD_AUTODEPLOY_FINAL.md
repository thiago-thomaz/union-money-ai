# FASE 5.1 — CLOUD FIRST, DEPLOY AUTOMÁTICO E OPERAÇÃO CONTÍNUA 24/7
## PROJETO: UNION MONEY AI (`https://afiliados.projetosunion.cloud`)

---

## 1. Arquitetura Cloud Implementada (6 Componentes Separados)

O **UNION MONEY AI v5.1.0** opera 100% em infraestrutura Cloud permanente (VPS Linux + Docker + Coolify + Traefik Proxy com Let's Encrypt TLS), sem qualquer dependência do computador local ligado, terminal aberto ou Antigravity em execução.

| # | Componente | Implementação Técnica | Status em Produção |
| :--- | :--- | :--- | :--- |
| **1** | **Web / API** | FastAPI (`app.main:app`) + Portal Público `UNION OFERTAS` servido via Uvicorn e proxy reverso Traefik com HTTPS e certificado SSL Let's Encrypt automático. | `ONLINE` (`https://afiliados.projetosunion.cloud`) |
| **2** | **Scheduler** | APScheduler nativo acoplado ao `SchedulerLeaderLock` (`app/core/cloud_runtime.py`), utilizando trava distribuída com lease (`cloud_scheduler_leader_lock`) no banco para **impedir múltiplas instâncias concorrentes de agendarem tarefas duplicadas**. | `ACTIVE` (`leader_id: 5d66943bce3a:pid-1`, `duplicate_scheduler_prevented: true`) |
| **3** | **Worker** | `CloudTaskWorker` (`app/core/cloud_runtime.py`) + `PersistentOrchestratorQueue` (`app/models/autonomous.py`) com heartbeat contínuo, detecção automática de tarefas travadas (`RUNNING` além do timeout), recuperação com **backoff exponencial** e isolamento de falhas. | `ACTIVE` (`worker-5d66943bce3a-pid-1`) |
| **4** | **Database** | SQLite 3 em modo concorrente **WAL (`journal_mode=wal`)** e `synchronous=NORMAL`, isolado em volume Docker persistente dedicado (`/app/data`). | `HEALTHY` (`journal_mode: wal`, `/app/data`) |
| **5** | **Storage & Backups** | Volume persistente de mídias (`/app/storage`) e **volume persistente separado de backups (`/app/backups`)**, distinto de `/app/data`, com política de retenção (`BACKUP_RETENTION_COUNT=15`), verificação `PRAGMA integrity_check` + checksum `SHA-256` e teste automático de restauração não destrutivo. | `MOUNTED` (`/app/storage` e `/app/backups` separados, `backups_separate_from_data: true`) |
| **6** | **Monitoring** | `CloudAvailabilityMonitor` e `CloudDeployRegistry` monitorando HTTP `/health`, `/api/cloud/status`, uso de CPU, RAM, espaço livre em disco, logs centralizados e histórico auditável de deploys/rollbacks. | `ACTIVE` (CPU `10.0%`, RAM `32.6%`, Disco Livre `61.11 GB / 95.82 GB`) |

---

## 2. URL de Produção, Repositório e Branch Conectada

- **URL Pública de Produção (HTTPS):** `https://afiliados.projetosunion.cloud`
- **Portal Público de Ofertas:** `https://afiliados.projetosunion.cloud/ofertas`
- **Healthcheck Cloud:** `https://afiliados.projetosunion.cloud/health`
- **Diagnóstico de Arquitetura Cloud (Fase 5.1):** `https://afiliados.projetosunion.cloud/api/cloud/status`
- **Status do Líder do Scheduler:** `https://afiliados.projetosunion.cloud/api/cloud/leader`
- **Repositório GitHub Oficial:** `https://github.com/thiago-thomaz/union-money-ai`
- **Branch Conectada ao Deploy Automático:** `main`
- **Aplicação no Coolify:** `union-money-ai` (`uuid: q8xnbh2ncefepqe6nhpqsgju`, Servidor `localhost` / `s14duf5l3yrrn0xobdqs6zhu`)

---

## 3. Containers e Volumes Persistentes Configurados

### Container de Produção
- **Imagem Base:** `python:3.11-slim` com `ffmpeg`, `libsqlite3-dev`, `libpng-dev`, `libjpeg-dev`, `curl`.
- **Entrypoint Cloud-First:** `python -m scripts.cloud_entrypoint` (`scripts/cloud_entrypoint.py`), que executa:
  1. Migrações seguras e idempotentes do banco (`run_migrations()`).
  2. Eleição de líder do Scheduler (`SchedulerLeaderLock.acquire_or_renew_leadership`).
  3. Varredura e recuperação de jobs travados (`CloudTaskWorker.detect_and_recover_stalled_jobs`).
  4. Backup atômico no volume separado `/app/backups` + teste de restauração verificada (`CloudAvailabilityMonitor.run_separate_cloud_backup_and_test_restore`).
  5. Verificação crítica de saúde pós-deploy e registro de versão/commit (`CloudDeployRegistry.verify_post_deploy_and_rollback_if_unhealthy`).
  6. Inicialização do servidor ASGI `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- **Healthcheck Nativo Docker & Coolify:** `GET http://127.0.0.1:8000/health` (intervalo `30s`, timeout `10s`, start-period `15s`, retries `3`).

### 4 Volumes Persistentes Isolados no Coolify
1. **`q8xnbh2ncefepqe6nhpqsgju-union-money-ai-data`** (`uuid: txfnr7vv1gr7kypskfqrjax6`) -> montado em `/app/data` (Banco SQLite WAL principal).
2. **`q8xnbh2ncefepqe6nhpqsgju-union-money-ai-storage`** (`uuid: zdgzgpymsbku4jdksoqqq4pj`) -> montado em `/app/storage` (Vídeos MP4, thumbnails, infográficos, relatórios PDF e pacotes).
3. **`q8xnbh2ncefepqe6nhpqsgju-union-money-ai-logs`** (`uuid: hf7mputdgypfbha8leuimpl5`) -> montado em `/app/logs` (Logs operacionais e de auditoria).
4. **`q8xnbh2ncefepqe6nhpqsgju-union-money-ai-backups`** (`uuid: sese7kl6lgmbu903lr8ymqhx`) -> montado em `/app/backups` (**Volume exclusivo para backups**, fisicamente separado de `/app/data`).

---

## 4. Configuração de CI/CD e Deploy Automático (`GitHub -> Coolify`)

1. **GitHub Actions (`.github/workflows/ci_cd_cloud.yml`):**
   - Disparado automaticamente em cada `push` na branch `main`.
   - Instala dependências de sistema (`ffmpeg`, `sqlite3`, `libpng`, `libjpeg`) e Python (`requirements.txt`).
   - Executa o preflight Cloud (`python -m scripts.cloud_entrypoint --verify-only`) e a suíte completa `pytest -v` (37 testes automatizados).
   - Valida a saúde pós-deploy diretamente no domínio HTTPS `https://afiliados.projetosunion.cloud/health`.
2. **Webhook Automático GitHub -> Coolify (`Hook ID: 709965809`):**
   - Configurado no repositório `thiago-thomaz/union-money-ai` apontando para o endpoint de eventos GitHub do Coolify (`http://72.62.13.62:8000/webhooks/source/github/events/manual`) com assinatura HMAC secreta e `is_auto_deploy_enabled: true`.
   - Qualquer `git push origin main` inicia imediatamente o build, migração, healthcheck e rolling update no Coolify sem intervenção manual.

---

## 5. Resultado Real do Teste de Deploy Automático (Sem Ação Manual no Coolify)

- **Ação executada:** `git commit` e `git push origin main` do commit `c58107f82679abf74dd9bf06c2661e931fdabe1f`.
- **Evidência real auditada no Coolify (`deployment_uuid: tojte7qjvsdausoixqihcaj0`):**
  - `"commit": "c58107f82679abf74dd9bf06c2661e931fdabe1f"`
  - `"is_webhook": true` (disparado automaticamente pelo push no GitHub)
  - `"is_api": false` (nenhum comando manual de deploy foi chamado)
  - `"status": "finished"`
- **Logs reais do Rolling Update no Coolify:**
  ```text
  [2026-11-10T18:18:24.991561Z] Starting deployment of thiago-thomaz/union-money-ai:main to localhost.
  [2026-11-10T18:18:27.218573Z] Importing thiago-thomaz/union-money-ai:main (commit sha c58107f82679abf74dd9bf06c2661e931fdabe1f) to /artifacts/tojte7qjvsdausoixqihcaj0.
  [2026-11-10T18:20:54.345922Z] Building docker image completed.
  [2026-11-10T18:20:55.133383Z] Rolling update started.
  [2026-11-10T18:20:57.085992Z] New container started.
  [2026-11-10T18:20:57.178147Z] Healthcheck URL (inside the container): GET: http://localhost:8000/health
  [2026-11-10T18:21:12.609060Z] Attempt 1 of 3 | Healthcheck status: "healthy"
  [2026-11-10T18:21:12.653721Z] New container is healthy.
  [2026-11-10T18:21:18.064041Z] Removing old containers.
  [2026-11-10T18:21:19.643421Z] Rolling update completed.
  ```

---

## 6. Resultado do Teste de Independência do Computador Local

- A aplicação, o banco SQLite WAL (`/app/data`), o agendador (`APScheduler` com `SchedulerLeaderLock` no container `5d66943bce3a`) e o worker (`worker-5d66943bce3a-pid-1`) estão em execução diretamente no servidor Linux da VPS (`72.62.13.62`).
- Resposta ao vivo de `GET https://afiliados.projetosunion.cloud/health`:
  ```json
  {
    "status": "OK",
    "system": "UNION MONEY AI",
    "site": "UNION OFERTAS",
    "version": "5.1.0",
    "git_commit_sha": "production-cloud",
    "cloud_first": true,
    "depends_on_local_pc": false,
    "scheduler_running": true
  }
  ```
- O desligamento do computador local ou fechamento do Antigravity tem impacto **zero** sobre o site, redirecionador de cliques (`/r/{slug}`), agendador ou sincronização financeira.

---

## 7. Resultado dos Testes de Recuperação, Rollback Automático e Backup/Restauração

- **Suíte Automatizada Completa (`pytest -v`):**
  - **Total:** `37 passed, 0 failed, 0 skipped, 0 errors` (100% de aprovação).
- **Testes Específicos da Fase 5.1 (`tests/test_part5_1_cloud_autodeploy.py`):**
  1. `test_scheduler_leader_lock_prevents_duplicate_instances`: **PASSED** — comprova que uma segunda instância concorrente (`cloud-scheduler-node-B`) é bloqueada enquanto o líder (`cloud-scheduler-node-A`) detém o lease ativo.
  2. `test_cloud_task_worker_detects_and_recovers_stalled_jobs_with_exponential_backoff`: **PASSED** — comprova que tarefas travadas em `RUNNING` além do timeout são recuperadas com backoff exponencial (`status="RECOVERED"`) ou finalizadas como `FAILED` quando excedem `max_attempts`, além de recuperar `AutopilotTaskRun` travados (`RECOVERED_TIMEOUT`).
  3. `test_cloud_deploy_registry_post_deploy_verification_and_automatic_rollback`: **PASSED** — comprova o registro de versão saudável (`5.1.0`) e o **rollback automático** (`action="ROLLED_BACK_AUTOMATICALLY"`) para a última versão íntegra + geração de alerta crítico (`CLOUD_DEPLOY_ROLLBACK`) quando uma versão defeituosa (`5.1.1-broken`) falha nos critérios críticos de saúde.
  4. `test_cloud_availability_monitor_separate_backup_and_6_components_api`: **PASSED** — comprova a criação de backup no volume separado (`/app/backups`), validação `PRAGMA integrity_check=ok` + `SHA-256`, limpeza por política de retenção e **teste de restauração real** (`restore_test_passed: true`) em banco temporário isolado.

