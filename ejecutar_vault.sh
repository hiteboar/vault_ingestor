#!/bin/bash
# Script de lanzamiento y configuración rápida para Vault Ingestor en Raspberry Pi

# Asegurar que operamos en el directorio del proyecto
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR" || exit

# Envolver toda la ejecución en un bloque para enviar la salida a la consola y al log
{
echo "=========================================="
echo "   Vault Ingestor: Sistema de Almacenaje"
echo "   Fecha: $(date)"
echo "=========================================="

echo "[*] Preparando permisos del sistema..."
sudo chown -R $USER:$USER "$PROJECT_DIR"
sudo chmod -R 775 "$PROJECT_DIR"

# Leer STORAGE_DIR del .env si existe
STORAGE_DIR="./vault_storage"
if [ -f ".env" ]; then
    ENV_STORAGE=$(grep "^STORAGE_DIR=" .env | cut -d '=' -f2)
    if [ -n "$ENV_STORAGE" ]; then
        STORAGE_DIR="$ENV_STORAGE"
    fi
fi

# Intentar dar permisos al STORAGE_DIR (Ruta absoluta o relativa)
case "$STORAGE_DIR" in
    /*) ;; # Es absoluta, la dejamos igual
    *) STORAGE_DIR="$PROJECT_DIR/$STORAGE_DIR" ;; # Es relativa
esac

if [ -d "$STORAGE_DIR" ]; then
    echo "[*] Aplicando permisos a la carpeta de almacenamiento configurada: $STORAGE_DIR"
    sudo chown -R $USER:$USER "$STORAGE_DIR" 2>/dev/null
    sudo chmod -R 775 "$STORAGE_DIR" 2>/dev/null
fi

# Permisos disco externo
if [ -d "/mnt/vault" ]; then
    echo "[*] Aplicando permisos a disco externo detectado en /mnt/vault..."
    sudo chown -R $USER:$USER "/mnt/vault" 2>/dev/null
    sudo chmod -R 775 "/mnt/vault" 2>/dev/null
fi

echo "[*] Gestionando el servicio vault_ingestor..."
SERVICE_NAME="vault_ingestor"

if systemctl list-units --type=service | grep -q "$SERVICE_NAME"; then
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo "[*] El servicio ya estaba corriendo. Reiniciando para aplicar posibles cambios..."
        sudo systemctl restart "$SERVICE_NAME"
    else
        echo "[*] Iniciando el servicio..."
        sudo systemctl start "$SERVICE_NAME"
    fi
else
    echo "[!] Advertencia: El servicio systemd ($SERVICE_NAME) no está instalado."
    echo "[*] Iniciando en segundo plano de forma manual..."
    pkill -f "python.*app.py" 2>/dev/null
    nohup .venv/bin/python app.py > /dev/null 2>&1 &
fi

echo "[*] Esperando a que el sistema esté listo (Cloudflare Tunnel)..."
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

print("\n[*] Consultando datos de emparejamiento...")
try:
    max_retries = 10
    for i in range(max_retries):
        try:
            resp = requests.get("http://localhost:8001/api/config", timeout=2)
            if resp.status_code == 200:
                auth_resp = requests.get("http://localhost:8001/api/auth/request", timeout=2)
                if auth_resp.status_code == 200:
                    data = auth_resp.json()
                    print("\n" + "="*50)
                    print("   ¡SISTEMA LISTO PARA CONECTAR!")
                    print("="*50)
                    print(f"   URL: {data['url']}")
                    print(f"   PIN: {data['pin']}")
                    print("="*50)
                    
                    try:
                        import qrcode
                        qr = qrcode.QRCode()
                        qr.add_data(json.dumps({"url": data["url"], "pin": data["pin"]}))
                        qr.print_ascii(invert=True)
                    except:
                        print("[!] No se pudo generar el QR de texto. Usa los datos de arriba.")
                    
                    break
        except Exception:
            time.sleep(2)
    else:
        print("[!] Tiempo de espera agotado. El servicio podría estar tardando en iniciar.")
        print("[*] Revisa 'app.log' para más detalles.")
except Exception as e:
    print(f"[!] Error conectando con la API: {e}")
EOF

echo ""
echo "[*] La terminal ya no está bloqueada. El sistema sigue corriendo en segundo plano."
echo "[*] Puedes cerrar esta ventana."
} 2>&1 | tee -a "$PROJECT_DIR/app.log"

