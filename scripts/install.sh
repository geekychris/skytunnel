#!/usr/bin/env bash
set -euo pipefail

echo "=== tunnelctl Installer ==="

# Check Python version
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 is required (>= 3.11)"
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Python version: $PY_VERSION"

# Install the package
echo "Installing tunnelctl..."
pip install -e .

# Copy example config if none exists
if [[ ! -f config.yaml ]]; then
    cp config.example.yaml config.yaml
    echo "Created config.yaml from example. Edit it with your settings."
fi

# Set up SSH keys if needed
if [[ ! -f ~/.ssh/tunnel_key ]]; then
    echo ""
    read -p "Generate SSH tunnel key? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        bash scripts/setup-keys.sh
    fi
fi

echo ""
echo "Installation complete!"
echo ""
echo "Usage:"
echo "  tunnelctl agent     - Start the tunnel agent (Starlink side)"
echo "  tunnelctl endpoint  - Start the endpoint service (public server)"
echo "  tunnelctl status    - Check tunnel statuses"
echo "  tunnelctl --help    - See all commands"
