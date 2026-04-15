#!/bin/bash
# setup_pi.sh - Vault Ingestor Setup for Raspberry Pi

echo "=== Vault Ingestor: Setup for Raspberry Pi ==="

# 0. Instalar dependencias del sistema (para Pillow/Thumbnails)
echo "Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y libopenjp2-7 libtiff6 libjpeg-dev zlib1g-dev python3-venv

# 1. Verificar si existe .venv
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment (.venv)..."
    python3 -m venv .venv
else
    echo "Virtual environment (.venv) already exists."
fi

# 2. Activar entorno virtual
echo "Activating virtual environment..."
source .venv/bin/activate

# 3. Instalar dependencias
echo "Installing dependencies from requirements.txt..."
pip install --upgrade pip
pip install -r requirements.txt

# 4. Verificar instalación
echo "Running diagnosis..."
python diagnose_pi.py

echo ""
echo "=== Setup complete! ==="
echo "To run the bot, use:"
echo "  source .venv/bin/activate"
echo "  python app.py"
echo ""
