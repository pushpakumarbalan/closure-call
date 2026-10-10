# ---- frontend build ----
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ .
RUN npm run build

# ---- backend runtime ----
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY backend/pyproject.toml ./backend/
RUN pip install --upgrade pip && pip install "strands-agents[openai]>=1.59.0" "fastapi>=0.115" "uvicorn[standard]>=0.30" "httpx>=0.27" "pydantic>=2.7" "python-dotenv>=1.0"
COPY backend/app ./backend/app
COPY --from=web /web/dist ./frontend/dist
ENV STATIC_DIR=/app/frontend/dist DB_PATH=/data/closurecall.sqlite3
VOLUME ["/data"]
EXPOSE 8000
WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
