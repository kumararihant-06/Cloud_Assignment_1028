FROM python:3.11.10-slim-bookworm

ARG TARGETARCH

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MODEL_CACHE_DIR=/models

WORKDIR /app

COPY service/requirements.lock /tmp/requirements.lock
RUN if [ "$TARGETARCH" = "amd64" ]; then \
      pip install --no-cache-dir --no-deps --index-url https://download.pytorch.org/whl/cpu torch==2.2.2; \
    else \
      pip install --no-cache-dir --no-deps torch==2.2.2; \
    fi \
    && pip install --no-cache-dir --no-deps --requirement /tmp/requirements.lock

COPY service /app/service
COPY data/schema.json /app/data/schema.json

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /models \
    && chown -R appuser:appuser /app /models

USER appuser
EXPOSE 8000

CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8000"]

