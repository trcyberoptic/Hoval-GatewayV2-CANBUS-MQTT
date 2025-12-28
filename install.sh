#!/bin/bash
# Hoval Gateway Installation Script for Debian Trixie
set -e

INSTALL_DIR="/opt/hoval-gateway"
LOG_DIR="/var/log/hoval-gateway"
SERVICE_USER="hoval"

echo "=== Hoval Gateway Installation ==="

# Check for root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo)"
    exit 1
fi

# Install dependencies
echo "Installing dependencies..."
apt-get update
apt-get install -y python3 python3-paho-mqtt

# Create service user
if ! id "$SERVICE_USER" &>/dev/null; then
    echo "Creating service user '$SERVICE_USER'..."
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi

# Create directories
echo "Creating directories..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$LOG_DIR"

# Copy files
echo "Installing application..."
cp hoval.py "$INSTALL_DIR/"
cp hoval_datapoints.csv "$INSTALL_DIR/"

# Set permissions
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
chown -R "$SERVICE_USER:$SERVICE_USER" "$LOG_DIR"
chmod 755 "$INSTALL_DIR"
chmod 644 "$INSTALL_DIR"/*.py "$INSTALL_DIR"/*.csv

# Install systemd service
echo "Installing systemd service..."
cp hoval-gateway.service /etc/systemd/system/
systemctl daemon-reload

# Setup log rotation
echo "Setting up log rotation..."
cat > /etc/logrotate.d/hoval-gateway << 'EOF'
/var/log/hoval-gateway/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 hoval hoval
    postrotate
        systemctl reload hoval-gateway > /dev/null 2>&1 || true
    endscript
}
EOF

echo ""
echo "=== Installation complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit configuration: sudo nano $INSTALL_DIR/hoval.py"
echo "  2. Enable service:     sudo systemctl enable hoval-gateway"
echo "  3. Start service:      sudo systemctl start hoval-gateway"
echo "  4. Check status:       sudo systemctl status hoval-gateway"
echo "  5. View logs:          tail -f $LOG_DIR/hoval.log"
