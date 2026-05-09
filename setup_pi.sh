#!/bin/bash
# setup_pi.sh - Wrapper for the Smart Setup Wizard

cat << "EOF"
==========================================
    Vault Ingestor - Raspberry Pi Setup
==========================================
EOF

# 1. Crear entorno virtual (.venv) si no existe
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment (.venv)..."
    python -m venv .venv
else
    echo "Virtual environment (.venv) already exists."
fi

# 2. Activar entorno virtual
echo "Activating virtual environment..."
source .venv/bin/activate

# 3. Lanzar el asistente interactivo (Python)
python setup.py

# 4. Ofrecer instalar el servicio systemd
echo ""
read -p "❓ ¿Deseas instalar el servicio systemd para arranque automático? (y/n): " install_service
if [[ "$install_service" == "y" || "$install_service" == "Y" ]]; then
    # Ajustar paths en los service units
    WORKING_DIR=$(pwd)
    VENV_PYTHON="${WORKING_DIR}/.venv/bin/python"
    USER_NAME=$(whoami)
    
    # 1. Servicio para la API (Almacenamiento)
    cat > vault_api.service << EOL
[Unit]
Description=Vault Ingestor API Service
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${USER_NAME}
WorkingDirectory=${WORKING_DIR}
ExecStart=${VENV_PYTHON} app.py --mode api
Restart=always
RestartSec=10
StandardOutput=inherit
StandardError=inherit

[Install]
WantedBy=multi-user.target
EOL

    # 2. Servicio para el Bot (Controlador)
    cat > vault_bot.service << EOL
[Unit]
Description=Vault Ingestor Bot Service
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${USER_NAME}
WorkingDirectory=${WORKING_DIR}
ExecStart=${VENV_PYTHON} app.py --mode bot
Restart=always
RestartSec=10
StandardOutput=inherit
StandardError=inherit

[Install]
WantedBy=multi-user.target
EOL

    echo "💾 Archivos 'vault_api.service' y 'vault_bot.service' generados."
    echo "Para habilitarlos ahora mismo, ejecuta:"
    echo "  sudo cp vault_api.service vault_bot.service /etc/systemd/system/"
    echo "  sudo systemctl daemon-reload"
    echo "  sudo systemctl enable vault_api.service vault_bot.service"
    echo "  sudo systemctl start vault_api.service vault_bot.service"
fi

echo ""
echo "=== Setup complete! ==="
