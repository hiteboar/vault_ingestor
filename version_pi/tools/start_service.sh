#!/bin/bash
# Script para levantar manualmente el servicio Vault Ingestor
# Ejecutar desde la raspberry: ./version_pi/tools/start_service.sh

echo "=== Vault Ingestor: Arranque Manual de Emergencia ==="
echo "En un arranque normal, systemctl enciende automáticamente el servicio."

# Determinar el directorio base
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export STORAGE_DIR="$PROJECT_DIR/vault_storage"

cd "$PROJECT_DIR" || exit

if systemctl list-units --type=service | grep -q "vault_ingestor.service"; then
    echo "Reiniciando via Systemd para mantener supervisión..."
    sudo systemctl restart vault_ingestor
    sudo systemctl status vault_ingestor --no-pager
else
    echo "Systemd service no encontrado. Ejecutando de forma manual..."
     
    # En caso extremo, levantar directo
    nohup ".venv/bin/python" "version_pi/autorun_pi.py" > "app.log" 2>&1 &
    
    echo "Servicio levantado en background. PID: $!"
    echo "Logs están siendo emitidos a app.log"
fi

echo ""
echo "Vault Ingestor está levantado."
echo "La conexión remota y la inicialización de red (Cloudflare) es gestionada de manera interna por app.py."
