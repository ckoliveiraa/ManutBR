# Plano de Implementação — CI/CD GitHub Actions

**Spec de referência:** `2026-04-18-cicd-github-actions-design.md`
**Data:** 2026-04-18

---

## Pré-requisitos

Antes de iniciar, confirmar que existem no GitHub (Settings → Secrets and variables → Actions):

- [ ] `GCP_PROJECT_ID`
- [ ] `GCP_SERVICE_ACCOUNT_JSON`
- [ ] `CLOUD_RUN_SERVICE`
- [ ] `CLOUD_RUN_REGION`

---

## Passo 1 — Criar estrutura de diretórios

```bash
mkdir -p .github/workflows
```

---

## Passo 2 — Criar `.github/workflows/dbt-ci.yml`

**Arquivo:** `.github/workflows/dbt-ci.yml`

```yaml
name: dbt CI

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

env:
  DBT_PROJECT_DIR: ManutBR
  DBT_PROFILES_DIR: .dbt

jobs:
  dbt-staging:
    name: dbt lint, compile & test
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request' || (github.event_name == 'push' && github.ref != 'refs/heads/main')

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Write dbt profiles (CI)
        env:
          GCP_PROJECT_ID: ${{ secrets.GCP_PROJECT_ID }}
          GCP_SERVICE_ACCOUNT_JSON: ${{ secrets.GCP_SERVICE_ACCOUNT_JSON }}
        run: |
          mkdir -p .dbt
          cat > .dbt/profiles.yml <<EOF
          ManutBR:
            target: ci
            outputs:
              ci:
                type: bigquery
                method: service-account-json
                project: ${GCP_PROJECT_ID}
                dataset: ci_${GITHUB_SHA::7}
                location: US
                threads: 4
                timeout_seconds: 300
                retries: 1
                priority: interactive
                keyfile_json: $(echo "$GCP_SERVICE_ACCOUNT_JSON" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin)))")
          EOF

      - name: dbt compile
        run: dbt compile --project-dir $DBT_PROJECT_DIR --profiles-dir $DBT_PROFILES_DIR

      - name: dbt build
        run: dbt build --project-dir $DBT_PROJECT_DIR --profiles-dir $DBT_PROFILES_DIR

      - name: Cleanup CI dataset
        if: always()
        env:
          GCP_PROJECT_ID: ${{ secrets.GCP_PROJECT_ID }}
          GCP_SERVICE_ACCOUNT_JSON: ${{ secrets.GCP_SERVICE_ACCOUNT_JSON }}
        run: |
          echo "$GCP_SERVICE_ACCOUNT_JSON" > /tmp/sa.json
          gcloud auth activate-service-account --key-file=/tmp/sa.json
          bq rm -r -f --project_id=${GCP_PROJECT_ID} ci_${GITHUB_SHA::7} || true

  dbt-prod:
    name: dbt build (prod)
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Write dbt profiles (prod)
        env:
          GCP_PROJECT_ID: ${{ secrets.GCP_PROJECT_ID }}
          GCP_SERVICE_ACCOUNT_JSON: ${{ secrets.GCP_SERVICE_ACCOUNT_JSON }}
        run: |
          mkdir -p .dbt
          cat > .dbt/profiles.yml <<EOF
          ManutBR:
            target: prod
            outputs:
              prod:
                type: bigquery
                method: service-account-json
                project: ${GCP_PROJECT_ID}
                dataset: manutbr_prod
                location: US
                threads: 4
                timeout_seconds: 300
                retries: 1
                priority: interactive
                keyfile_json: $(echo "$GCP_SERVICE_ACCOUNT_JSON" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin)))")
          EOF

      - name: dbt build
        run: dbt build --project-dir $DBT_PROJECT_DIR --profiles-dir $DBT_PROFILES_DIR

      - name: Cleanup CI dataset from merged PR
        if: always()
        env:
          GCP_PROJECT_ID: ${{ secrets.GCP_PROJECT_ID }}
          GCP_SERVICE_ACCOUNT_JSON: ${{ secrets.GCP_SERVICE_ACCOUNT_JSON }}
        run: |
          echo "$GCP_SERVICE_ACCOUNT_JSON" > /tmp/sa.json
          gcloud auth activate-service-account --key-file=/tmp/sa.json
          bq rm -r -f --project_id=${GCP_PROJECT_ID} ci_${GITHUB_SHA::7} || true

      - name: dbt docs generate
        run: dbt docs generate --project-dir $DBT_PROJECT_DIR --profiles-dir $DBT_PROFILES_DIR
```

---

## Passo 3 — Criar `.github/workflows/ingestion-ci.yml`

**Arquivo:** `.github/workflows/ingestion-ci.yml`

```yaml
name: Ingestion CI/CD

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

env:
  IMAGE: gcr.io/${{ secrets.GCP_PROJECT_ID }}/manutbr-ingestion

jobs:
  validate:
    name: Lint & test
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install dependencies
        run: pip install -r ingestion/requirements.txt ruff

      - name: Lint (ruff)
        run: ruff check ingestion/

      - name: Build Docker image (validate only)
        run: docker build -t manutbr-ingestion:pr-test ingestion/

  deploy-prod:
    name: Build & deploy (prod)
    runs-on: ubuntu-latest
    needs: validate
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'

    steps:
      - uses: actions/checkout@v4

      - uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{ secrets.GCP_SERVICE_ACCOUNT_JSON }}

      - uses: google-github-actions/setup-gcloud@v2

      - name: Configure Docker for GCR
        run: gcloud auth configure-docker gcr.io --quiet

      - name: Build & push image
        run: |
          docker build -t $IMAGE:$GITHUB_SHA ingestion/
          docker push $IMAGE:$GITHUB_SHA
          docker tag $IMAGE:$GITHUB_SHA $IMAGE:latest
          docker push $IMAGE:latest

      - uses: google-github-actions/deploy-cloudrun@v2
        with:
          service: ${{ secrets.CLOUD_RUN_SERVICE }}
          region: ${{ secrets.CLOUD_RUN_REGION }}
          image: ${{ env.IMAGE }}:${{ github.sha }}
```

---

## Passo 4 — Commit e push dos workflows

```bash
git add .github/workflows/
git commit -m "ci: adiciona pipelines dbt e ingestion com branch protection"
git push origin feature/develop
```

---

## Passo 5 — Verificar primeira execução

1. Abrir o repositório no GitHub → aba **Actions**
2. Confirmar que os workflows aparecem e executam ao push em `feature/develop`
3. Anotar os nomes exatos dos jobs que aparecem nos checks (necessário para o passo 6)

---

## Passo 6 — Configurar branch protection via `gh` CLI

> Executar **após** a primeira execução dos workflows, pois os checks precisam ter rodado ao menos uma vez para aparecerem no GitHub.

```bash
gh api repos/ckoliveiraa/ManutBR/branches/main/protection \
  --method PUT \
  --field 'required_status_checks[strict]=true' \
  --field 'required_status_checks[contexts][]=dbt lint, compile & test' \
  --field 'required_status_checks[contexts][]=Lint & test' \
  --field 'enforce_admins=true' \
  --field 'required_pull_request_reviews=null' \
  --field 'restrictions=null'
```

**O que isso faz:**
- Bloqueia push direto em `main`
- Exige que `dbt lint, compile & test` e `Lint & test` passem antes do merge
- Aplica a regra também para admins (`enforce_admins=true`)

---

## Passo 7 — Validar proteção

```bash
# Confirma que a proteção foi aplicada
gh api repos/ckoliveiraa/ManutBR/branches/main/protection | jq '.required_status_checks'
```

Resultado esperado:
```json
{
  "strict": true,
  "contexts": ["dbt lint, compile & test", "Lint & test"]
}
```

---

## Checklist Final

- [ ] Secrets configurados no GitHub
- [ ] `dbt-ci.yml` criado e commitado
- [ ] `ingestion-ci.yml` criado e commitado
- [ ] Push em `feature/develop` disparou os workflows
- [ ] Branch protection aplicada em `main`
- [ ] Tentativa de push direto em `main` foi rejeitada
- [ ] PR com CI verde liberou o merge
- [ ] PR com CI falhando bloqueou o merge
