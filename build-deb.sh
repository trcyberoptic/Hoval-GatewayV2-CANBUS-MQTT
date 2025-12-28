#!/bin/bash
# Build Debian package for Hoval Gateway
set -e

echo "=== Building Hoval Gateway Debian Package ==="

# Check for required tools
if ! command -v dpkg-buildpackage &> /dev/null; then
    echo "Error: dpkg-buildpackage not found. Install with:"
    echo "  sudo apt-get install build-essential debhelper devscripts"
    exit 1
fi

# Make rules executable
chmod +x debian/rules

# Build the package
dpkg-buildpackage -us -uc -b

echo ""
echo "=== Build complete ==="
echo "Package created in parent directory:"
ls -la ../hoval-gateway_*.deb 2>/dev/null || echo "Check parent directory for .deb file"
