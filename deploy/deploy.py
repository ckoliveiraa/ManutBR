"""Deploy do projeto dbt para o Google Cloud (Cloud Run Jobs).

============================================================
PRE-REQUISITOS
============================================================

1. Software local
   - Python 3.10+
   - Google Cloud SDK (gcloud) no PATH
     https://cloud.google.com/sdk/docs/install

2. Autenticacao no GCP (uma vez por maquina)
       gcloud auth login
       gcloud auth application-default login
       gcloud config set project <SEU_PROJECT_ID>

3. Conta com permissao no projeto GCP. Roles minimas:
       roles/serviceusage.serviceUsageAdmin
       roles/iam.serviceAccountAdmin
       roles/resourcemanager.projectIamAdmin
       roles/artifactregistry.admin
       roles/run.admin
       roles/cloudbuild.builds.editor
   (em projetos pessoais, roles/owner geralmente ja basta)

4. Projeto GCP existente com billing habilitado.
   APIs serao habilitadas pelo proprio script.

5. Estrutura do repo
       <repo>/
       ├── <DBT_PROJECT_DIR>/        # projeto dbt (com dbt_project.yml)
       ├── .dockerignore
       └── deploy/
           ├── Dockerfile
           ├── cloudbuild.yaml
           ├── profiles.yml          # nome do profile = `profile:` do dbt_project.yml
           ├── requirements.txt
           ├── deploy.py             # este arquivo
           └── .env                  # crie a partir de .env.example

6. Configuracao em deploy/.env
   Obrigatorios:
       GCP_PROJECT_ID=...
       BQ_DATASET=...
   Opcional (se a pasta do projeto dbt nao for "ManutBR"):
       DBT_PROJECT_DIR=NomeDaPasta

============================================================
FLUXO DO SCRIPT
============================================================
   1. Habilita APIs (artifactregistry, run, cloudbuild, bigquery, iam).
   2. Cria a service account `dbt-runner` com papeis BigQuery.
   3. Cria o repo Artifact Registry (se nao existir).
   4. Builda a imagem via Cloud Build (deploy/cloudbuild.yaml).
   5. Cria/atualiza Cloud Run Job que executa `dbt build`.
   6. Se --execute, dispara uma execucao e aguarda terminar.

============================================================
USO
============================================================
   cp deploy/.env.example deploy/.env    # edite GCP_PROJECT_ID e BQ_DATASET
   python deploy/deploy.py               # builda + implanta
   python deploy/deploy.py --execute     # builda + implanta + roda
   python deploy/deploy.py --tag v1.2.0  # sobrescreve IMAGE_TAG do .env

Pra remover tudo que foi criado: python deploy/teardown.py
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
ENV_FILE = SCRIPT_DIR / ".env"


def _load_env(path: Path) -> None:
    """Carrega KEY=VALUE de um .env para os.environ (sem sobrescrever vars ja setadas)."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if value and value[0] not in ('"', "'"):
            hash_idx = value.find("#")
            if hash_idx != -1:
                value = value[:hash_idx].rstrip()
        value = value.strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


_load_env(ENV_FILE)


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"Variavel obrigatoria ausente: {name}. Defina em {ENV_FILE} ou no ambiente.")
    return value


def _env(name: str, default: str) -> str:
    return os.environ.get(name) or default


REQUIRED_APIS = (
    "artifactregistry.googleapis.com",
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "bigquery.googleapis.com",
    "iam.googleapis.com",
)


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, check=check, text=True)


def _gcloud() -> str:
    path = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if not path:
        sys.exit("gcloud nao encontrado no PATH.")
    return path


def _enable_apis(gcloud: str, project: str) -> None:
    _run([gcloud, "services", "enable", *REQUIRED_APIS, f"--project={project}"])


def _ensure_service_account(gcloud: str, project: str, sa_name: str) -> str:
    sa_email = f"{sa_name}@{project}.iam.gserviceaccount.com"
    exists = subprocess.run(
        [gcloud, "iam", "service-accounts", "describe", sa_email, f"--project={project}"],
        capture_output=True, text=True,
    )
    if exists.returncode != 0:
        _run([gcloud, "iam", "service-accounts", "create", sa_name,
              "--display-name=dbt ManutBR runner", f"--project={project}"])
    for role in ("roles/bigquery.dataEditor", "roles/bigquery.jobUser"):
        _run([gcloud, "projects", "add-iam-policy-binding", project,
              f"--member=serviceAccount:{sa_email}", f"--role={role}",
              "--condition=None", "--quiet"])
    return sa_email


def _ensure_artifact_repo(gcloud: str, project: str, region: str, repo_name: str) -> None:
    result = subprocess.run(
        [gcloud, "artifacts", "repositories", "describe", repo_name,
         f"--location={region}", f"--project={project}"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return
    _run([gcloud, "artifacts", "repositories", "create", repo_name,
          "--repository-format=docker", f"--location={region}",
          "--description=Imagens dbt ManutBR", f"--project={project}"])


def _build_and_push(gcloud: str, project: str, region: str, tag: str,
                    repo_name: str, image_name: str, source: Path,
                    dbt_project_dir: str) -> str:
    image_uri = f"{region}-docker.pkg.dev/{project}/{repo_name}/{image_name}:{tag}"
    cloudbuild = SCRIPT_DIR / "cloudbuild.yaml"
    substitutions = f"_DBT_PROJECT_DIR={dbt_project_dir},_IMAGE_URI={image_uri}"
    _run([gcloud, "builds", "submit", str(source),
          f"--config={cloudbuild}", f"--substitutions={substitutions}",
          f"--project={project}"])
    return image_uri


def _job_exists(gcloud: str, project: str, region: str, job_name: str) -> bool:
    result = subprocess.run(
        [gcloud, "run", "jobs", "describe", job_name,
         f"--region={region}", f"--project={project}"],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def _deploy_job(gcloud: str, project: str, region: str, image_uri: str,
                dataset: str, location: str, threads: int,
                service_account: str, job_name: str) -> None:
    env_vars = ",".join([
        f"GCP_PROJECT_ID={project}",
        f"BQ_DATASET={dataset}",
        f"BQ_LOCATION={location}",
        f"DBT_THREADS={threads}",
    ])
    verb = "update" if _job_exists(gcloud, project, region, job_name) else "create"
    _run([gcloud, "run", "jobs", verb, job_name,
          f"--image={image_uri}", f"--region={region}", f"--project={project}",
          f"--set-env-vars={env_vars}", f"--service-account={service_account}",
          "--task-timeout=3600", "--memory=2Gi", "--cpu=2", "--max-retries=1"])


def _execute_job(gcloud: str, project: str, region: str, job_name: str) -> None:
    _run([gcloud, "run", "jobs", "execute", job_name,
          f"--region={region}", f"--project={project}", "--wait"])


def deploy(*, execute: bool = False, tag: str | None = None) -> str:
    """Builda (do working tree local), publica e implanta o job dbt. Le config do .env."""
    project = _required("GCP_PROJECT_ID")
    dataset = _required("BQ_DATASET")
    region = _env("GCP_REGION", "us-central1")
    location = _env("BQ_LOCATION", "US")
    threads = int(_env("DBT_THREADS", "8"))
    repo_name = _env("ARTIFACT_REPO", "manutbr")
    image_name = _env("IMAGE_NAME", "manutbr-dbt")
    job_name = _env("JOB_NAME", "manutbr-dbt-job")
    sa_name = _env("SERVICE_ACCOUNT_NAME", "dbt-runner")
    image_tag = tag or _env("IMAGE_TAG", "latest")
    dbt_project_dir = _env("DBT_PROJECT_DIR", "ManutBR")

    gcloud = _gcloud()
    _enable_apis(gcloud, project)
    sa_email = _ensure_service_account(gcloud, project, sa_name)
    _ensure_artifact_repo(gcloud, project, region, repo_name)
    image_uri = _build_and_push(gcloud, project, region, image_tag,
                                repo_name, image_name, REPO_ROOT, dbt_project_dir)
    _deploy_job(gcloud, project, region, image_uri, dataset, location, threads, sa_email, job_name)
    if execute:
        _execute_job(gcloud, project, region, job_name)
    return image_uri


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--execute", action="store_true", help="Dispara execucao apos deploy")
    p.add_argument("--tag", default=None, help="Sobrescreve IMAGE_TAG do .env")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    uri = deploy(execute=args.execute, tag=args.tag)
    print(f"\nImagem publicada: {uri}")
