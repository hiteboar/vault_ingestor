# Raspi Vault Storage

A lightweight **local file storage system** designed to run on personal
computers, home servers, or Raspberry Pi devices.

It allows you to **receive, organize, and manage files automatically**,
while keeping full control of your own storage.

## Features

-   Automatic file organization by **year and month**
-   Support for **custom folders**
-   **Duplicate detection** to avoid unnecessary storage usage
-   Centralized storage accessible from **authorized devices**
-   Lightweight and suitable for **Raspberry Pi and low-power systems**
-   Built with **Python**

------------------------------------------------------------------------

# Table of Contents

-   [Requirements](#requirements)
-   [How It Works](#how-it-works)
-   [Installation](#installation)
-   [Running the Service](#running-the-service)
-   [Logs](#logs)
-   [Updating](#updating)
-   [Uninstall](#uninstall)
-   [Getting Started](#getting-started)
-   [Using an External Disk (Linux)](#using-an-external-disk-linux)
-   [License](#license)

------------------------------------------------------------------------

# Requirements

-   Python **3.9+**
-   Git

Supported operating systems:

-   Linux
-   macOS
-   Windows

------------------------------------------------------------------------

# How It Works

The system receives files and automatically stores them in the
configured storage directory.

By default, files are organized using the following structure:

    YEAR/MONTH

Example:

    storage/
     ├── 2026/
     │   ├── 03/
     │   ├── 04/

You can also use **custom folders** to organize files according to your
needs.

Example:

    storage/
     ├── trips/
     │   ├── 2026/
     │   │   ├── 03/
     │   │   ├── 04/

Files remain stored until the user decides to delete or manage them
manually.

------------------------------------------------------------------------

# Installation

## 1. Clone the repository

``` bash
git clone https://github.com/usuario/repositorio.git
cd repositorio
```

## 2. Create a virtual environment

``` bash
python3 -m venv venv
```

Activate it:

Linux / macOS

``` bash
source venv/bin/activate
```

Windows

``` bash
venv\Scripts\activate
```

## 3. Install dependencies

``` bash
pip install -r requirements.txt
```

## 4. Configure environment variables

``` bash
cp .env.example .env
```

Edit the `.env` file:

    STORAGE_DIR=PATH_TO_DIRECTORY
    META_LOG=PATH_TO_DIRECTORY/metadata.jsonl

    DEFAULT_CONTEXT=default
    ALLOW_COMPRESSED_PHOTOS=false
    MAX_BYTES=0

Where `PATH_TO_DIRECTORY` is the **absolute path to the storage
directory**.

------------------------------------------------------------------------

# Running the Project

Start the application with:

``` bash
python app.py
```

------------------------------------------------------------------------

# Running as a System Service (Linux)

Create the file:

    /etc/systemd/system/storage.service

Example configuration:

    [Unit]
    Description=Storage Service
    After=network.target

    [Service]
    User=user
    WorkingDirectory=/path/to/project
    ExecStart=/path/to/project/venv/bin/python app.py
    Restart=always

    [Install]
    WantedBy=multi-user.target

Enable the service:

``` bash
sudo systemctl daemon-reload
sudo systemctl enable storage.service
sudo systemctl start storage.service
```

------------------------------------------------------------------------

# Logs

Check service status:

``` bash
sudo systemctl status storage.service
```

Follow logs in real time:

``` bash
journalctl -u storage.service -f
```

------------------------------------------------------------------------

# Updating

``` bash
git pull
pip install -r requirements.txt
sudo systemctl restart storage.service
```

------------------------------------------------------------------------

# Uninstall

``` bash
sudo systemctl stop storage.service
sudo systemctl disable storage.service
rm -rf repositorio
```

------------------------------------------------------------------------

# Getting Started

## Telegram Integration

Currently, the system uses a **Telegram bot** to interact with the
storage.

### Creating a Telegram Bot

1.  Open Telegram
2.  Search for **@BotFather**
3.  Run:

```{=html}
<!-- -->
```
    /start

4.  Create a new bot:

```{=html}
<!-- -->
```
    /newbot

5.  Follow the instructions

BotFather will provide a **bot token**.

Example:

    123456789:AAExampleBotTokenExample

## Configure the Token

Example using an environment variable:

``` bash
export TELEGRAM_BOT_TOKEN=YOUR_TOKEN_HERE
```

## Available Commands

  Command       Description
  ------------- ---------------------------
  `/start`      Initialize the bot
  `/help`       Show available commands
  `/folder`     Select or create a folder
  `/storage`    Show storage information
  `/list`       List files or folders
  `/search`     Search files
  `/download`   Download file
  `/delete`     Delete file

------------------------------------------------------------------------

# Using an External Disk (Linux)

To locate your disk:

``` bash
lsblk
```

Example device:

    /dev/sdX1

Mount it:

``` bash
sudo mkdir /mnt/storage
sudo mount /dev/sdX1 /mnt/storage
```

## Automatic Mount (fstab)

Get disk UUID:

``` bash
blkid
```

Edit:

    /etc/fstab

Add:

    UUID=XXXXXXXX /mnt/storage ext4 defaults,nofail 0 2

Test:

``` bash
sudo mount -a
```

------------------------------------------------------------------------

# License

See the `LICENSE` file.
