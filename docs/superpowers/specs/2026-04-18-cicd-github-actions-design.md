# CI/CD GitHub Actions — ManutBR

**Data:** 2026-04-18
**Escopo:** Pipelines de CI/CD para os projetos `dbt` (ManutBR/) e `ingestion/`

---

## Contexto

O repositório ManutBR possui dois projetos independentes:

- **dbt (`ManutBR/`):** Modelos BigQuery com camadas staging, intermediate e marts.
- **ingestion (`ingestion/`):** Serviço Python containerizado que roda no Cloud Run.

Os pipelines devem validar mudanças em PRs (staging) e executar deploys ao fazer merge para `main` (produção).

---

## Fluxo de Branches

```
feature/develop  →  PR para main  →  merge (se checks passarem)
                         ↑
                   CI obrigatório
```

- Commits diretos em `main` são **bloqueados** via branch protection.
- Push em `feature/develop` dispara CI automaticamente.
- Merge para `main` só é liberado se todos os status checks passarem.

## Ambientes

| Ambiente | Trigger | Comportamento |
|----------|---------|---------------|
| Staging  | `push` em `feature/develop` / `pull_request` → `main` | Valida sem deploy real em produção |
| Produção | `push` → `main` (merge após PR aprovado) | Executa build/deploy completo |

---

## Workflow 1: `dbt-ci.yml`

### Triggers

```yaml
on:
  pull_request:
    branches: [main]
    paths:
      - "ManutBR/**"
      - "requirements.txt"
      - ".github/workflows/dbt-ci.yml"
  push:
    branches:
      - feature/develop
      - main
    paths:
      - "ManutBR/**"
      - "requirements.txt"
      - ".github/workflows/dbt-ci.yml"
```

### Job 1: `dbt-staging` (apenas em PRs)

**Condição:** `if: github.event_name == 'pull_request'`

**Passos:**
1. `actions/checkout@v4`
2. `actions/setup-python@v5` com Python 3.12 e cache pip
3. `pip install -r requirements.txt`
4. Gera `.dbt/profiles.yml` com dataset isolado: `ci_${GITHUB_SHA::7}` no BigQuery (target `ci`)
5. `dbt compile --project-dir ManutBR --profiles-dir .dbt`
6. `dbt build --project-dir ManutBR --profiles-dir .dbt` (modelos + testes)
7. Limpeza do dataset isolado via `bq rm -r -f <projeto>:ci_${GITHUB_SHA::7}` — executado em step separado com `if: always()` para garantir limpeza mesmo em falha

### Job 2: `dbt-prod` (apenas em push/merge para main)

**Condição:** `if: github.event_name == 'push' && github.ref == 'refs/heads/main'`

**Passos:**
1. `actions/checkout@v4`
2. `actions/setup-python@v5` com Python 3.12 e cache pip
3. `pip install -r requirements.txt`
4. Gera `.dbt/profiles.yml` apontando para dataset de produção (target `prod`)
5. `dbt build --project-dir ManutBR --profiles-dir .dbt`
6. Limpeza do dataset CI da PR mergeada: `bq rm -r -f <projeto>:ci_${GITHUB_SHA::7}` com `if: always()`
7. `dbt docs generate --project-dir ManutBR --profiles-dir .dbt`

### Secrets necessários

| Secret | Descrição |
|--------|-----------|
| `GCP_PROJECT_ID` | ID do projeto GCP |
| `GCP_SERVICE_ACCOUNT_JSON` | JSON da service account com acesso ao BigQuery |

---

## Workflow 2: `ingestion-ci.yml`

### Triggers

```yaml
on:
  pull_request:
    branches: [main]
    paths:
      - "ingestion/**"
      - ".github/workflows/ingestion-ci.yml"
  push:
    branches:
      - feature/develop
      - main
    paths:
      - "ingestion/**"
      - ".github/workflows/ingestion-ci.yml"
```

### Job 1: `validate` (PRs e push)

**Roda sempre** (tanto em PR quanto em merge).

**Passos:**
1. `actions/checkout@v4`
2. `actions/setup-python@v5` com Python 3.12 e cache pip
3. `pip install -r ingestion/requirements.txt ruff`
4. `ruff check ingestion/` — falha o pipeline se houver erros de lint
5. `docker build -t manutbr-ingestion:pr-test ingestion/` — valida build da imagem sem push

### Job 2: `deploy-prod` (apenas em push/merge para main)

**Condição:** `if: github.event_name == 'push' && github.ref == 'refs/heads/main'`
**Depende de:** `validate`

**Passos:**
1. `actions/checkout@v4`
2. `google-github-actions/auth@v2` com `GCP_SERVICE_ACCOUNT_JSON`
3. `google-github-actions/setup-gcloud@v2` — configura `gcloud` e Docker para `gcr.io`
4. `docker build -t gcr.io/$GCP_PROJECT_ID/manutbr-ingestion:$GITHUB_SHA ingestion/`
5. `docker push gcr.io/$GCP_PROJECT_ID/manutbr-ingestion:$GITHUB_SHA`
6. `docker tag ... :latest` + push da tag `:latest`
7. `google-github-actions/deploy-cloudrun@v2` — deploy no Cloud Run usando a imagem com tag `$GITHUB_SHA`

### Secrets necessários

| Secret | Descrição |
|--------|-----------|
| `GCP_PROJECT_ID` | ID do projeto GCP (mesmo do dbt) |
| `GCP_SERVICE_ACCOUNT_JSON` | JSON da service account com acesso ao GCR e Cloud Run |
| `CLOUD_RUN_SERVICE` | Nome do serviço Cloud Run (ex: `manutbr-ingestion`) |
| `CLOUD_RUN_REGION` | Região do Cloud Run (ex: `us-central1`) |

---

## Branch Protection (`main`)

Configurado via `gh` CLI após os workflows existirem no repositório:

```bash
# Bloqueia push direto em main e exige checks obrigatórios
gh api repos/ckoliveiraa/ManutBR/branches/main/protection \
  --method PUT \
  --field required_status_checks='{"strict":true,"contexts":["dbt lint, compile & test","Lint & test"]}' \
  --field enforce_admins=true \
  --field required_pull_request_reviews='{"required_approving_review_count":0}' \
  --field restrictions=null
```

**Checks obrigatórios** (nomes dos jobs nos workflows):
- `dbt lint, compile & test` — job `dbt-staging` do `dbt-ci.yml`
- `Lint & test` — job `validate` do `ingestion-ci.yml`

> Os checks só aparecem no GitHub após a primeira execução dos workflows. Rodar a branch protection somente depois disso.

---

## Decisões de Design

- **Branch protection bloqueando main:** Commits diretos são rejeitados; merge só ocorre após CI verde, garantindo que produção nunca receba código não validado.
- **CI em `feature/develop` e em PRs:** O push em `feature/develop` já roda a esteira, dando feedback rápido antes mesmo de abrir o PR.
- **Dois workflows independentes:** Cada projeto evolui sem afetar o outro. Logs de falha são claros e isolados.
- **Dataset isolado por PR (dbt):** Evita poluição do dataset de produção durante validação. Limpeza automática garante custo zero após o teste.
- **Staging sem deploy real (ingestion):** O build Docker valida o Dockerfile e dependências sem custo de infraestrutura para PRs.
- **Tag por SHA + latest:** Permite rastrear qual imagem está em produção e fazer rollback por SHA se necessário.
- **`if: always()` na limpeza dbt:** Garante que datasets temporários sejam removidos mesmo quando o pipeline falha.

---

## Secrets a configurar no GitHub

Todos os secrets são compartilhados entre os dois workflows. Configurar em **Settings → Secrets and variables → Actions**:

- `GCP_PROJECT_ID`
- `GCP_SERVICE_ACCOUNT_JSON`
- `CLOUD_RUN_SERVICE`
- `CLOUD_RUN_REGION`
