# Raspi Vault Ingestor - Core 🛡️📦

A lightweight, personal **media ingestor and vault core** designed for home servers, personal computers, or Raspberry Pi devices. This is the **Base Engine** that provides storage logic, deduplication, and a REST API for management.

## 📂 Project Structure

The project is organized by flavors to support different use cases:

### 1. **Core Engine** (Root)
The heart of the system. Contains the API (`api/`) and the storage logic (`core/`).
- `app.py`: Universal starter for the backend API.
- `.env.example`: Template for manual configuration.

### 2. **Version: Raspberry Pi** (`/version_pi`)
Optimized for home servers and low-power devices.
- `setup_pi.sh`: Intelligent installer for Linux environments.
- `diagnose_pi.py`: Hardware and permission diagnostic tool.

### 3. **Version: Windows Desktop** (`/version_desktop`)
A user-friendly version with a native dashboard.
- `launcher.py`: Automatic installer and updater (GitHub integration).
- `console_ui.py`: Premium management console with system monitoring.

---

## 🚀 Getting Started

### Standard (API Only)
```bash
python app.py
```

### Windows Desktop (Auto-setup)
Run `python version_desktop/launcher.py` to start the automatic installation and dashboard.

### Raspberry Pi (CLI)
Run `bash version_pi/setup_pi.sh` for guided terminal setup.

---

## 🌐 API Endpoints
- `GET /api/items`: List metadata of stored files.
- `GET /api/system/status`: Real-time storage, CPU, and RAM telemetry.
- `POST /api/config`: Visual configuration bridge.

---

## 📄 License
MIT License. See `LICENSE` for details.

