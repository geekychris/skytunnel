# tunnelctl agent - multi-arch (amd64, arm64 for Pi and Mac)
# Build context should be the repo root.

FROM --platform=$TARGETPLATFORM python:3.12-slim

ARG TARGETPLATFORM
ARG BUILDPLATFORM

LABEL maintainer="tunnelctl"
LABEL description="tunnelctl tunnel agent"
LABEL org.opencontainers.image.source="https://github.com/tunnelctl/tunnelctl"

WORKDIR /app

# Install system dependencies
# openssh-client for key management utilities
# tini for proper PID 1 signal handling
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    tini \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (cached layer)
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Copy application code
COPY src/ src/

# Re-install to pick up the actual source (not just deps)
RUN pip install --no-cache-dir .

# Copy default config
COPY config.example.yaml /app/config.example.yaml

# Create directories for volumes
RUN mkdir -p /app/config /root/.ssh && chmod 700 /root/.ssh

VOLUME ["/app/config", "/root/.ssh"]

# Web dashboard / API
EXPOSE 8080

# Use tini as init to handle signals properly
ENTRYPOINT ["tini", "--"]
CMD ["tunnelctl", "agent", "--config", "/app/config/config.yaml"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/status')" || exit 1
