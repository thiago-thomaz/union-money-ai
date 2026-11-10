# UNION MONEY AI — Sistema Comercial Autônomo de Marketing de Afiliados

Sistema completo em Python (FastAPI + SQLAlchemy + SQLite/PostgreSQL + APScheduler + ReportLab + FFmpeg/Pillow) projetado para descoberta de oportunidades comerciais, produção editorial (`UNION CONTENT ENGINE` e `UNION VIDEO ENGINE`), portal público de afiliados (`UNION OFERTAS`), gestão financeira (`UNION FINANCE AI`, `UNION WEALTH SIMULATOR`, `UNION GROWTH MANAGER`), segurança, conformidade e governança autônoma (`UNION AUTOPILOT`).

---

## 1. Requisitos e Arquitetura

- **Linguagem principal**: Python 3.12+
- **Zero dependência de n8n**: 100% da orquestração e das rotinas (6h, diária, semanal, mensal) rodam nativamente via `APScheduler` e `UnionAutopilot`.
- **Zero serviços pagos obrigatórios**: Motor de conteúdo nativo (`NativePythonProvider`) com fallback automático para provedores locais/externos opcionais.
- **Integridade comercial e financeira**:
  - Não simula vendas nem comissões.
  - Não contabiliza cliques como vendas.
  - Separa obrigatoriamente comissões em 5 estágios: **Potencial**, **Atribuída (Pendente)**, **Aprovada**, **Cancelada** e **Efetivamente Paga (`PAID`)**.
  - Somente comissões com status `PAID` entram no **Caixa Recebido (`cash_received_brl`)**.

---

## 2. Instalação (Windows e Linux)

### Windows (PowerShell)
```powershell
cd union_money_ai
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m scripts.init_database
```

### Linux (Bash)
```bash
cd union_money_ai
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 -m scripts.init_database
```

---

## 3. Como Iniciar a Aplicação

Comando simples unificado (Windows ou Linux):
```bash
python -m app.main
```
Ou diretamente via Uvicorn:
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- **Painel Administrativo (`UNION MONEY AI`)**: `http://127.0.0.1:8000/`
- **Portal Público (`UNION OFERTAS`)**: `http://127.0.0.1:8000/ofertas`
- **Central Financeira (`UNION FINANCE AI`)**: `http://127.0.0.1:8000/finance`
- **Segurança, Conformidade, LGPD e Autonomia**: `http://127.0.0.1:8000/settings`
- **Healthcheck**: `http://127.0.0.1:8000/health`

---

## 4. Backup e Restauração

### Criar Backup Verificado (Banco SQLite + Configurações Sem Segredos + Manifesto de Conteúdos)
```bash
python -m scripts.backup_db
```

### Restaurar Backup com Validação de Integridade (`PRAGMA integrity_check` + SHA-256)
```bash
python -m scripts.restore_db data/backups/<nome_do_arquivo_backup.db>
```

---

## 5. Execução da Suíte Completa de Testes Automatizados

```bash
python -m pytest -v
```
