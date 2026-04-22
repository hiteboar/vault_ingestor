#!/bin/bash
# Script para gestionar el servicio Vault Ingestor de forma interactiva

# Determinar el directorio base
PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_DIR" || exit

SERVICE_NAME="vault_ingestor"
IS_SYSTEMD=false

if systemctl list-units --type=service | grep -q "$SERVICE_NAME"; then
    IS_SYSTEMD=true
fi

check_running() {
    if [ "$IS_SYSTEMD" = true ]; then
        systemctl is-active --quiet "$SERVICE_NAME"
        return $?
    else
        # Comprobar si hay algo en el puerto 8001
        lsof -i:8001 > /dev/null 2>&1
        return $?
    fi
}

start_background() {
    echo "[*] Iniciando servicio en segundo plano..."
    if [ "$IS_SYSTEMD" = true ]; then
        sudo systemctl start "$SERVICE_NAME"
    else
        nohup ".venv/bin/python" "app.py" > "app.log" 2>&1 &
        echo $! > .vault_pid
    fi
}

stop_service() {
    echo "[*] Deteniendo servicio existente..."
    if [ "$IS_SYSTEMD" = true ]; then
        sudo systemctl stop "$SERVICE_NAME"
    else
        if [ -f .vault_pid ]; then
            kill $(cat .vault_pid) 2>/dev/null
            rm .vault_pid
        else
            pkill -f "python.*app.py"
        fi
    fi
}

# Lógica Principal
if check_running; then
    echo "⚠️  El servicio Vault Ingestor ya está en ejecución."
    read -p "¿Deseas reiniciarlo? (s/n): " choice
    case "$choice" in 
      s|S ) 
        stop_service
        sleep 2
        start_background
        ;;
      * ) 
        echo "[*] Manteniendo el servicio actual."
        ;;
    esac
else
    start_background
fi

echo "[✔] Proceso de gestión de servicio finalizado."
echo "Vault Ingestor está levantado."
echo "La conexión remota y la inicialización de red (Cloudflare) es gestionada de manera interna por app.py."
