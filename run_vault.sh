#!/bin/bash
# Launch and quick config script for Vault Ingestor on Raspberry Pi

# Ensure we operate in the project directory
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR" || exit

echo "=========================================="
echo "   Vault Ingestor: Storage System"
echo "   Date: $(date)"
echo "=========================================="

echo "[*] Preparing system permissions..."
sudo chown -R $USER:$USER "$PROJECT_DIR"
sudo chmod -R 775 "$PROJECT_DIR"

# Read STORAGE_DIR from .env if it exists
STORAGE_DIR="./vault_storage"
if [ -f ".env" ]; then
    ENV_STORAGE=$(grep "^STORAGE_DIR=" .env | cut -d '=' -f2)
    if [ -n "$ENV_STORAGE" ]; then
        STORAGE_DIR="$ENV_STORAGE"
    fi
fi

# Try to apply permissions to STORAGE_DIR (Absolute or relative path)
case "$STORAGE_DIR" in
    /*) ;; # It's absolute, leave it as is
    *) STORAGE_DIR="$PROJECT_DIR/$STORAGE_DIR" ;; # It's relative
esac

if [ -d "$STORAGE_DIR" ]; then
    echo "[*] Applying permissions to configured storage folder: $STORAGE_DIR"
    sudo chown -R $USER:$USER "$STORAGE_DIR" 2>/dev/null
    sudo chmod -R 775 "$STORAGE_DIR" 2>/dev/null
fi

# External disk permissions
if [ -d "/mnt/vault" ]; then
    echo "[*] Applying permissions to detected external disk in /mnt/vault..."
    sudo chown -R $USER:$USER "/mnt/vault" 2>/dev/null
    sudo chmod -R 775 "/mnt/vault" 2>/dev/null
fi

echo "[*] Managing vault services..."
API_SERVICE="vault_api"
BOT_SERVICE="vault_bot"

# Restart API
if systemctl list-unit-files | grep -q "$API_SERVICE"; then
    echo "[*] Restarting API service..."
    sudo systemctl restart "$API_SERVICE"
else
    echo "[!] Warning: systemd service ($API_SERVICE) is not installed."
    pkill -f "python.*app.py --mode api" 2>/dev/null
    nohup .venv/bin/python app.py --mode api >> "$PROJECT_DIR/api.log" 2>&1 &
fi

# Ensure Bot is running
if systemctl list-unit-files | grep -q "$BOT_SERVICE"; then
    if ! systemctl is-active --quiet "$BOT_SERVICE"; then
        echo "[*] Starting Bot service..."
        sudo systemctl start "$BOT_SERVICE"
    fi
else
    if ! pgrep -f "python.*app.py --mode bot" > /dev/null; then
        echo "[*] Starting Bot manually in the background..."
        nohup .venv/bin/python app.py --mode bot >> "$PROJECT_DIR/bot.log" 2>&1 &
    fi
fi

echo "[*] Waiting for the system to be ready (Cloudflare Tunnel)..."
sleep 6

if [ -f ".venv/bin/python" ]; then
    PYTHON_EXE=".venv/bin/python"
else
    PYTHON_EXE="python3"
fi

$PYTHON_EXE <<EOF
import requests
import json
import time

print("\n[*] Fetching pairing data...")
try:
    max_retries = 15
    for i in range(max_retries):
        try:
            resp = requests.get("http://localhost:8001/api/config", timeout=2)
            if resp.status_code == 200:
                config_data = resp.json()
                remote_enabled = config_data.get("ENABLE_REMOTE_ACCESS", "false").lower() == "true"
                
                # Read recovery token if exists
                recovery_param = ""
                try:
                    with open("vault_internal/.recovery_token", "r") as f:
                        recovery_param = f"?recovery={f.read().strip()}"
                except:
                    pass
                    
                auth_resp = requests.get(f"http://localhost:8001/api/auth/request{recovery_param}", timeout=2)
                
                if auth_resp.status_code == 403:
                    print("\n" + "="*50)
                    print("   [!] ADMIN DEVICE ALREADY LINKED")
                    print("="*50)
                    print("   You already have a mobile device paired as admin.")
                    print("   If you want to invite more users, do it from the App.")
                    print("\n   Lost access on your primary mobile?")
                    print("   To reset linkings, run this command:")
                    print("   rm -rf /mnt/vault/.vault/devices.json")
                    print("   (Or look for the .vault/devices.json file in your STORAGE_DIR)")
                    print("="*50)
                    break
                    
                elif auth_resp.status_code == 200:
                    data = auth_resp.json()
                    
                    # Detect if the URL is remote (not local)
                    is_remote_url = not any(local in data['url'] for local in ["localhost", "127.0.0.1", "192.168.", "10."])
                    if remote_enabled and not is_remote_url and i < (max_retries - 2):
                        print(f"[*] Server is alive but remote tunnel is still being established. Waiting... ({i+1}/{max_retries})")
                        time.sleep(3)
                        continue
                        
                    print("\n" + "="*50)
                    print("   SYSTEM READY TO CONNECT!")
                    print("="*50)
                    
                    if data.get("recovered"):
                        print("   [i] Recovery Mode: Cloudflare URL updated.")
                        print("       Scan this QR to reconnect your mobile.")
                        print("-" * 50)
                        
                    print(f"   URL: {data['url']}")
                    print(f"   PIN: {data['pin']}")
                    print("="*50)
                    
                    try:
                        import qrcode
                        qr = qrcode.QRCode()
                        qr.add_data(json.dumps({"url": data["url"], "pin": data["pin"]}))
                        qr.print_ascii(invert=True)
                    except:
                        print("[!] Could not generate text QR. Use the data above.")
                    
                    break
        except Exception:
            time.sleep(2)
    else:
        print("[!] Timeout. The service might be taking too long to start.")
        print("[*] Check 'app.log' for more details.")
except Exception as e:
    print(f"[!] Error connecting to API: {e}")
EOF

echo ""
echo "[*] Terminal is no longer blocked. The system continues running in the background."
echo "[*] You can close this window."
