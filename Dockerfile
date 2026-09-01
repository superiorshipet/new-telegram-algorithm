FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY pyproject.toml README.md ./
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
COPY entrypoint.sh ./entrypoint.sh

RUN pip install --upgrade pip && pip install . \
    && chmod +x ./entrypoint.sh

USER app

ENTRYPOINT ["./entrypoint.sh"]
CMD ["python", "-m", "app.bot"]

