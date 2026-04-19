"""Enfileira disparo do Workflow com deduplicacao por janela de tempo.

Recebe eventos Eventarc/Pub/Sub de Cloud Storage. Cria uma Cloud Task com
nome deterministico por janela (`WINDOW_SECONDS`). Tasks com o mesmo nome
sao rejeitadas pelo Cloud Tasks (ALREADY_EXISTS), garantindo que rajadas
de arquivos disparem o Workflow exatamente UMA vez.
"""

import datetime as dt
import json
import logging
import os

import functions_framework
from google.api_core import exceptions as gax
from google.cloud import tasks_v2
from google.protobuf import duration_pb2, timestamp_pb2

log = logging.getLogger()
log.setLevel(logging.INFO)

PROJECT = os.environ["GCP_PROJECT"]
LOCATION = os.environ.get("TASKS_LOCATION", "us-central1")
QUEUE = os.environ.get("TASKS_QUEUE", "ingestion-queue")
WORKFLOW = os.environ.get("WORKFLOW_NAME", "manutbr-pipeline")
SERVICE_ACCOUNT = os.environ["INVOKER_SA"]
WINDOW_SECONDS = int(os.environ.get("WINDOW_SECONDS", "120"))
WATCH_PREFIX = os.environ.get("WATCH_PREFIX", "raw/gestao_manutencao_industrial/")

_client = tasks_v2.CloudTasksClient()
_queue_path = _client.queue_path(PROJECT, LOCATION, QUEUE)

_workflow_exec_url = (
    f"https://workflowexecutions.googleapis.com/v1/"
    f"projects/{PROJECT}/locations/{LOCATION}/workflows/{WORKFLOW}/executions"
)


def _window_id(now: dt.datetime) -> str:
    epoch = int(now.timestamp())
    bucket = epoch // WINDOW_SECONDS
    return f"ingestion-{bucket}"


@functions_framework.cloud_event
def enqueue(event):
    data = event.data or {}
    name = data.get("name", "")
    if not name.startswith(WATCH_PREFIX):
        log.info("fora do prefixo, ignorado: %s", name)
        return

    now = dt.datetime.now(dt.timezone.utc)
    window = _window_id(now)
    schedule = now + dt.timedelta(seconds=WINDOW_SECONDS)

    ts = timestamp_pb2.Timestamp()
    ts.FromDatetime(schedule)

    task = tasks_v2.Task(
        name=f"{_queue_path}/tasks/{window}",
        schedule_time=ts,
        dispatch_deadline=duration_pb2.Duration(seconds=1800),
        http_request=tasks_v2.HttpRequest(
            http_method=tasks_v2.HttpMethod.POST,
            url=_workflow_exec_url,
            headers={"Content-Type": "application/json"},
            body=json.dumps({}).encode(),
            oauth_token=tasks_v2.OAuthToken(
                service_account_email=SERVICE_ACCOUNT,
                scope="https://www.googleapis.com/auth/cloud-platform",
            ),
        ),
    )

    try:
        _client.create_task(parent=_queue_path, task=task)
        log.info("task criada: %s (schedule=%s)", window, schedule.isoformat())
    except gax.AlreadyExists:
        log.info("task %s ja existe — dedup ok (trigger=%s)", window, name)
