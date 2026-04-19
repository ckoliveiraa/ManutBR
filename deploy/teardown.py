"""Remove tudo que o deploy.py criou no GCP.

Uso:
    python teardown.py           # pede confirmacao
    python teardown.py --yes     # sem confirmacao (use com cuidado)

O que e removido (na ordem):
    1. Cloud Run Job
    2. Artifact Registry (repo + todas as imagens dentro)
    3. IAM bindings da service account no projeto
    4. Service account

APIs habilitadas NAO sao desabilitadas (nao geram custo ociosas).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ENV_FILE = SCRIPT_DIR / ".env"


def _load_env(path: Path) -> None:
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


def _gcloud() -> str:
    path = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if not path:
        sys.exit("gcloud nao encontrado no PATH.")
    return path


def _run(cmd: list[str]) -> int:
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, text=True).returncode


def _exists(cmd: list[str]) -> bool:
    return subprocess.run(cmd, capture_output=True, text=True).returncode == 0


def _delete_job(gcloud: str, project: str, region: str, job_name: str) -> None:
    if not _exists([gcloud, "run", "jobs", "describe", job_name,
                    f"--region={region}", f"--project={project}"]):
        print(f"[skip] Cloud Run Job '{job_name}' nao existe.")
        return
    _run([gcloud, "run", "jobs", "delete", job_name,
          f"--region={region}", f"--project={project}", "--quiet"])


def _delete_artifact_repo(gcloud: str, project: str, region: str, repo_name: str) -> None:
    if not _exists([gcloud, "artifacts", "repositories", "describe", repo_name,
                    f"--location={region}", f"--project={project}"]):
        print(f"[skip] Artifact Registry '{repo_name}' nao existe.")
        return
    _run([gcloud, "artifacts", "repositories", "delete", repo_name,
          f"--location={region}", f"--project={project}", "--quiet"])


def _remove_iam_bindings(gcloud: str, project: str, sa_email: str) -> None:
    for role in ("roles/bigquery.dataEditor", "roles/bigquery.jobUser"):
        result = subprocess.run(
            [gcloud, "projects", "remove-iam-policy-binding", project,
             f"--member=serviceAccount:{sa_email}", f"--role={role}",
             "--condition=None", "--quiet"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print(f"[ok] IAM binding {role} removido.")
        else:
            print(f"[skip] IAM binding {role} ausente.")


def _delete_service_account(gcloud: str, project: str, sa_email: str) -> None:
    if not _exists([gcloud, "iam", "service-accounts", "describe", sa_email,
                    f"--project={project}"]):
        print(f"[skip] Service account '{sa_email}' nao existe.")
        return
    _run([gcloud, "iam", "service-accounts", "delete", sa_email,
          f"--project={project}", "--quiet"])


def teardown(*, assume_yes: bool = False) -> None:
    project = _required("GCP_PROJECT_ID")
    region = _env("GCP_REGION", "us-central1")
    repo_name = _env("ARTIFACT_REPO", "manutbr")
    job_name = _env("JOB_NAME", "manutbr-dbt-job")
    sa_name = _env("SERVICE_ACCOUNT_NAME", "dbt-runner")
    sa_email = f"{sa_name}@{project}.iam.gserviceaccount.com"

    print("== Recursos que serao removidos ==")
    print(f"  Project:          {project}")
    print(f"  Region:           {region}")
    print(f"  Cloud Run Job:    {job_name}")
    print(f"  Artifact Repo:    {repo_name} (e todas as imagens dentro)")
    print(f"  Service Account:  {sa_email} (e seus IAM bindings)")
    print()

    if not assume_yes:
        resposta = input("Digite 'DELETE' para confirmar: ").strip()
        if resposta != "DELETE":
            sys.exit("Cancelado.")

    gcloud = _gcloud()
    _delete_job(gcloud, project, region, job_name)
    _delete_artifact_repo(gcloud, project, region, repo_name)
    _remove_iam_bindings(gcloud, project, sa_email)
    _delete_service_account(gcloud, project, sa_email)
    print("\nTeardown concluido.")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--yes", action="store_true", help="Pula confirmacao interativa")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    teardown(assume_yes=args.yes)
