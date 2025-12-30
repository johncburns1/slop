# Multi-stage Dockerfile for Slop
# Stage 1: Build React frontend
# Stage 2: Python runtime with built frontend

# ============================================
# Stage 1: Build Frontend
# ============================================
FROM node:25-alpine AS frontend-builder

WORKDIR /app/frontend

# Copy frontend package files
COPY frontend/package*.json ./

# Install dependencies
RUN npm ci --only=production

# Copy frontend source
COPY frontend/ ./

# Build frontend (outputs to dist/)
RUN npm run build

# ============================================
# Stage 2: Python Runtime
# ============================================
FROM python:3.13-slim AS runtime

# Set working directory
WORKDIR /app

# Install uv for faster dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1

# Copy project files
COPY pyproject.toml uv.lock ./
COPY src/ ./src/

# Install production dependencies only (no dev deps)
RUN uv sync --frozen --no-dev

# Copy built frontend from Stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Create directory for SQLite database
RUN mkdir -p /data

# Expose port 8000 for FastAPI
EXPOSE 8000

# Health check on /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()"

# Run the application
# When FastAPI server is implemented, this will start the server
# The server should be accessible at: uvicorn slop.api.main:app or via `uv run slop serve`
CMD ["uv", "run", "slop", "serve"]
