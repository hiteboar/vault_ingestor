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
- `console_ui.py`: Premium management console with system monitoring and mobile pairing QR.

### 4. **Version: Mobile App** (`/vault_mobile`)
Android application developed in React Native (Expo). Found in the `MobileApp` branch.
- `App.js`: Minimalist dark-mode dashboard and gallery.
- `api.js`: Secure communication service with token storage.

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

## 📱 Mobile App Development (`MobileApp` branch)

This branch contains the React Native project for the Android App.

### Prerequisites
- **Node.js**: Version 18.0 or higher.
- **Expo Go**: Download it from the Google Play Store on your mobile device.

### Setup & Running
1. Navigate to the mobile folder:
   ```bash
   cd vault_mobile
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the development server:
   ```bash
   npx expo start
   ```
4. Scan the QR code displayed in the terminal using the **Expo Go** app on your phone.

### Linking your Device
To connect your phone to the server:
1. Open the **Management Console** on your desktop.
2. Go to the **"Vincular App Móvil"** tab.
3. In the mobile app, enter the **Server URL** and the **6-digit PIN** displayed on your desktop.

---

## 🌐 API Endpoints
- `GET /api/items`: List metadata of stored files.
- `GET /api/system/status`: Real-time storage, CPU, and RAM telemetry.
- `POST /api/config`: Visual configuration bridge.

---

## 📄 License
MIT License. See `LICENSE` for details.

