#!/bin/bash
# Script para reinstalar y reparar entornos y dependencias, y regenerar el autorun

echo "=== Vault Ingestor: Reparación de Sistema (Raspberry Pi) ==="

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_DIR" || exit

echo "[1/4] Instalando dependencias base del sistema..."
sudo apt-get update
sudo apt-get install -y libopenjp2-7 libtiff6 libjpeg-dev zlib1g-dev python3-venv rustc cargo libffi-dev libssl-dev

echo "[2/4] Regenerando entorno virtual (Python)..."
if [ ! -d ".venv" ]; then
    echo "Creando .venv..."
    python3 -m venv .venv
fi
source .venv/bin/activate

echo "Actualizando librerías..."
pip install --upgrade pip
pip install -r requirements.txt
pip install pycloudflared

echo "[3/4] Reparando Servicio de Auto-Arrranque (Systemd) para resiliencia..."
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

echo "[4/4] Restaurando el Servicio..."
sudo systemctl restart vault_ingestor

echo ""
echo "=== Reparación Completada! ==="
echo "1. Systemd reiniciará automáticamente la aplicación si sufre un error (Restart=always)."
echo "2. El control de conectividad remoto y los túneles a la app mobile se restaurarán apenas inicie el código en app.py."
echo "Puedes validar que todo funcionó correctamente con:"
echo "   python version_pi/tools/check_system.py"
