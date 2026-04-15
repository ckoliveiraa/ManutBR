"""Loads the YAML schema and maps dtype strings to BigQuery SchemaFields."""

import yaml
from google.cloud import bigquery

DTYPE_TO_BQ = {
    "int_seq": bigquery.enums.SqlTypeNames.INT64,
    "int": bigquery.enums.SqlTypeNames.INT64,
    "float": bigquery.enums.SqlTypeNames.FLOAT64,
    "str": bigquery.enums.SqlTypeNames.STRING,
    "text": bigquery.enums.SqlTypeNames.STRING,
    "date": bigquery.enums.SqlTypeNames.DATE,
    "datetime": bigquery.enums.SqlTypeNames.DATETIME,
    "bool": bigquery.enums.SqlTypeNames.BOOL,
    "name": bigquery.enums.SqlTypeNames.STRING,
    "email": bigquery.enums.SqlTypeNames.STRING,
    "phone": bigquery.enums.SqlTypeNames.STRING,
    "company": bigquery.enums.SqlTypeNames.STRING,
    "bothify": bigquery.enums.SqlTypeNames.STRING,
}


def load_schema(yaml_path: str) -> dict:
    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_bq_schema(table_columns: dict) -> list[bigquery.SchemaField]:
    fields = []
    for col_name, col_def in table_columns.items():
        dtype = col_def.get("dtype", "str")
        bq_type = DTYPE_TO_BQ.get(dtype, bigquery.enums.SqlTypeNames.STRING)
        nullable = col_def.get("nullable", 0)
        mode = "NULLABLE" if nullable else "REQUIRED"
        # primary keys and foreign keys are always required
        if col_def.get("primary_key") or col_def.get("foreign_key"):
            mode = "REQUIRED"
        fields.append(bigquery.SchemaField(col_name, bq_type, mode=mode))
    return fields
