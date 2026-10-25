FROM python:3.12-alpine

RUN apk add --no-cache \
    postgresql-client \
    redis \
    git
    
RUN addgroup -S appgroup \
    && adduser -S -G appgroup appuser

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser . .

COPY entrypoint.sh /entrypoint.sh

RUN chmod 755 /entrypoint.sh

USER appuser

ENTRYPOINT ["/entrypoint.sh"]