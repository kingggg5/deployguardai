FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt \
    && addgroup --system deployguard \
    && adduser --system --ingroup deployguard --home /nonexistent deployguard

COPY --chown=deployguard:deployguard app ./app
COPY --chown=deployguard:deployguard alembic.ini .
COPY --chown=deployguard:deployguard migrations ./migrations

USER deployguard

EXPOSE 8100

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
