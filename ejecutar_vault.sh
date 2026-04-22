#!/bin/bash
# Script de lanzamiento rápido para Vault Ingestor en Raspberry Pi

echo "=========================================="
echo "   Vault Ingestor: Sistema de Almacenaje"
echo "=========================================="

# Directorio base
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR" || exit

# 1. Asegurar que el servicio está corriendo en segundo plano
./version_pi/tools/start_service.sh

echo "[*] Esperando a que el sistema esté listo (Cloudflare Tunnel)..."
sleep 5

# 2. Obtener información de conexión y mostrar QR en terminal
# Usamos un pequeño script de python integrado para esto
.venv/bin/python <<EOF
import requests
import json
import time
import os

print("\n[*] Consultando datos de emparejamiento...")
try:
    # Intentar obtener la URL pública desde el sistema o la API
    # Primero esperamos a que la API responda
    max_retries = 10
    url = None
    for i in range(max_retries):
        try:
            resp = requests.get("http://localhost:8001/api/config", timeout=2)
            if resp.status_code == 200:
                # Intentar obtener el PIN y la URL real
                auth_resp = requests.get("http://localhost:8001/api/auth/request", timeout=2)
                if auth_resp.status_code == 200:
                    data = auth_resp.json()
                    print("\n" + "="*50)
                    print("   ¡SISTEMA LISTO PARA CONECTAR!")
                    print("="*50)
                    print(f"   URL: {data['url']}")
                    print(f"   PIN: {data['pin']}")
                    print("="*50)
                    
                    # Intentar imprimir QR en texto si qrcode está instalado
                    try:
                        import qrcode
                        qr = qrcode.QRCode()
                        qr.add_data(json.dumps({"url": data["url"], "pin": data["pin"]}))
                        qr.print_ascii(invert=True)
                    except:
                        print("[!] No se pudo generar el QR de texto. Usa los datos de arriba.")
                    
                    break
        except:
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
