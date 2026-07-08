FROM python:3.14-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev gcc && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md attesta-architecture.md ./
COPY app ./app
COPY config ./config
COPY ops ./ops
COPY public ./public
COPY alembic ./alembic
COPY alembic.ini ./
COPY ops/entrypoint.sh ./ops/entrypoint.sh
RUN chmod +x ./ops/entrypoint.sh

RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["./ops/entrypoint.sh"]
