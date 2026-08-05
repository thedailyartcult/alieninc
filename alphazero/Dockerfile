# Alpha Zero — Multi-stage Docker build for production
# Stage 1: Build Go alphacore binary
FROM golang:1.24-alpine AS go-builder
RUN apk add --no-cache git make
WORKDIR /build
COPY alpha-zero-engine/core/alphacore/ ./alphacore/
RUN cd alphacore && CGO_ENABLED=0 GOOS=linux go build -o alphacore -ldflags="-s -w" .

# Stage 2: Build Rust mcp-client (optional, for MCP bridge)
FROM rust:1.97-alpine AS rust-builder
RUN apk add --no-cache musl-dev openssl-dev pkgconfig
WORKDIR /build
COPY rust/mcp-client/ ./mcp-client/
RUN cd mcp-client && cargo build --release

# Stage 3: Python runtime with all dependencies
FROM python:3.13-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

# System deps for psycopg2, redis, and runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libssl3 \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r alphazero && useradd -r -g alphazero -d /app -s /sbin/nologin alphazero

WORKDIR /app

# Copy Python dependencies first (for layer caching)
COPY alpha-zero-engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY alpha-zero-engine/ ./alpha-zero-engine/
COPY ai/ ./ai/
COPY test_*.py ./

# Copy built binaries from builder stages
COPY --from=go-builder /build/alphacore/alphacore /app/alpha-zero-engine/core/bin/alphacore
COPY --from=rust-builder /build/mcp-client/target/release/alphazero-mcp-client /usr/local/bin/alphazero-mcp-client

# Create data directories
RUN mkdir -p /app/alpha-zero-engine/analytics_data \
    /app/alpha-zero-engine/cmb_data \
    /home/tablet/alpha_zero_data \
    && chown -R alphazero:alphazero /app /home/tablet/alpha_zero_data

# Switch to non-root user
USER alphazero

# Expose ports
EXPOSE 8080

# Health check (uses the /api/health endpoint)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

# Default command
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "--timeout", "600", "wsgi:app"]