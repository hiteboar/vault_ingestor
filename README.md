# Raspi Vault Ingestor 🛡️📦

A lightweight, personal **media ingestor and vault** designed for home servers, personal computers, or Raspberry Pi devices. This project allows you to capture, organize, and secure your files effortlessly via a Telegram Bot interface while maintaining 100% control over your data.

## 🚀 Key Features

- **Automated Organization**: Files are sorted by **Year/Month** by default.
- **Custom Folders (Contexts)**: Create specific directories for events, trips, or projects.
- **Deduplication**: Built-in hash-based detection to prevent storing identical files twice.
- **Telegram Interface**: Complete control through a robust set of bot commands.
- **Invitation System**: Securely invite other users to upload or access specific folders without granting full server access.
- **Secure Vault**: An isolated storage area for sensitive files with tagged retrieval.
- **Media Preview**: Quickly browse through images stored in any folder directly from Telegram.
- **Original Quality**: Toggle between original uncompressed documents and standard photo uploads.

---

## 📋 Requirements

- **Python 3.9+**
- **Git**
- **Telegram Bot Token** (from [@BotFather](https://t.me/botfather))

---

## 🛠️ Installation

### 1. Clone the repository
```bash
git clone https://github.com/your-username/vault-ingestor.git
cd vault-ingestor
```

### 2. Setup Virtual Environment
```bash
python -m venv venv
# Linux / macOS
source venv/bin/activate
# Windows
.\venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configuration
Create a `.env` file from the example:
```bash
cp .env.example .env
```

Edit your `.env` with the following variables:
- `TELEGRAM_BOT_TOKEN`: Your Bot Token from @BotFather.
- `STORAGE_DIR`: Absolute path where files will be stored.
- `ALLOWED_CHAT_IDS`: Comma-separated list of Telegram User IDs allowed to use the bot.
- `DEFAULT_CONTEXT`: Folder name for default uploads (e.g., `default`).
- `META_LOG`: (Optional) Path to the metadata journal file.
- `MAX_BYTES`: (Optional) Maximum file size in bytes (0 for no limit).
- `ALLOW_COMPRESSED_PHOTOS`: (Optional) Set to `true` to allow regular photo uploads by default.

---

## 🤖 Usage & Bot Commands

Start the bot:
```bash
python app.py
```

### Authorization & Sharing
| Command | Description |
|:--- |:--- |
| `/invite <folder>` | (Admin only) Generates a unique invitation code for a specific folder. |
| `/join <code>` | Use a code to gain access to a shared folder. |

### Folder Management
| Command | Description |
|:--- |:--- |
| `/setfolder <name>` | Switch to a specific folder. Creates it if it doesn't exist. |
| `/folder` | Show the currently active folder. |
| `/folders` | List all custom folders you have access to. |
| `/clearfolder` | Reset to the default structure. |

### File Retrieval & Media
| Command | Description |
|:--- |:--- |
| `/preview <folder> [pag]` | Browse thumbnails of images in a folder. |
| `/download <filename>` | Search and download a specific file. |
| `/downloadfolder <name>` | Export an entire folder as a `.zip` archive. |

### Security & Vault
| Command | Description |
|:--- |:--- |
| `/vaultadd <tag>` | Prepare to save the next file securely in the Vault under `<tag>`. |
| `/vaultget <tag>` | Retrieve a file from the Vault by its tag. |
| `/vaultlist` | List all secrets saved in the Vault. |
| `/vaultdelete <tag>` | Remove a secret from the Vault (requires confirmation). |
| `/delete <path>` | Delete a file or folder in the general storage (requires confirmation). |

### System
| Command | Description |
|:--- |:--- |
| `/original on\|off` | Toggle requirement for uncompressed "File" uploads. |
| `/help` | Display command list and current status. |

---

## 📂 Storage Structure

By default, the server organizes files as follows:
```text
storage/
 ├── 2026/
 │   ├── 03/
 │   │   └── file.jpg
 ├── trips/           <-- Custom Folder
 │   └── vacation.mp4
 └── _vault/          <-- Isolated Secrets
     └── passport.pdf
```

---

## ⚙️ Running as a Service (Linux)

To keep the ingestor running in the background, create a systemd service:

1. Create `/etc/systemd/system/vault.service`:
```ini
[Unit]
Description=Vault Ingestor Bot
After=network.target

[Service]
User=your-user
WorkingDirectory=/path/to/vault-ingestor
ExecStart=/path/to/vault-ingestor/venv/bin/python app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

2. Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable vault.service
sudo systemctl start vault.service
```

---

## 🔄 Updating

To update to the latest version of the code:

```bash
# Get the latest changes
git pull

# Update dependencies if needed
pip install -r requirements.txt

# Restart the service (if using systemd)
sudo systemctl restart vault.service
```

---

## 🗑️ Uninstalling

To completely remove the project:

1. **Stop and remove the service** (if installed):
```bash
sudo systemctl stop vault.service
sudo systemctl disable vault.service
sudo rm /etc/systemd/system/vault.service
sudo systemctl daemon-reload
```

2. **Remove the project directory**:
```bash
cd ..
rm -rf vault-ingestor
```

*(Note: This will not delete your `STORAGE_DIR` unless it was located inside the project folder.)*

---

## 📄 License

This project is open-source under the MIT License. See `LICENSE` for details.
