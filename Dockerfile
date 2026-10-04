# drawgen with draw.io Desktop and a virtual display: exact rendering anywhere Docker runs,
# with no desktop. Default command is the MCP server on stdio.
#   docker build -t drawgen .
#   docker run --rm -v "$PWD:/work" -w /work drawgen drawgen build spec.yaml
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb xauth libgbm1 libasound2 libnss3 libgtk-3-0 libxss1 libxtst6 libsecret-1-0 \
        fonts-liberation fonts-dejavu-core ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev && uv run drawgen install-drawio

ENV PATH="/app/.venv/bin:$PATH" DRAWGEN_CACHE=/root/.cache/drawgen
CMD ["drawgen-mcp"]
