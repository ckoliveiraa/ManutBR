"""
Cloud Run ingestion job — reads CSV/Parquet files from GCS, appends to BigQuery,
moves processed files, and logs results to a BQ audit table.

Environment variables required:
  GCP_PROJECT        — GCP project ID
  BQ_DATASET         — Target BigQuery dataset
  GCS_BUCKET         — GCS bucket name (without gs://)
  GCS_INPUT_PREFIX   — Folder inside the bucket with incoming files (e.g. "raw/")
  GCS_PROCESSED_PREFIX — Destination folder after ingestion (e.g. "processed/")
  DOMAIN             — Domain name logged to the audit table
"""

import os
import io
import logging
import datetime

import pandas as pd
from flask import Flask, jsonify
from google.cloud import bigquery, storage

from bq_schemas import ALL_SCHEMAS

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

DOMAIN = os.environ.get("DOMAIN", "gestao_manutencao_industrial")

# ── Config ────────────────────────────────────────────────────────────────────
PROJECT = os.environ["GCP_PROJECT"]
DATASET = os.environ["BQ_DATASET"]
BUCKET_NAME = os.environ["GCS_BUCKET"]
INPUT_PREFIX = os.environ.get("GCS_INPUT_PREFIX", "raw/").rstrip("/") + "/"
PROCESSED_PREFIX = os.environ.get("GCS_PROCESSED_PREFIX", "processed/").rstrip("/") + "/"
# Sub-folder between the input prefix and the table name, e.g.:
#   raw/gestao_manutencao_industrial/equipamentos/
INPUT_DOMAIN_FOLDER = os.environ.get("GCS_INPUT_DOMAIN_FOLDER", DOMAIN)

# ── Clients ───────────────────────────────────────────────────────────────────
bq_client = bigquery.Client(project=PROJECT)
gcs_client = storage.Client(project=PROJECT)
bucket = gcs_client.bucket(BUCKET_NAME)

# ── Audit table schema ────────────────────────────────────────────────────────
AUDIT_TABLE_ID = f"{PROJECT}.{DATASET}.ingestion_logs"
AUDIT_SCHEMA = [
    bigquery.SchemaField("run_ts", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("domain", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("table_name", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("source_file", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("rows_ingested", "INT64", mode="NULLABLE"),
    bigquery.SchemaField("status", "STRING", mode="REQUIRED"),  # SUCCESS | ERROR
    bigquery.SchemaField("error_message", "STRING", mode="NULLABLE"),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def ensure_dataset() -> None:
    dataset_ref = bigquery.Dataset(f"{PROJECT}.{DATASET}")
    dataset_ref.location = "US"
    bq_client.create_dataset(dataset_ref, exists_ok=True)
    log.info("Dataset %s.%s ready.", PROJECT, DATASET)


def ensure_table(table_id: str, schema: list[bigquery.SchemaField]) -> None:
    table_ref = bigquery.Table(table_id, schema=schema)
    bq_client.create_table(table_ref, exists_ok=True)
    log.info("Table %s ready.", table_id)


def ensure_audit_table() -> None:
    ensure_table(AUDIT_TABLE_ID, AUDIT_SCHEMA)


def cast_date_columns(df: pd.DataFrame, bq_schema: list[bigquery.SchemaField]) -> pd.DataFrame:
    date_cols = [f.name for f in bq_schema if f.field_type == "DATE"]
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
    return df


def read_gcs_file(blob: storage.Blob) -> pd.DataFrame:
    name = blob.name.lower()
    if not (name.endswith(".json") or name.endswith(".ndjson")):
        raise ValueError(
            f"Formato nao suportado: {blob.name}. "
            f"A ingestao espera arquivos JSON (NDJSON: um objeto JSON por linha)."
        )
    data = blob.download_as_bytes()
    return pd.read_json(io.BytesIO(data), lines=True)


def move_to_processed(blob: storage.Blob) -> None:
    # Preserve folder structure and add timestamp to filename:
    # raw/domain/table/file.json → processed/domain/table/file_20260416T000500.json
    relative_path = blob.name.removeprefix(INPUT_PREFIX)
    path_parts = relative_path.rsplit("/", 1)
    folder = path_parts[0] + "/" if len(path_parts) > 1 else ""
    filename = path_parts[-1]
    stem, _, ext = filename.rpartition(".")
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
    dest_name = f"{PROCESSED_PREFIX}{folder}{stem}_{ts}.{ext}"
    bucket.copy_blob(blob, bucket, dest_name)
    blob.delete()
    log.info("Moved %s → %s", blob.name, dest_name)


def append_to_bq(table_id: str, df: pd.DataFrame) -> int:
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_RELAXATION],
    )
    job = bq_client.load_table_from_dataframe(df, table_id, job_config=job_config)
    job.result()
    return len(df)


def write_audit_log(entries: list[dict]) -> None:
    if not entries:
        return
    errors = bq_client.insert_rows_json(AUDIT_TABLE_ID, entries)
    if errors:
        log.error("Failed to write audit logs: %s", errors)


# ── Core ingestion ────────────────────────────────────────────────────────────

def ingest_table(table_name: str, bq_schema: list[bigquery.SchemaField]) -> list[dict]:
    table_id = f"{PROJECT}.{DATASET}.{table_name}"
    ensure_table(table_id, bq_schema)

    prefix = f"{INPUT_PREFIX}{INPUT_DOMAIN_FOLDER}/{table_name}/"
    blobs = list(gcs_client.list_blobs(BUCKET_NAME, prefix=prefix))
    if not blobs:
        log.info("No files found under gs://%s/%s — skipping.", BUCKET_NAME, prefix)
        return []

    audit_entries = []
    run_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

    for blob in blobs:
        # Skip "folder" placeholder objects
        if blob.name.endswith("/"):
            continue
        source_file = f"gs://{BUCKET_NAME}/{blob.name}"
        log.info("Ingesting %s → %s", source_file, table_id)
        try:
            df = read_gcs_file(blob)
            df = cast_date_columns(df, bq_schema)
            rows = append_to_bq(table_id, df)
            move_to_processed(blob)
            audit_entries.append(
                {
                    "run_ts": run_ts,
                    "domain": DOMAIN,
                    "table_name": table_name,
                    "source_file": source_file,
                    "rows_ingested": rows,
                    "status": "SUCCESS",
                    "error_message": None,
                }
            )
            log.info("SUCCESS — %d rows loaded from %s.", rows, source_file)
        except Exception as exc:
            log.exception("ERROR ingesting %s: %s", source_file, exc)
            audit_entries.append(
                {
                    "run_ts": run_ts,
                    "domain": DOMAIN,
                    "table_name": table_name,
                    "source_file": source_file,
                    "rows_ingested": None,
                    "status": "ERROR",
                    "error_message": str(exc),
                }
            )

    return audit_entries


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    ensure_dataset()
    ensure_audit_table()

    all_audit = []
    for schema_cls in ALL_SCHEMAS:
        entries = ingest_table(schema_cls.TABLE_NAME, schema_cls.FIELDS)
        all_audit.extend(entries)

    write_audit_log(all_audit)

    errors = [e for e in all_audit if e["status"] == "ERROR"]
    if errors:
        raise RuntimeError(f"{len(errors)} table(s) had errors during ingestion.")
    log.info("Ingestion complete. %d file(s) processed.", len(all_audit))


# ── HTTP server (Cloud Run Service) ──────────────────────────────────────────

app = Flask(__name__)


@app.route("/", methods=["POST", "GET"])
def run():
    try:
        main()
        return jsonify({"status": "ok"}), 200
    except Exception as exc:
        log.exception("Ingestion failed: %s", exc)
        return jsonify({"status": "error", "message": str(exc)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
