FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DBT_PROFILES_DIR=/app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY profiles.yml .
COPY ManutBR/ ./ManutBR/

CMD ["dbt", "build", "--project-dir", "/app/ManutBR", "--profiles-dir", "/app"]
