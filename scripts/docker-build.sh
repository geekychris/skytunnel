#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# tunnelctl Docker Multi-Architecture Build Script
# ============================================================================
# Builds Docker images for:
#   - linux/amd64     (x86_64 servers, Intel Macs)
#   - linux/arm64     (Raspberry Pi 4/5, Apple Silicon Macs, ARM servers)
#
# Usage:
#   bash scripts/docker-build.sh              # Build + push multi-arch
#   bash scripts/docker-build.sh --local      # Build for current platform only
#   bash scripts/docker-build.sh --push       # Build + push to registry
#   bash scripts/docker-build.sh --tag v0.1.0 # Custom tag
# ============================================================================

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# --- Configuration ---
REGISTRY="${TUNNELCTL_REGISTRY:-}"    # e.g. ghcr.io/yourusername or docker.io/yourusername
IMAGE_PREFIX="${TUNNELCTL_IMAGE_PREFIX:-tunnelctl}"
TAG="latest"
PLATFORMS="linux/amd64,linux/arm64"
LOCAL_ONLY=false
PUSH=false
BUILDER_NAME="tunnelctl-builder"

# --- Parse arguments ---
while [[ $# -gt 0 ]]; do
    case $1 in
        --local)
            LOCAL_ONLY=true
            shift ;;
        --push)
            PUSH=true
            shift ;;
        --tag)
            TAG="$2"
            shift 2 ;;
        --registry)
            REGISTRY="$2"
            shift 2 ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --local       Build for current platform only (no buildx)"
            echo "  --push        Push images to registry after building"
            echo "  --tag TAG     Image tag (default: latest)"
            echo "  --registry R  Registry prefix (e.g. ghcr.io/user)"
            echo ""
            echo "Environment variables:"
            echo "  TUNNELCTL_REGISTRY       Default registry prefix"
            echo "  TUNNELCTL_IMAGE_PREFIX   Image name prefix (default: tunnelctl)"
            exit 0 ;;
        *)
            error "Unknown option: $1"
            exit 1 ;;
    esac
done

# --- Resolve image names ---
if [[ -n "$REGISTRY" ]]; then
    AGENT_IMAGE="${REGISTRY}/${IMAGE_PREFIX}-agent:${TAG}"
    ENDPOINT_IMAGE="${REGISTRY}/${IMAGE_PREFIX}-endpoint:${TAG}"
else
    AGENT_IMAGE="${IMAGE_PREFIX}-agent:${TAG}"
    ENDPOINT_IMAGE="${IMAGE_PREFIX}-endpoint:${TAG}"
fi

# --- Navigate to repo root ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

echo ""
echo -e "${BOLD}${CYAN}"
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║     tunnelctl Docker Build                   ║"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
info "Agent image:    $AGENT_IMAGE"
info "Endpoint image: $ENDPOINT_IMAGE"
if $LOCAL_ONLY; then
    info "Mode:           Local (no buildx)"
elif $PUSH; then
    info "Mode:           Multi-arch + push"
    info "Platforms:      $PLATFORMS"
else
    info "Mode:           Buildx (current platform)"
    info "Tip:            Use --push to build all platforms"
fi
echo ""

# ============================================================================
# Local build (no buildx, current platform only)
# ============================================================================
if $LOCAL_ONLY; then
    info "Building agent image..."
    docker build \
        -f docker/agent/Dockerfile \
        -t "$AGENT_IMAGE" \
        .
    success "Agent image built: $AGENT_IMAGE"

    info "Building endpoint image..."
    docker build \
        -f docker/endpoint/Dockerfile \
        -t "$ENDPOINT_IMAGE" \
        .
    success "Endpoint image built: $ENDPOINT_IMAGE"

    echo ""
    success "Local build complete!"
    echo ""
    echo "  Run agent:    docker run -d -p 8080:8080 -v \$(pwd)/config:/app/config -v ~/.ssh:/root/.ssh:ro $AGENT_IMAGE"
    echo "  Run endpoint: docker run -d -p 80:80 -p 443:443 -v \$(pwd)/config:/app/config $ENDPOINT_IMAGE"
    echo ""
    exit 0
fi

# ============================================================================
# Multi-architecture build with buildx
# ============================================================================

# --- Check Docker buildx ---
if ! docker buildx version &>/dev/null; then
    error "Docker buildx is required for multi-arch builds."
    echo "  Install: https://docs.docker.com/build/buildx/install/"
    echo "  Or use --local for single-platform builds."
    exit 1
fi

# --- Create/use buildx builder ---
if docker buildx inspect "$BUILDER_NAME" &>/dev/null; then
    info "Using existing builder: $BUILDER_NAME"
else
    info "Creating buildx builder: $BUILDER_NAME"
    docker buildx create \
        --name "$BUILDER_NAME" \
        --driver docker-container \
        --platform "$PLATFORMS" \
        --bootstrap
fi

docker buildx use "$BUILDER_NAME"

# --- Determine build action ---
if $PUSH; then
    if [[ -z "$REGISTRY" ]]; then
        error "Cannot push without a registry. Use --registry or set TUNNELCTL_REGISTRY."
        exit 1
    fi
    BUILD_ACTION="--push"
    BUILD_PLATFORMS="$PLATFORMS"
    info "Will push multi-arch images to registry"
else
    # Without --push, we can only --load for the current platform
    BUILD_ACTION="--load"
    BUILD_PLATFORMS=""
    info "Building for current platform only (use --push for multi-arch)"
    info "To build multi-arch and push: $0 --push --registry ghcr.io/youruser"
fi

# --- Build agent ---
PLATFORM_FLAG=""
if [[ -n "$BUILD_PLATFORMS" ]]; then
    PLATFORM_FLAG="--platform $BUILD_PLATFORMS"
fi

info "Building agent image..."
docker buildx build \
    --builder "$BUILDER_NAME" \
    $PLATFORM_FLAG \
    -f docker/agent/Dockerfile \
    -t "$AGENT_IMAGE" \
    $BUILD_ACTION \
    .

success "Agent image built: $AGENT_IMAGE"

# --- Build endpoint ---
info "Building endpoint image..."
docker buildx build \
    --builder "$BUILDER_NAME" \
    $PLATFORM_FLAG \
    -f docker/endpoint/Dockerfile \
    -t "$ENDPOINT_IMAGE" \
    $BUILD_ACTION \
    .

success "Endpoint image built: $ENDPOINT_IMAGE"

# --- Summary ---
echo ""
echo -e "${BOLD}${GREEN}"
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║          Build Complete!                     ║"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo "  Images built:"
echo "    $AGENT_IMAGE"
echo "    $ENDPOINT_IMAGE"
echo ""
if $PUSH; then
    echo "  Platforms: $PLATFORMS"
    echo ""
    echo "  Images pushed to registry."
    echo ""
    echo "  Pull on Raspberry Pi:  docker pull $AGENT_IMAGE"
    echo "  Pull on x86 server:    docker pull $ENDPOINT_IMAGE"
else
    echo "  Platform: current ($(uname -m))"
    echo ""
    echo "  To build multi-arch and push to a registry:"
    echo "    bash scripts/docker-build.sh --push --registry ghcr.io/yourusername"
fi

echo ""
echo "  Quick start:"
echo ""
echo "  # Agent (Starlink side)"
echo "  cd docker/agent"
echo "  mkdir -p config ssh"
echo "  cp ../../config.example.yaml config/config.yaml"
echo "  # Edit config/config.yaml, copy SSH keys to ssh/"
echo "  docker compose up -d"
echo ""
echo "  # Endpoint (public server)"
echo "  cd docker/endpoint"
echo "  mkdir -p config"
echo "  cp ../../config.example.yaml config/config.yaml"
echo "  # Edit config/config.yaml"
echo "  docker compose up -d"
echo ""
