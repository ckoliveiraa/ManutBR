"""
BigQuery table schemas for the gestao_manutencao_industrial domain.
Schemas are defined in code — no YAML or external file is passed to BigQuery.
"""

from google.cloud import bigquery


class EquipamentosSchema:
    TABLE_NAME = "equipamentos"
    FIELDS = [
        bigquery.SchemaField("id",               "INT64",   mode="REQUIRED"),
        bigquery.SchemaField("tag_ativo",         "STRING",  mode="REQUIRED"),
        bigquery.SchemaField("nome_equipamento",  "STRING",  mode="REQUIRED"),
        bigquery.SchemaField("setor",             "STRING",  mode="REQUIRED"),
        bigquery.SchemaField("fabricante",        "STRING",  mode="REQUIRED"),
        bigquery.SchemaField("data_instalacao",   "DATE",    mode="REQUIRED"),
        bigquery.SchemaField("criticidade",       "STRING",  mode="REQUIRED"),
    ]


class TecnicosSchema:
    TABLE_NAME = "tecnicos"
    FIELDS = [
        bigquery.SchemaField("id",                  "INT64",  mode="REQUIRED"),
        bigquery.SchemaField("nome_completo",        "STRING", mode="REQUIRED"),
        bigquery.SchemaField("especialidade",        "STRING", mode="REQUIRED"),
        bigquery.SchemaField("telefone",             "STRING", mode="REQUIRED"),
        bigquery.SchemaField("email_corporativo",    "STRING", mode="REQUIRED"),
        bigquery.SchemaField("nivel_experiencia",    "STRING", mode="REQUIRED"),
    ]


class OrdensServicoSchema:
    TABLE_NAME = "ordens_servico"
    FIELDS = [
        bigquery.SchemaField("id",                "INT64",   mode="REQUIRED"),
        bigquery.SchemaField("equipamento_id",    "INT64",   mode="REQUIRED"),
        bigquery.SchemaField("tecnico_id",        "INT64",   mode="REQUIRED"),
        bigquery.SchemaField("tipo_manutencao",   "STRING",  mode="REQUIRED"),
        bigquery.SchemaField("prioridade",        "STRING",  mode="REQUIRED"),
        bigquery.SchemaField("data_abertura",     "DATE",    mode="REQUIRED"),
        bigquery.SchemaField("data_conclusao",    "DATE",    mode="NULLABLE"),
        bigquery.SchemaField("horas_parada",      "FLOAT64", mode="REQUIRED"),
        bigquery.SchemaField("custo_pecas",       "FLOAT64", mode="REQUIRED"),
        bigquery.SchemaField("custo_mao_obra",    "FLOAT64", mode="REQUIRED"),
        bigquery.SchemaField("descricao_servico", "STRING",  mode="NULLABLE"),
        bigquery.SchemaField("status",            "STRING",  mode="REQUIRED"),
    ]


class TipoManutencaoSchema:
    TABLE_NAME = "tipo_manutencao"
    FIELDS = [
        bigquery.SchemaField("id_tipo",         "STRING", mode="REQUIRED"),
        bigquery.SchemaField("tipo_manutencao", "STRING", mode="REQUIRED"),
    ]


# Registry — used by main.py to iterate over all tables
ALL_SCHEMAS = [
    EquipamentosSchema,
    TecnicosSchema,
    OrdensServicoSchema,
    TipoManutencaoSchema,
]
