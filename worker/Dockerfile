FROM python:3.11.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY worker/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --requirement /tmp/requirements.txt

COPY worker /app/worker
COPY prompts /app/prompts
COPY data/schema.json /app/data/schema.json

RUN useradd --create-home --uid 10001 pipeline && chown -R pipeline:pipeline /app
USER pipeline

CMD ["python", "-m", "worker.label"]

