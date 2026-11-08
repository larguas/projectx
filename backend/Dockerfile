# syntax=docker/dockerfile:1
# Image de production du backend (multi-stage, uv).

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
# D'abord les métadonnées pour profiter du cache de couches :
# le venv n'est reconstruit que si pyproject.toml / uv.lock changent.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen
COPY . .

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production
WORKDIR /app
# Le venv est copié avant le code : les changements de code ne relancent pas l'installation.
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/config /app/config
COPY --from=builder /app/core /app/core
COPY --from=builder /app/apps /app/apps
COPY --from=builder /app/manage.py /app/openapi.yaml ./
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
