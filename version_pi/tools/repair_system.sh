#!/bin/bash
# Script to reinstall and repair environments and dependencies, and regenerate autorun

echo "=== Vault Ingestor: System Repair (Raspberry Pi) ==="

PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_DIR" || exit

echo "[1/5] Installing system base dependencies..."
sudo apt-get update
sudo apt-get install -y libopenjp2-7 libtiff6 libjpeg-dev zlib1g-dev python3-venv rustc cargo libffi-dev libssl-dev ffmpeg curl

# Install official Cloudflared for ARM (armv7/armhf)
if ! command -v cloudflared &> /dev/null; then
    echo "[*] Installing official Cloudflared for Raspberry Pi..."
    curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-armhf.deb
    sudo dpkg -i cloudflared.deb
    rm cloudflared.deb
fi

echo "[2/5] Regenerating virtual environment (Python)..."
if [ ! -d ".venv" ]; then
    echo "Creating .venv..."
    python3 -m venv .venv
fi
. .venv/bin/activate

# Compilation compatibility for Cryptography module on Python 3.13 (Raspberry OS Trixie)
export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1

echo "Updating libraries..."
pip install --upgrade pip
pip install -r requirements.txt
pip install pycloudflared

echo "[3/5] Verifying .env configuration..."
if [ ! -f ".env" ]; then
    echo "Creating initial .env..."
    cp .env.example .env
    # Force remote access on repair if it's a new system
    sed -i 's/ENABLE_REMOTE_ACCESS=false/ENABLE_REMOTE_ACCESS=true/g' .env
fi

echo "[4/5] Repairing Auto-Start Service (Systemd) for resilience..."
# Using Restart=always to ensure automatic recovery after crashes

USER_NAME=$USER
API_SERVICE_FILE="/tmp/vault_api.service"
BOT_SERVICE_FILE="/tmp/vault_bot.service"

echo "[*] Creating Vault API Service..."
cat <<EOF > "$API_SERVICE_FILE"
[Unit]
Description=Vault Ingestor API Service
After=network.target network-online.target
Wants=network-online.target

[Service]
User=$USER_NAME
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/.venv/bin/python $PROJECT_DIR/app.py --mode api
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "[*] Creating Vault Bot Service..."
cat <<EOF > "$BOT_SERVICE_FILE"
[Unit]
Description=Vault Ingestor Bot Service
After=network.target network-online.target
Wants=network-online.target

[Service]
User=$USER_NAME
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/.venv/bin/python $PROJECT_DIR/app.py --mode bot
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Clean up old combined service if it exists
sudo systemctl stop vault_ingestor 2>/dev/null
sudo systemctl disable vault_ingestor 2>/dev/null
sudo rm -f /etc/systemd/system/vault_ingestor.service

# Install new services
sudo mv "$API_SERVICE_FILE" /etc/systemd/system/vault_api.service
sudo mv "$BOT_SERVICE_FILE" /etc/systemd/system/vault_bot.service
sudo systemctl daemon-reload
sudo systemctl enable vault_api vault_bot

echo ""
echo "=== Repair Completed! ==="
echo "1. Vital dependencies and files have been restored."
echo "2. Systemd has been configured to auto-recover the application (Restart=always)."
echo ""
echo "[5/5] Proceeding to RESTART services in the background..."
echo "      (This operation may take a few seconds, please wait...)"
sudo systemctl restart vault_api
sudo systemctl restart vault_bot

echo ""
echo "[✔] Service restarted successfully."
echo "Remote tunnel and connection with the mobile App are being re-established."
echo "To get the new QR Code or check status, run:"
echo "   ./run_vault.sh"
