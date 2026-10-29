# ClearSwath web app. Build: docker build -t clearswath .  Run: docker run -p 8000:8000 --env-file .env clearswath

# The page: built here with Node, served by FastAPI from web/dist. Node never runs in the final image.
FROM node:22.21.0-slim AS page
WORKDIR /build/web-app
COPY web-app/package.json web-app/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web-app ./
RUN npm run build

FROM python:3.12-slim

# rasterio's bundled GDAL needs libexpat, which slim leaves out
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /usr/local/bin/uv
ENV UV_NO_CACHE=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH"

WORKDIR /srv
# Dependencies first (cached layer); rasterio, pyproj, shapely and PyMuPDF ship wheels with their C libraries.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY web ./web
COPY --from=page /build/web/dist ./web/dist
COPY data/demo ./data/demo

RUN useradd --create-home clearswath && mkdir -p data/runs data/cache data/logs && chown -R clearswath data
USER clearswath

ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.api:app --host 0.0.0.0 --port ${PORT}"]
