#!/bin/bash
# ==========================================================
#   Vault Ingestor: Automatic Installer (Linux/Raspberry Pi)
# ==========================================================

# Terminal colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

clear
echo -e "${BLUE}==========================================================${NC}"
echo -e "${BLUE}       VAULT INGESTOR: SERVER INSTALLER${NC}"
echo -e "${BLUE}==========================================================${NC}"
echo ""

# 1. Warnings and Requirements
echo -e "${YELLOW}[!] BEFORE CONTINUING, YOU WILL NEED:${NC}"
echo -e " 1. A path where you want to store your images and videos."
echo -e "    (Example: /mnt/external_drive/vault or ./vault_storage)"
echo ""
echo -e " 2. (Optional) A Cloudflare Token if you want persistent remote access."
echo -e "    If you don't have one, the system will use a free temporary URL."
echo ""
echo -e " 3. The installer will download dependencies like Python, libwebp, and ffmpeg."
echo -e "    Sudo permissions will be required."
echo ""

read -p "Do you want to continue with the installation? (y/n): " confirm
if [[ $confirm != "y" && $confirm != "Y" ]]; then
    echo -e "${RED}[!] Installation cancelled.${NC}"
    exit 1
fi

# 2. System dependencies installation
echo -e "\n${BLUE}[*] Installing system dependencies...${NC}"
sudo apt update
sudo apt install -y python3-venv python3-pip libwebp-dev ffmpeg curl

# 3. Data collection
echo -e "\n${BLUE}==========================================================${NC}"
echo -e "${BLUE}           SYSTEM CONFIGURATION${NC}"
echo -e "${BLUE}==========================================================${NC}"

# STORAGE_DIR
echo -e "\n${YELLOW}Where do you want to save your files?${NC}"
read -p "[Default: ./vault_storage]: " storage_dir
if [[ -z "$storage_dir" ]]; then
    storage_dir="./vault_storage"
fi

# ENABLE_REMOTE_ACCESS
echo -e "\n${YELLOW}Do you want to enable remote access (outside your home network)?${NC}"
read -p "(y/n) [Default: y]: " remote_confirm
if [[ -z "$remote_confirm" || $remote_confirm == "y" || $remote_confirm == "Y" ]]; then
    enable_remote="true"
    
    echo -e "\n${YELLOW}Do you have a persistent Cloudflare Token?${NC}"
    echo -e "If left empty, TryCloudflare will be used (random URL that changes on restart)."
    read -p "Token (optional): " cf_token
else
    enable_remote="false"
    cf_token=""
fi

# 4. .env file generation
echo -e "\n${BLUE}[*] Generating .env configuration file...${NC}"

cat <<EOF > .env
# Folder where files will be stored
STORAGE_DIR=$storage_dir

# Metadata log
META_LOG=$storage_dir/metadata.jsonl

# Maximum size per file (0 = no limit)
MAX_BYTES=0

# Allow compressed photos
ALLOW_COMPRESSED_PHOTOS=true

# Default context
DEFAULT_CONTEXT=default

# Remote Access Configuration
ENABLE_REMOTE_ACCESS=$enable_remote
CLOUDFLARE_TOKEN=$cf_token
PUBLIC_URL=
EOF

# 5. Python environment setup
echo -e "\n${BLUE}[*] Creating Python virtual environment...${NC}"
python3 -m venv .venv
source .venv/bin/activate

echo -e "\n${BLUE}[*] Installing project dependencies...${NC}"
pip install --upgrade pip
pip install -r requirements.txt

# 6. Prepare the execution script
chmod +x run_vault.sh

# 7. Finalization
echo -e "\n${GREEN}==========================================================${NC}"
echo -e "${GREEN}       INSTALLATION COMPLETED SUCCESSFULLY!${NC}"
echo -e "${GREEN}==========================================================${NC}"
echo ""
echo -e "${YELLOW}HOW TO START THE SYSTEM:${NC}"
echo -e " Execute the command: ${BLUE}./run_vault.sh${NC}"
echo ""
echo -e "${YELLOW}HOW TO LINK THE MOBILE APP:${NC}"
echo -e " 1. Open the Vault App on your mobile."
echo -e " 2. Run ./run_vault.sh on this server."
echo -e " 3. Scan the QR code that will appear on the screen."
echo ""
echo -e "${BLUE}Enjoy your personal Vault.${NC}"
echo ""
