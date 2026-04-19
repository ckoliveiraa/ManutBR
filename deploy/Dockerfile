FROM python:3.12-slim

# Nome da pasta do projeto dbt no contexto de build (sobrescrevivel)
ARG DBT_PROJECT_DIR=ManutBR

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DBT_PROFILES_DIR=/app

WORKDIR /app

COPY deploy/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY deploy/profiles.yml .
COPY ${DBT_PROJECT_DIR}/ ./project/

CMD ["dbt", "build", "--project-dir", "/app/project", "--profiles-dir", "/app"]
