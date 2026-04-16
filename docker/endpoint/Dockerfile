# tunnelctl endpoint - multi-arch (amd64, arm64 for Pi and Mac)
# Build context should be the repo root.

FROM --platform=$TARGETPLATFORM python:3.12-slim

ARG TARGETPLATFORM
ARG BUILDPLATFORM

LABEL maintainer="tunnelctl"
LABEL description="tunnelctl endpoint service with NGINX"
LABEL org.opencontainers.image.source="https://github.com/tunnelctl/tunnelctl"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    tini \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (cached layer)
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Copy application code
COPY src/ src/

# Re-install to pick up the actual source
RUN pip install --no-cache-dir .

# Copy default config and NGINX template
COPY config.example.yaml /app/config.example.yaml
COPY docker/endpoint/nginx.conf.template /etc/nginx/nginx.conf

# Create directories
RUN mkdir -p /app/config /etc/nginx/conf.d

VOLUME ["/app/config", "/etc/nginx/conf.d"]

# HTTP, HTTPS, and tunnel port range
EXPOSE 80 443 2200-2300 8500-8600

ENTRYPOINT ["tini", "--"]
CMD ["tunnelctl", "endpoint", "--config", "/app/config/config.yaml"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:80/ || exit 0
