# Raspi Vault Ingestor - Core 🛡️📦

A lightweight, personal **media ingestor and vault core** designed for home servers, personal computers, or Raspberry Pi devices. This is the **Core Engine** that provides storage logic, deduplication, and a REST API for management.

> [!NOTE]
> This branch (`main`) contains only the core engine and API. For the Telegram Bot or AI Agent features, please check their respective branches.

## 🚀 Key Features

- **Automated Organization**: Files are sorted by **Year/Month** by default.
- **Custom Folders (Contexts)**: Create specific directories for events, trips, or projects.
- **Deduplication**: Built-in hash-based detection to prevent storing identical files twice.
- **REST API**: A FastAPI backend to consult metadata and retrieve media files.
- **Atomic Operations**: Secure file writing to prevent data corruption.
- **Core Setup Wizard**: A simple interactive tool to configure storage paths and API settings.

---

## 📋 Requirements

- **Python 3.9+**
- **Git**

---

## 🛠️ Installation

### 1. Clone the repository
```bash
git clone https://github.com/your-username/vault-ingestor.git
cd vault-ingestor
```

### 2. Run the Core Setup
The project includes a smart wizard that handles virtual environment creation and configuration:
```bash
bash setup_pi.sh
```
*Note: This script will install dependencies and guide you through creating your `.env` file.*

---

## 🌐 API & Usage

Start the API service:
```bash
python app.py
```
By default, the API will be available at `http://localhost:8000`.

### Endpoints
- `GET /api/items`: List all ingested files and their metadata.
- `GET /api/media/{path}`: Access a specific file.

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

To keep the API running in the background, you can use the generated `vault_ingestor.service` file or create one manually with `systemd`.

---

## 📄 License

This project is open-source under the MIT License. See `LICENSE` for details.
