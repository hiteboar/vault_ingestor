#!/bin/bash
# =========================================================================
#   Vault Ingestor: Unified Smart Installer & Repair Utility (Linux/Pi)
# =========================================================================

# Terminal colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

clear
echo -e "${BLUE}==========================================================${NC}"
echo -e "${BLUE}       VAULT INGESTOR: UNIFIED INSTALL & REPAIR SYSTEM${NC}"
echo -e "${BLUE}==========================================================${NC}"
echo ""

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR" || exit

# 1. Detection of pre-existing installation
MODE="install"
if [ -f ".env" ]; then
    echo -e "${YELLOW}[!] Se ha detectado una instalación previa (.env ya existe).${NC}"
    echo -e "Selecciona una opción:"
    echo -e " 1) ${GREEN}Reparar / Actualizar sistema${NC} (Reinstala dependencias de forma limpia y recrea el arranque de systemd, manteniendo tus datos y .env)"
    echo -e " 2) ${RED}Reconfiguración completa${NC} (Vuelve a preguntar las opciones y sobrescribe tu .env actual)"
    echo ""
    read -p "Elige una opción (1/2) [Por defecto: 1]: " env_option
    if [[ "$env_option" == "2" ]]; then
        MODE="install"
    else
        MODE="repair"
    fi
fi

# 2. Stop active services before doing anything to avoid pip corruption and concurrent access
echo -e "\n${BLUE}[*] Deteniendo servicios activos para evitar bloqueos y corrupción...${NC}"
sudo systemctl stop vault_api vault_bot 2>/dev/null
pkill -f "python.*app.py" 2>/dev/null

# 3. If in install mode, collect new configuration variables
if [ "$MODE" == "install" ]; then
    echo -e "\n${YELLOW}[!] ANTES DE CONTINUAR, NECESITARÁS:${NC}"
    echo -e " 1. La ruta donde deseas almacenar tus fotos y vídeos."
    echo -e "    (Ejemplo: /mnt/vault_storage o ./vault_storage)"
    echo -e " 2. (Opcional) Un token de Cloudflare si deseas acceso persistente global."
    echo ""
    read -p "¿Deseas continuar con la instalación? (y/n): " confirm
    if [[ $confirm != "y" && $confirm != "Y" ]]; then
        echo -e "${RED}[!] Instalación cancelada.${NC}"
        exit 1
    fi

    echo -e "\n${BLUE}==========================================================${NC}"
    echo -e "${BLUE}           CONFIGURACIÓN DEL SISTEMA VAULT${NC}"
    echo -e "${BLUE}==========================================================${NC}"

    # STORAGE_DIR
    echo -e "\n${YELLOW}¿Dónde deseas almacenar tus archivos?${NC}"
    read -p "[Por defecto: ./vault_storage]: " storage_dir
    if [[ -z "$storage_dir" ]]; then
        storage_dir="./vault_storage"
    fi

    # ENABLE_REMOTE_ACCESS
    echo -e "\n${YELLOW}¿Deseas habilitar el acceso remoto seguro (fuera de casa)?${NC}"
    read -p "(y/n) [Por defecto: y]: " remote_confirm
    if [[ -z "$remote_confirm" || $remote_confirm == "y" || $remote_confirm == "Y" ]]; then
        enable_remote="true"
        echo -e "\n${YELLOW}¿Tienes un token persistente de Cloudflare?${NC}"
        echo -e "Si lo dejas en blanco, se utilizará TryCloudflare (URL temporal aleatoria)."
        read -p "Token (opcional): " cf_token
    else
        enable_remote="false"
        cf_token=""
    fi

    # Generate .env
    echo -e "\n${BLUE}[*] Generando archivo de configuración .env...${NC}"
    cat <<EOF > .env
# Carpeta base de almacenamiento
STORAGE_DIR=$storage_dir

# Registro de metadatos
META_LOG=$storage_dir/metadata.jsonl

# Tamaño máximo por archivo (0 = sin límite)
MAX_BYTES=0

# Permitir fotos comprimidas
ALLOW_COMPRESSED_PHOTOS=true

# Contexto por defecto
DEFAULT_CONTEXT=default

# Configuración de Acceso Remoto (Cloudflare)
ENABLE_REMOTE_ACCESS=$enable_remote
CLOUDFLARE_TOKEN=$cf_token
PUBLIC_URL=
EOF
else
    echo -e "\n${GREEN}[✔] Modo Reparación/Actualización activado. Se conservará la configuración de .env.${NC}"
fi

# 4. System resource and Architecture Detection
USER_NAME=$(logname 2>/dev/null || echo $USER)
ARCH=$(uname -m)
TOTAL_RAM=$(free -m 2>/dev/null | awk '/^Mem:/{print $2}')

echo -e "\n${BLUE}[*] Información del Sistema:${NC}"
echo -e "  - Arquitectura: ${GREEN}$ARCH${NC}"
echo -e "  - Usuario activo: ${GREEN}$USER_NAME${NC}"
if [ -n "$TOTAL_RAM" ]; then
    echo -e "  - Memoria RAM: ${GREEN}${TOTAL_RAM} MB${NC}"
    if [ "$TOTAL_RAM" -lt 900 ]; then
        echo -e "${YELLOW}[!] Se ha detectado memoria RAM baja (< 1GB).${NC}"
        echo -e "    Si la instalación de dependencias falla, asegúrate de activar memoria Swap."
        echo -e "    Ejemplo: sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile"
    fi
fi

# 5. Base System Dependencies Installation
echo -e "\n${BLUE}[*] Instalando/Actualizando dependencias base del sistema...${NC}"
sudo apt-get update
# Robust installation for Bullseye & Bookworm OS versions
sudo apt-get install -y libopenjp2-7 libtiff5 libtiff6 libjpeg-dev zlib1g-dev python3-venv rustc cargo libffi-dev libssl-dev ffmpeg curl 2>/dev/null || \
sudo apt-get install -y libopenjp2-7 libjpeg-dev zlib1g-dev python3-venv rustc cargo libffi-dev libssl-dev ffmpeg curl

# 6. Official Cloudflared Binary Installation (32/64-bit aware)
if ! command -v cloudflared &> /dev/null; then
    echo -e "\n${BLUE}[*] Descargando e instalando Cloudflared oficial para tu arquitectura...${NC}"
    if [[ "$ARCH" == "aarch64" ]]; then
        CF_DEB="cloudflared-linux-arm64.deb"
    else
        CF_DEB="cloudflared-linux-armhf.deb"
    fi
    curl -L --output cloudflared.deb "https://github.com/cloudflare/cloudflared/releases/latest/download/$CF_DEB"
    sudo dpkg -i cloudflared.deb
    rm cloudflared.deb
fi

# 7. Python Virtual Environment Setup & Clean Up
echo -e "\n${BLUE}[*] Regenerando entorno virtual de Python (.venv) limpio...${NC}"
if [ -d ".venv" ]; then
    rm -rf .venv
fi
python3 -m venv .venv
source .venv/bin/activate

# Cryptography compilation flag compatibility (prevents rust compile errors on Pi)
export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1

echo -e "\n${BLUE}[*] Instalando requerimientos de Python (esto puede tardar unos minutos)...${NC}"
pip install --upgrade pip
pip install -r requirements.txt
pip install pycloudflared

# 8. Setup Auto-Start systemd Services
echo -e "\n${BLUE}[*] Registrando servicios de inicio automático (systemd)...${NC}"
API_SERVICE_FILE="/tmp/vault_api.service"
BOT_SERVICE_FILE="/tmp/vault_bot.service"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"

cat <<EOF > "$API_SERVICE_FILE"
[Unit]
Description=Vault Ingestor API Service
After=network.target network-online.target
Wants=network-online.target

[Service]
User=$USER_NAME
WorkingDirectory=$PROJECT_DIR
ExecStart=$PYTHON_BIN $PROJECT_DIR/app.py --mode api
Environment=VAULT_NO_AUTOINSTALL=true
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target
EOF

cat <<EOF > "$BOT_SERVICE_FILE"
[Unit]
Description=Vault Ingestor Bot Service
After=network.target network-online.target
Wants=network-online.target

[Service]
User=$USER_NAME
WorkingDirectory=$PROJECT_DIR
ExecStart=$PYTHON_BIN $PROJECT_DIR/app.py --mode bot
Environment=VAULT_NO_AUTOINSTALL=true
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target
EOF

# Clean up legacy auto-start files
sudo systemctl stop vault_ingestor 2>/dev/null
sudo systemctl disable vault_ingestor 2>/dev/null
sudo rm -f /etc/systemd/system/vault_ingestor.service

# Move new service units and register them
sudo mv "$API_SERVICE_FILE" /etc/systemd/system/vault_api.service
sudo mv "$BOT_SERVICE_FILE" /etc/systemd/system/vault_bot.service
sudo systemctl daemon-reload
sudo systemctl enable vault_api vault_bot

# 9. Grant necessary runner permissions
chmod +x "$PROJECT_DIR/run_vault.sh"

# 10. Start the application services in background
echo -e "\n${BLUE}[*] Iniciando servicios en segundo plano...${NC}"
sudo systemctl start vault_api
sudo systemctl start vault_bot

echo -e "\n${GREEN}==========================================================${NC}"
echo -e "${GREEN}       ¡PROCESO COMPLETADO CON ÉXITO!${NC}"
echo -e "${GREEN}==========================================================${NC}"
echo ""
echo -e "El sistema se encuentra en funcionamiento y configurado de forma resiliente."
echo ""
echo -e "${YELLOW}CÓMO INICIAR / VER EL CÓDIGO QR DE VINCULACIÓN:${NC}"
echo -e " Ejecuta en consola el comando: ${BLUE}./run_vault.sh${NC}"
echo ""
echo -e "Este comando te mostrará los datos de emparejamiento móvil (Código QR y PIN)"
echo -e "mientras vigila el estado de ejecución."
echo ""
echo -e "${BLUE}¡Disfruta de tu nube privada descentralizada Vault!${NC}"
echo ""
