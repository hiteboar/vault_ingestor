#!/bin/bash
# Script para reinstalar y reparar entornos y dependencias, y regenerar el autorun

echo "=== Vault Ingestor: Reparación de Sistema (Raspberry Pi) ==="

PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_DIR" || exit

echo "[1/5] Instalando dependencias base del sistema..."
sudo apt-get update
sudo apt-get install -y libopenjp2-7 libtiff6 libjpeg-dev zlib1g-dev python3-venv rustc cargo libffi-dev libssl-dev ffmpeg curl

# Instalar Cloudflared oficial para ARM (armv7/armhf)
if ! command -v cloudflared &> /dev/null; then
    echo "[*] Instalando Cloudflared oficial para Raspberry Pi..."
    curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-armhf.deb
    sudo dpkg -i cloudflared.deb
    rm cloudflared.deb
fi

echo "[2/5] Regenerando entorno virtual (Python)..."
if [ ! -d ".venv" ]; then
    echo "Creando .venv..."
    python3 -m venv .venv
fi
. .venv/bin/activate

# Compatibilidad de compilacion para módulo Cryptography en Python 3.13 (Raspberry OS Trixie)
export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1

echo "Actualizando librerías..."
pip install --upgrade pip
pip install -r requirements.txt
pip install pycloudflared

echo "[3/5] Verificando configuración .env..."
if [ ! -f ".env" ]; then
    echo "Creando .env inicial..."
    cp .env.example .env
    # Forzar acceso remoto en la reparación si es un sistema nuevo
    sed -i 's/ENABLE_REMOTE_ACCESS=false/ENABLE_REMOTE_ACCESS=true/g' .env
fi

echo "[4/5] Reparando Servicio de Auto-Arrranque (Systemd) para resiliencia..."
# Usamos Restart=always para garantizar que se recupere automáticamente ante caídas

USER_NAME=$USER
SERVICE_FILE="/tmp/vault_ingestor.service"

cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=Vault Ingestor API Supervisor
After=network.target network-online.target
Wants=network-online.target

[Service]
User=$USER_NAME
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/.venv/bin/python $PROJECT_DIR/version_pi/autorun_pi.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo mv "$SERVICE_FILE" /etc/systemd/system/vault_ingestor.service
sudo systemctl daemon-reload
sudo systemctl enable vault_ingestor

echo ""
echo "=== Reparación Completada! ==="
echo "1. Dependencias y archivos vitales han sido restaurados."
echo "2. Systemd ha sido configurado para autorecuperar la aplicación (Restart=always)."
echo ""
echo "[5/5] Procediendo al REINICIO del servicio en segundo plano..."
echo "      (Esta operación puede tardar unos segundos, por favor espera...)"
sudo systemctl restart vault_ingestor

echo ""
echo "[✔] Servicio reiniciado con éxito."
echo "El túnel remoto y la conexión con la App móvil se están restableciendo."
echo "Para obtener el nuevo Código QR o ver el estado, ejecuta:"
echo "   ./ejecutar_vault.sh"
