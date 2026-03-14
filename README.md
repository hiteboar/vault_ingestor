# Raspi Vault Storage

# 1. Introduction and Features

This project implements a system for **organized local file storage**,
designed to run on devices such as personal computers, home servers, or
Raspberry Pi.

The system allows you to **centralize the reception and storage of
files**, automatically organizing them into folders structured by **year
and month**, while also allowing the creation of **custom subfolders**
where information can be stored according to the user's needs. Files
remain stored until the user decides to delete or manage them manually.

Additionally, the system includes a **file verification mechanism** that
helps prevent duplicates and reduces unnecessary storage space usage.

The goal of the project is to simplify **file management and access from
different authorized devices**, allowing users to browse, extract, or
download stored information without depending solely on the device where
the physical storage is located.

The project is developed in **Python** and can run on different types of
computers and desktop or server operating systems.

## System Requirements

-   Python **3.9+**
-   Git

Compatible with:

-   Linux
-   macOS
-   Windows

------------------------------------------------------------------------

# 2. System Usage

The system allows receiving and storing files in the configured storage
directory. Once a file is received, the system automatically processes
it and saves it following the defined folder structure.

By default, files are organized by date:

    YEAR/MONTH

Example:

    storage/
     ├── 2026/
     │   ├── 03/
     │   ├── 04/

Additionally, the system allows the use of **custom subfolders** to
organize information according to user needs.

Example:

    storage/
     ├── trips/
     │   ├── 2026/
     │   │   ├── 03/
     │   │   ├── 04/

Files will remain stored in the system until the user decides to delete
them or manage them manually.

# 3. Installation

## 3.1 Clone the repository

``` bash
git clone https://github.com/usuario/repositorio.git
cd repositorio
```

## 3.2 Create a virtual environment

``` bash
python3 -m venv venv
```

Activate:

Linux/macOS

``` bash
source venv/bin/activate
```

Windows

``` bash
venv\Scripts\activate
```

## 3.3 Install dependencies

``` bash
pip install -r requirements.txt
```

## 3.5 Configure environment variables

``` bash
cp .env.example .env
```

Configure the values in the `.env` file:

    STORAGE_DIR=PATH_TO_DIRECTORY
    META_LOG=PATH_TO_DIRECTORY/metadata.jsonl

    DEFAULT_CONTEXT=default
    ALLOW_COMPRESSED_PHOTOS=false
    MAX_BYTES=0

Where `PATH_TO_DIRECTORY` corresponds to the absolute path of the
directory you want to use to store all received files.

## 3.6 Run the project

To run the project, simply execute:

``` bash
python app.py
```

### 3.6.1 Run as an automatic service

Edit the file `/etc/systemd/system/storage.service`

Content:

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

Run the following commands to enable the service:

``` bash
sudo systemctl daemon-reload
sudo systemctl enable storage.service
sudo systemctl start storage.service
```

## 3.9 Logs

``` bash
sudo systemctl status storage.service
journalctl -u storage.service -f
```

## 3.10 Update

``` bash
git pull
pip install -r requirements.txt
sudo systemctl restart storage.service
```

## 3.11 Uninstall

``` bash
sudo systemctl stop storage.service
sudo systemctl disable storage.service
rm -rf repositorio
```

# 4. Getting Started

## 4.1 Telegram Control Configuration

Currently, the system uses a **Telegram bot** to interact with the
storage.

### Create a Telegram Bot

1.  Open Telegram.
2.  Search for **@BotFather**.
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

5.  Follow the instructions and assign a name to the bot.

BotFather will provide an **access token**.

Example:

    123456789:AAExampleBotTokenExample

### Configure the token

Example using an environment variable:

``` bash
export TELEGRAM_BOT_TOKEN=YOUR_TOKEN_HERE
```

### Available Commands (Telegram)

  Command       Description
  ------------- --------------------------------------
  `/start`      Initializes interaction with the bot
  `/help`       Shows the list of available commands
  `/folder`     Selects or creates a subfolder
  `/storage`    Storage information
  `/list`       Lists files or folders
  `/search`     Search files
  `/download`   Download file
  `/delete`     Delete file

# 5 Using an External Disk (Linux)

Use the following commands to find and configure the disk you want to
use.

Run:

``` bash
lsblk
```

to find the name of the external disk. In this example we will use
`/dev/sdX1`. Then create the directory and mount the disk using:

``` bash
sudo mkdir /mnt/storage
sudo mount /dev/sdX1 /mnt/storage
```

## 5.1 Automatic Mount of the External Disk

Run the command `blkid` to obtain the UUID of your external disk.

Edit the file `/etc/fstab`

Add:

    UUID=XXXXXXXX /mnt/storage ext4 defaults,nofail 0 2

Test:

``` bash
sudo mount -a
```

------------------------------------------------------------------------

# 6. License

See the `LICENSE` file.
