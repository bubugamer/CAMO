FROM debian:bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

RUN set -eux; \
    for attempt in 1 2 3 4 5; do \
        apt-get -o Acquire::Retries=5 update && \
        apt-get -o Acquire::Retries=5 install -y --no-install-recommends --fix-missing \
            build-essential \
            ca-certificates \
            curl \
            python3 \
            python3-dev \
            python3-venv && \
        rm -rf /var/lib/apt/lists/* && \
        exit 0; \
        echo "apt-get failed on attempt ${attempt}; retrying in 5 seconds..." >&2; \
        rm -rf /var/lib/apt/lists/*; \
        sleep 5; \
    done; \
    exit 1

RUN python3 -m venv /opt/venv \
    && pip install --upgrade pip setuptools wheel

COPY pyproject.toml README.md ./
COPY alembic.ini ./
COPY config ./config
COPY migrations ./migrations
COPY prompts ./prompts
COPY src ./src
COPY docker ./docker

RUN pip install --no-cache-dir .

CMD ["sh", "/app/docker/start-api.sh"]
