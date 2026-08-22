FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-client \
        redis-tools \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home appuser

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser . .

COPY entrypoint.sh /entrypoint.sh

RUN chmod 755 /entrypoint.sh

USER appuser

ENTRYPOINT ["/entrypoint.sh"]