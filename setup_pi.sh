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
    # Ajustar paths en el service unit
    WORKING_DIR=$(pwd)
    VENV_PYTHON="${WORKING_DIR}/.venv/bin/python"
    
    # Crear el archivo systemd con los paths correctos
    cat > vault_ingestor.service << EOL
[Unit]
Description=Vault Ingestor Bot Service
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=${WORKING_DIR}
ExecStart=${VENV_PYTHON} app.py
Restart=always
RestartSec=10
StandardOutput=inherit
StandardError=inherit

[Install]
WantedBy=multi-user.target
EOL

    echo "💾 Archivo 'vault_ingestor.service' generado."
    echo "Para habilitarlo ahora mismo, ejecuta:"
    echo "  sudo cp vault_ingestor.service /etc/systemd/system/"
    echo "  sudo systemctl daemon-reload"
    echo "  sudo systemctl enable vault_ingestor.service"
    echo "  sudo systemctl start vault_ingestor.service"
fi

echo ""
echo "=== Setup complete! ==="
