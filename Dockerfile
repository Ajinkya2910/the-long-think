# Runs the pipeline anywhere: docker compose run --rm pipeline
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends stockfish ca-certificates \
 && rm -rf /var/lib/apt/lists/*
ENV STOCKFISH_PATH=/usr/games/stockfish \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml ./
COPY storyteller ./storyteller
RUN pip install --no-cache-dir .
COPY config.toml ./
COPY schema ./schema

# data/ (raw PGNs + engine cache) and web/data (site JSON) are mounted as volumes
ENTRYPOINT ["python", "-m", "storyteller"]
CMD ["run"]
