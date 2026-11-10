FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 krill && mkdir -p /data && chown krill:krill /data
USER krill

# SQLite lives on a mounted volume so the DB survives rebuilds.
VOLUME ["/data"]

CMD ["python", "-m", "krillionbot"]
