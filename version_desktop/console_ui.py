import os
import threading
import time
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

# Ensure core is importable from the subfolder
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

import webview
import uvicorn
import pystray
from PIL import Image, ImageDraw
import requests

try:
    import exifread
except ImportError:
    exifread = None

from api.main import app as fastapi_app
from api.main import auth as fastapi_auth
from app import bootstrap # Import startup logic from app.py

# Basic configuration
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8081"))
API_URL = f"http://{API_HOST}:{API_PORT}"
UI_TITLE = "Vault Ingestor - Management Console & Client"

CLIENT_SETTINGS_FILE = BASE_DIR / "vault_internal" / "client_settings.json"

def load_client_settings():
    """Loads active client connection or defaults to local server."""
    if CLIENT_SETTINGS_FILE.exists():
        try:
            data = json.loads(CLIENT_SETTINGS_FILE.read_text(encoding="utf-8"))
            # Ensure basic fields
            if "url" in data and "token" in data:
                return data
        except:
            pass
    return {
        "url": f"http://127.0.0.1:{API_PORT}",
        "token": "desktop_local_admin_token",
        "is_local": True,
        "role": "admin"
    }

def save_client_settings(settings):
    """Saves client connection credentials to disk."""
    try:
        CLIENT_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        CLIENT_SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[CLIENT_CONFIG_ERROR] Could not save: {e}")

def run_server():
    """Launches the FastAPI server in a separate thread."""
    bootstrap()
    uvicorn.run(fastapi_app, host=API_HOST, port=API_PORT)

class Api:
    """Bridge class between Python and JavaScript."""
    def __init__(self):
        self.upload_state = {
            "active": False,
            "total": 0,
            "current": 0,
            "current_name": "",
            "percent": 0,
            "error": ""
        }

    def get_status(self):
        return {"status": "ok", "message": "Console Bridge Active"}

    def open_folder(self, path):
        """Opens a folder in Windows explorer."""
        if os.name == "nt":
            os.startfile(path)
        return True

    def get_client_connection(self):
        """Retrieves the active client configuration."""
        return load_client_settings()

    def disconnect_vault(self):
        """Resets the client connection to the default local server."""
        settings = {
            "url": f"http://127.0.0.1:{API_PORT}",
            "token": "desktop_local_admin_token",
            "is_local": True,
            "role": "admin"
        }
        save_client_settings(settings)
        return settings

    def link_remote_vault(self, url, pin):
        """Connects and pairs with a remote Vault server using a PIN."""
        url = url.strip().rstrip('/')
        if not url:
            return {"success": False, "message": "Invalid Server URL"}
        
        try:
            verify_url = f"{url}/api/auth/verify"
            print(f"[CLIENT] Linking to {verify_url}...")
            res = requests.post(verify_url, json={"pin": pin}, timeout=10)
            if res.status_code != 200:
                detail = res.json().get("detail", "Failed to link PIN")
                return {"success": False, "message": f"Server returned error: {detail}"}
                
            data = res.json()
            token = data.get("token")
            if not token:
                return {"success": False, "message": "Failed to retrieve connection token."}
                
            # Verify token and fetch metadata role
            me_res = requests.get(f"{url}/api/auth/me", headers={"x-device-token": token}, timeout=10)
            if me_res.status_code != 200:
                return {"success": False, "message": "Verify failed. Token could not be authenticated."}
                
            me_data = me_res.json()
            settings = {
                "url": url,
                "token": token,
                "is_local": False,
                "role": me_data.get("role", "standard")
            }
            save_client_settings(settings)
            return {"success": True, "settings": settings}
        except Exception as e:
            return {"success": False, "message": f"Connection error: {str(e)}"}

    def get_upload_status(self):
        """Returns the active file uploading progress."""
        return self.upload_state

    def open_file_locally(self, item_id):
        """Opens a vault file locally on the PC using the OS default application."""
        from api.main import metadata_cache
        item_meta = metadata_cache.get_item(item_id)
        if item_meta:
            saved_path = item_meta.get("saved_path")
            if saved_path and os.path.exists(saved_path):
                if os.name == "nt":
                    os.startfile(saved_path)
                    return True
        return False

    def select_and_upload_files(self, folder):
        """Launches the OS native file chooser and uploads in background."""
        if not webview.windows:
            return {"success": False, "message": "No active window"}
            
        window = webview.windows[0]
        # Open native OS multi-file dialog
        file_paths = window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=True)
        
        if not file_paths:
            return {"success": False, "message": "No files selected"}
            
        # Start background uploading thread
        threading.Thread(
            target=self._select_and_upload_worker,
            args=(file_paths, folder),
            daemon=True
        ).start()
        
        return {"success": True, "count": len(file_paths)}

    def _extract_creation_date(self, path_str):
        # Try to get EXIF
        try:
            if exifread:
                with open(path_str, 'rb') as f:
                    tags = exifread.process_file(f, stop_at_track_only=True)
                    if 'Image DateTimeOriginal' in tags:
                        dt_str = str(tags['Image DateTimeOriginal'])
                        parts = dt_str.split(' ')
                        if len(parts) == 2:
                            return f"{parts[0].replace(':', '-')}T{parts[1]}Z"
        except Exception:
            pass
        # Fallback: file creation or modification date
        try:
            mtime = os.path.getmtime(path_str)
            return datetime.fromtimestamp(mtime, timezone.utc).isoformat().replace('+00:00', 'Z')
        except:
            pass
        return None

    def _select_and_upload_worker(self, file_paths, folder):
        self.upload_state.update({
            "active": True,
            "total": len(file_paths),
            "current": 0,
            "current_name": "",
            "percent": 0,
            "error": ""
        })
        
        settings = load_client_settings()
        upload_url = f"{settings['url']}/api/upload"
        headers = {"x-device-token": settings["token"]}
        
        success_count = 0
        for idx, path in enumerate(file_paths):
            if not os.path.exists(path):
                continue
                
            filename = os.path.basename(path)
            self.upload_state.update({
                "current": idx + 1,
                "current_name": filename,
                "percent": 0
            })
            
            # Map MIME type
            ext = os.path.splitext(filename)[1].lower()
            mime_types = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.webp': 'image/webp',
                '.heic': 'image/heic',
                '.heif': 'image/heif',
                '.gif': 'image/gif',
                '.mp4': 'video/mp4',
                '.mov': 'video/quicktime',
                '.mkv': 'video/x-matroska',
                '.pdf': 'application/pdf'
            }
            content_type = mime_types.get(ext, 'application/octet-stream')
            
            original_date = self._extract_creation_date(path)
            
            try:
                total_size = os.path.getsize(path)
                with open(path, 'rb') as f:
                    class ProgressFileWrapper:
                        def __init__(self, file_obj, progress_callback):
                            self.file_obj = file_obj
                            self.progress_callback = progress_callback
                            self.bytes_read = 0
                        
                        def read(self, size=-1):
                            chunk = self.file_obj.read(size)
                            if chunk:
                                self.bytes_read += len(chunk)
                                pct = int((self.bytes_read / total_size) * 100)
                                self.progress_callback(pct)
                            return chunk
                            
                        def seek(self, offset, whence=0):
                            return self.file_obj.seek(offset, whence)
                            
                        def tell(self):
                            return self.file_obj.tell()

                    def progress_cb(pct):
                        self.upload_state["percent"] = pct
                        # Send live JS call
                        try:
                            if webview.windows:
                                win = webview.windows[0]
                                escaped_name = filename.replace("'", "\\'")
                                win.evaluate_js(f"if(typeof updateUploadProgress === 'function') updateUploadProgress({idx + 1}, {len(file_paths)}, '{escaped_name}', {pct});")
                        except Exception:
                            pass

                    wrapped_file = ProgressFileWrapper(f, progress_cb)
                    files = {'file': (filename, wrapped_file, content_type)}
                    data = {'context': folder}
                    if original_date:
                        data['original_date'] = original_date
                        
                    response = requests.post(upload_url, headers=headers, files=files, data=data, timeout=300)
                    if response.status_code == 200:
                        success_count += 1
                    else:
                        print(f"[CLIENT_UPLOAD_ERROR] {filename}: {response.text}")
            except Exception as e:
                print(f"[CLIENT_UPLOAD_EXCEPTION] {filename}: {e}")
                
        self.upload_state.update({
            "active": False,
            "current": 0,
            "percent": 0
        })
        
        # Trigger reload in JS
        try:
            if webview.windows:
                webview.windows[0].evaluate_js("if(typeof onNativeUploadFinished === 'function') onNativeUploadFinished();")
        except:
            pass

def run_tray(window):
    """Runs the icon in the system tray in the background."""
    def create_image():
        image = Image.new('RGBA', (64, 64), color=(0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((4, 4, 60, 60), radius=16, fill=(15, 23, 42))
        draw.ellipse((20, 20, 44, 44), fill=(59, 130, 246))
        return image

    def on_open(icon, item):
        window.show()

    def on_exit(icon, item):
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem('Open Dashboard', on_open, default=True),
        pystray.MenuItem('Stop and Exit', on_exit)
    )
    
    icon = pystray.Icon("Vault Ingestor", create_image(), "Vault Ingestor", menu)
    icon.run()

# HTML with elegant responsive gallery, drag & drop, lightbox and statistics
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vault Ingestor - Desktop UI</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Outfit', sans-serif; background: #0b0f19; color: #f8fafc; overflow: hidden; }
        .glass { background: rgba(17, 24, 39, 0.7); backdrop-filter: blur(16px); border: 1px solid rgba(255,255,255,0.06); }
        .sidebar { width: 280px; height: 100vh; border-right: 1px solid rgba(255,255,255,0.05); }
        .main-content { height: 100vh; overflow-y: auto; }
        .radial-bg { background: radial-gradient(circle at 50% 50%, #111827 0%, #070a13 100%); }
        .nav-btn { cursor: pointer; transition: all 0.2s ease-in-out; }
        .nav-active { background: rgba(59, 130, 246, 0.12); color: #60a5fa; font-weight: 600; border-left: 3px solid #3b82f6; }
        .card-hover:hover { transform: translateY(-2px); border-color: rgba(59, 130, 246, 0.3); }
        .custom-scrollbar::-webkit-scrollbar { width: 6px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 9px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.25); }
    </style>
</head>
<body class="radial-bg flex select-none">

    <!-- Sidebar -->
    <div class="sidebar glass p-6 flex flex-col justify-between flex-shrink-0">
        <div>
            <div class="flex items-center gap-3 mb-8">
                <div class="w-10 h-10 bg-gradient-to-tr from-blue-600 to-cyan-500 rounded-xl flex items-center justify-center shadow-lg shadow-blue-500/30">
                    <svg class="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                    </svg>
                </div>
                <div>
                    <span class="text-lg font-bold tracking-tight block">Vault Ingestor</span>
                    <span class="text-[10px] text-slate-400 font-medium tracking-wide uppercase">Desktop Hub</span>
                </div>
            </div>
            
            <div class="mb-4">
                <span class="text-[10px] text-slate-500 font-bold uppercase tracking-wider block mb-2 px-3">Local Engine (Server)</span>
                <nav class="space-y-1">
                    <a id="btn-nav-dashboard" onclick="switchView('view-dashboard')" class="nav-btn flex items-center gap-3 text-slate-400 hover:text-white px-4 py-2.5 rounded-xl text-sm nav-active">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 002 2h2a2 2 0 002-2"/></svg>
                        Dashboard
                    </a>
                    
                    <a id="btn-nav-config" onclick="switchView('view-config')" class="nav-btn flex items-center gap-3 text-slate-400 hover:text-white px-4 py-2.5 rounded-xl text-sm">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37a1.724 1.724 0 002.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
                        Configuration
                    </a>

                    <a id="btn-nav-mobile" onclick="switchView('view-mobile')" class="nav-btn flex items-center gap-3 text-slate-400 hover:text-white px-4 py-2.5 rounded-xl text-sm">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>
                        Link Mobile
                    </a>
                </nav>
            </div>

            <div>
                <span class="text-[10px] text-slate-500 font-bold uppercase tracking-wider block mb-2 px-3">Vault Client</span>
                <nav class="space-y-1">
                    <a id="btn-nav-gallery" onclick="switchView('view-gallery')" class="nav-btn flex items-center gap-3 text-slate-400 hover:text-white px-4 py-2.5 rounded-xl text-sm">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
                        Gallery Explorer
                    </a>
                    
                    <a id="btn-nav-uploader" onclick="switchView('view-uploader')" class="nav-btn flex items-center gap-3 text-slate-400 hover:text-white px-4 py-2.5 rounded-xl text-sm">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/></svg>
                        Native Uploader
                    </a>

                    <a id="btn-nav-remote" onclick="switchView('view-remote')" class="nav-btn flex items-center gap-3 text-slate-400 hover:text-white px-4 py-2.5 rounded-xl text-sm">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"/></svg>
                        Connect Remote
                    </a>
                </nav>
            </div>
        </div>

        <div class="space-y-4">
            <div class="p-4 bg-slate-900/50 rounded-2xl border border-white/5">
                <div class="text-[10px] text-slate-500 uppercase font-bold tracking-wide mb-1">Target Vault</div>
                <div class="flex items-center gap-2 mb-1.5 overflow-hidden">
                    <span id="indicator-client-url" class="text-xs text-blue-400 font-medium truncate block">Checking...</span>
                </div>
                <div class="flex items-center gap-1.5">
                    <div id="indicator-client-status" class="w-2 h-2 bg-yellow-500 rounded-full animate-pulse"></div>
                    <span id="indicator-client-status-txt" class="text-[11px] text-slate-400">Loading...</span>
                </div>
            </div>
        </div>
    </div>

    <!-- Main Content Panel -->
    <div class="main-content flex-1 flex flex-col h-screen custom-scrollbar relative">
        
        <!-- ====== VIEW: DASHBOARD ====== -->
        <div id="view-dashboard" class="p-10 flex flex-col h-full space-y-6">
            <header class="flex justify-between items-center">
                <div>
                    <h1 class="text-3xl font-bold tracking-tight">System Monitor</h1>
                    <p class="text-sm text-slate-400 mt-1">Real-time status of your Vault central engine.</p>
                </div>
                <button onclick="updateStats()" class="p-2.5 glass rounded-xl hover:bg-white/10 transition-all text-blue-400 shadow-md">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
                </button>
            </header>

            <div class="grid grid-cols-3 gap-6">
                <div class="glass p-6 rounded-3xl card-hover border border-white/5 transition-all">
                    <div class="text-slate-400 text-xs uppercase font-bold tracking-wider mb-1">Disk Storage</div>
                    <div id="disk-text" class="text-4xl font-extrabold tracking-tight">-- %</div>
                    <div class="w-full bg-white/5 h-2 rounded-full mt-4 overflow-hidden">
                        <div id="disk-bar" class="bg-blue-500 h-full transition-all duration-1000" style="width: 0%"></div>
                    </div>
                </div>

                <div class="glass p-6 rounded-3xl card-hover border border-white/5 transition-all">
                    <div class="text-slate-400 text-xs uppercase font-bold tracking-wider mb-1">CPU Load</div>
                    <div id="cpu-text" class="text-4xl font-extrabold tracking-tight">-- %</div>
                    <div class="w-full bg-white/5 h-2 rounded-full mt-4 overflow-hidden">
                        <div id="cpu-bar" class="bg-indigo-500 h-full transition-all duration-1000" style="width: 0%"></div>
                    </div>
                </div>

                <div class="glass p-6 rounded-3xl card-hover border border-white/5 transition-all">
                    <div class="text-slate-400 text-xs uppercase font-bold tracking-wider mb-1">RAM Usage</div>
                    <div id="ram-text" class="text-4xl font-extrabold tracking-tight">-- %</div>
                    <div class="w-full bg-white/5 h-2 rounded-full mt-4 overflow-hidden">
                        <div id="ram-bar" class="bg-cyan-500 h-full transition-all duration-1000" style="width: 0%"></div>
                    </div>
                </div>
            </div>

            <div class="glass rounded-3xl p-6 flex-1 flex flex-col overflow-hidden min-h-[300px] border border-white/5">
                <div class="flex justify-between items-center mb-4">
                    <h2 class="text-lg font-bold">Activity Logs</h2>
                    <span class="text-[10px] text-slate-500 uppercase tracking-widest font-bold">Live Stream</span>
                </div>
                <div id="log-container" class="flex-1 overflow-y-auto font-mono text-xs text-slate-400 space-y-1.5 pr-2 custom-scrollbar">
                    <div class="text-slate-600">[System] Shell interface loaded successfully.</div>
                </div>
            </div>
        </div>

        <!-- ====== VIEW: CONFIGURATION ====== -->
        <div id="view-config" class="p-10 space-y-6 hidden">
            <header>
                <h1 class="text-3xl font-bold tracking-tight">Local Server Configuration</h1>
                <p class="text-sm text-slate-400 mt-1">Configure your Central Ingestor Engine preferences.</p>
            </header>

            <div class="glass rounded-3xl p-8 max-w-3xl border border-white/5 space-y-6">
                <form id="config-form" class="space-y-6" onsubmit="event.preventDefault(); saveConfig();">
                    <div class="space-y-2">
                        <label class="block text-sm font-semibold text-blue-300">Central Storage Directory</label>
                        <p class="text-xs text-slate-500">Absolute path where the processed database files and physical assets are physically saved.</p>
                        <input type="text" id="input-STORAGE_DIR" placeholder="e.g.: vault_storage" class="w-full bg-slate-900/50 border border-white/10 rounded-xl px-4 py-3 text-white text-sm focus:outline-none focus:border-blue-500 transition-colors">
                    </div>

                    <div class="p-5 bg-white/5 rounded-2xl border border-white/5 flex items-center justify-between">
                        <div>
                            <span class="text-sm font-semibold text-blue-300 block">Enable Remote WAN Tunnel Access</span>
                            <span class="text-xs text-slate-500 mt-0.5 block">Expose central services securely over internet (temp Cloudflare address) without local WiFi coupling.</span>
                        </div>
                        <label class="relative inline-flex items-center cursor-pointer">
                            <input type="checkbox" id="input-ENABLE_REMOTE_ACCESS" class="sr-only peer">
                            <div class="w-11 h-6 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
                        </label>
                    </div>
                    
                    <div class="pt-4 flex items-center justify-between">
                        <div id="save-message" class="text-sm text-emerald-400 font-medium hidden">Configuration updated successfully.</div>
                        <button type="submit" id="save-btn" class="bg-blue-600 hover:bg-blue-500 text-white text-sm px-8 py-3 rounded-xl font-semibold transition-colors shadow-lg shadow-blue-500/20 ml-auto">Save Changes</button>
                    </div>
                </form>
            </div>
        </div>

        <!-- ====== VIEW: MOBILE LINKING ====== -->
        <div id="view-mobile" class="p-10 space-y-6 hidden">
            <header>
                <h1 class="text-3xl font-bold tracking-tight">Link Android Device</h1>
                <p class="text-sm text-slate-400 mt-1">Connect your smartphone to upload and navigate files easily.</p>
            </header>

            <div class="grid grid-cols-2 gap-10 max-w-5xl">
                <div class="glass rounded-3xl p-8 flex flex-col items-center border border-white/5">
                    <h2 class="text-base font-bold text-center mb-1">Scan the QR code</h2>
                    <p class="text-xs text-slate-500 text-center mb-6">Open the Vault Mobile App and point the scanner here.</p>
                    
                    <div class="bg-white p-4 rounded-3xl shadow-xl shadow-blue-500/5 mb-6">
                        <img id="pairing-qr" src="" alt="Pairing QR" class="w-60 h-60">
                    </div>
                    
                    <button onclick="generatePairing()" class="text-xs text-blue-400 hover:text-blue-300 font-semibold flex items-center gap-1.5">
                         <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
                         Renew pin & token
                    </button>
                </div>

                <div class="space-y-6">
                    <div class="glass rounded-3xl p-8 border border-white/5">
                        <h2 class="text-base font-bold mb-1">Manually enter the PIN</h2>
                        <p class="text-xs text-slate-500 mb-6">If scanner fails, manually link by typing the PIN below.</p>
                        
                        <div id="pairing-pin" class="text-5xl font-black tracking-widest text-center py-6 bg-slate-950/40 rounded-2xl text-blue-400 border border-blue-500/10 font-mono shadow-inner">
                            ------
                        </div>
                        
                        <div class="mt-4 text-center">
                            <span class="text-[10px] text-slate-600 font-bold uppercase tracking-wider">PIN session valid for 5 minutes</span>
                        </div>
                    </div>

                    <div class="bg-blue-600/5 border border-blue-500/10 rounded-3xl p-6">
                        <h3 class="font-bold text-sm text-blue-400 mb-2 flex items-center gap-2">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                            Linked Capabilities
                        </h3>
                        <ul class="text-xs text-slate-400 space-y-2 list-disc list-inside">
                            <li>Fast client synchronization over Local WiFi or Cloud tunnel.</li>
                            <li>Real-time image previewing and video streaming.</li>
                            <li>Preserves original metadata (EXIF/GPS) during picking.</li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>

        <!-- ====== VIEW: VAULT GALLERY ====== -->
        <div id="view-gallery" class="p-10 flex flex-col h-full space-y-6 hidden">
            <header class="flex justify-between items-end flex-wrap gap-4">
                <div>
                    <h1 class="text-3xl font-bold tracking-tight">Vault Explorer</h1>
                    <p class="text-sm text-slate-400 mt-1">Navigate processed resources from your active Vault server.</p>
                </div>
                
                <div class="flex items-center gap-3">
                    <select id="select-folder" onchange="loadGalleryData()" class="bg-slate-900 border border-white/10 rounded-xl px-3 py-2 text-xs text-slate-300 focus:outline-none focus:border-blue-500">
                        <option value="root">Timeline (All folders)</option>
                    </select>

                    <select id="select-sort" onchange="loadGalleryData()" class="bg-slate-900 border border-white/10 rounded-xl px-3 py-2 text-xs text-slate-300 focus:outline-none focus:border-blue-500">
                        <option value="time-desc">Newest First</option>
                        <option value="time-asc">Oldest First</option>
                        <option value="name-asc">Name (A-Z)</option>
                        <option value="size-desc">Largest First</option>
                    </select>

                    <button onclick="loadGalleryData()" class="p-2 bg-slate-900 border border-white/10 rounded-xl text-slate-400 hover:text-white transition-colors">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
                    </button>
                </div>
            </header>

            <!-- Timeline Filter Bar -->
            <div class="flex items-center gap-3 py-2 border-y border-white/5 overflow-x-auto custom-scrollbar">
                <span class="text-xs text-slate-500 font-bold uppercase tracking-wider mr-2">Timeline:</span>
                <div id="timeline-filters-container" class="flex items-center gap-2">
                    <button class="px-3 py-1.5 rounded-lg text-xs bg-blue-600 text-white font-medium">All</button>
                </div>
            </div>

            <!-- Grid Gallery -->
            <div class="flex-1 overflow-y-auto pr-2 custom-scrollbar min-h-[300px]">
                <div id="gallery-grid" class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                    <!-- Dynamic Items -->
                </div>
                <div id="gallery-empty" class="hidden flex-col items-center justify-center py-20 text-slate-500">
                    <svg class="w-12 h-12 text-slate-600 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4"/></svg>
                    <span>No matching vault items found</span>
                </div>
            </div>
        </div>

        <!-- ====== VIEW: NATIVE UPLOADER ====== -->
        <div id="view-uploader" class="p-10 flex flex-col h-full space-y-6 hidden">
            <header>
                <h1 class="text-3xl font-bold tracking-tight">Native Multi-file Uploader</h1>
                <p class="text-sm text-slate-400 mt-1">Upload high-res files directly with background performance and date preservation.</p>
            </header>

            <div class="grid grid-cols-3 gap-8 flex-1 overflow-hidden min-h-[300px]">
                <!-- Upload Drop Zone -->
                <div class="col-span-2 glass rounded-3xl border-2 border-dashed border-white/10 hover:border-blue-500/40 transition-all p-8 flex flex-col items-center justify-center text-center group cursor-pointer" onclick="triggerNativeUpload()">
                    <div class="w-16 h-16 bg-blue-600/10 border border-blue-500/20 group-hover:border-blue-500/40 rounded-2xl flex items-center justify-center text-blue-400 mb-4 transition-colors">
                        <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
                    </div>
                    <h2 class="text-lg font-bold mb-1">Click to select files</h2>
                    <p class="text-xs text-slate-500 max-w-sm mb-4">Opens the native OS file picker. EXIF creation dates will be fully preserved in the backend.</p>
                    
                    <div class="flex items-center gap-3">
                        <span class="text-xs text-slate-400">Destination Context:</span>
                        <select id="uploader-context" onclick="event.stopPropagation()" class="bg-slate-900 border border-white/10 rounded-xl px-3 py-1.5 text-xs text-slate-300 focus:outline-none">
                            <option value="root">root (Timeline)</option>
                        </select>
                    </div>
                </div>

                <!-- Progress Monitor -->
                <div class="glass rounded-3xl p-6 border border-white/5 flex flex-col h-full overflow-hidden">
                    <h3 class="font-bold text-sm mb-4 text-slate-300 border-b border-white/5 pb-3">Background Status</h3>
                    
                    <div id="uploader-idle-state" class="flex-1 flex flex-col items-center justify-center text-center text-slate-500">
                        <svg class="w-10 h-10 text-slate-600 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z"/></svg>
                        <span class="text-xs">No active uploads</span>
                    </div>

                    <div id="uploader-active-state" class="hidden flex-1 flex flex-col justify-between py-4">
                        <div class="space-y-4">
                            <div>
                                <span class="text-[10px] text-slate-500 uppercase font-bold tracking-wider block mb-1">Current File</span>
                                <span id="txt-upload-filename" class="text-xs font-semibold truncate block">file_name.jpg</span>
                            </div>

                            <div>
                                <span class="text-[10px] text-slate-500 uppercase font-bold tracking-wider block mb-1">Queue Progress</span>
                                <span id="txt-upload-queue" class="text-xs font-bold text-blue-400">1 of 10 completed</span>
                            </div>

                            <div class="space-y-1">
                                <div class="flex justify-between items-center text-[10px] text-slate-400">
                                    <span>Progress</span>
                                    <span id="txt-upload-percent">0%</span>
                                </div>
                                <div class="w-full bg-white/5 h-2 rounded-full overflow-hidden">
                                    <div id="bar-upload-percent" class="bg-blue-500 h-full transition-all duration-300" style="width: 0%"></div>
                                </div>
                            </div>
                        </div>

                        <div class="p-4 bg-blue-500/5 border border-blue-500/10 rounded-2xl flex items-center gap-3">
                            <div class="w-2 h-2 bg-blue-500 rounded-full animate-ping"></div>
                            <span class="text-xs text-slate-400">Streaming background upload...</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- ====== VIEW: CONNECT REMOTE ====== -->
        <div id="view-remote" class="p-10 space-y-6 hidden">
            <header>
                <h1 class="text-3xl font-bold tracking-tight">Connect to Remote Vault</h1>
                <p class="text-sm text-slate-400 mt-1">Link your desktop application client to a remote central storage (like a Raspberry Pi).</p>
            </header>

            <div class="glass rounded-3xl p-8 max-w-2xl border border-white/5 space-y-6">
                <form id="remote-form" class="space-y-5" onsubmit="event.preventDefault(); linkRemoteVault();">
                    <div class="space-y-2">
                        <label class="block text-sm font-semibold text-blue-300">Server API URL</label>
                        <p class="text-xs text-slate-500">Address of your remote Vault Ingestor server.</p>
                        <input type="text" id="input-remote-url" placeholder="e.g.: http://192.168.1.148:8001" class="w-full bg-slate-900/50 border border-white/10 rounded-xl px-4 py-3 text-white text-sm focus:outline-none focus:border-blue-500 transition-colors">
                    </div>

                    <div class="space-y-2">
                        <label class="block text-sm font-semibold text-blue-300">Linking PIN (6 digits)</label>
                        <p class="text-xs text-slate-500">The temporary PIN generated on your server's local console screen.</p>
                        <input type="text" id="input-remote-pin" placeholder="e.g.: 123456" class="w-full bg-slate-900/50 border border-white/10 rounded-xl px-4 py-3 text-white text-sm tracking-widest font-mono text-center focus:outline-none focus:border-blue-500 transition-colors">
                    </div>

                    <div id="remote-error-msg" class="text-sm text-rose-400 font-medium hidden"></div>

                    <div class="pt-4 flex items-center justify-between border-t border-white/5">
                        <button type="button" onclick="disconnectRemoteVault()" class="text-xs text-slate-400 hover:text-white font-medium">Reset connection to Local Host</button>
                        <button type="submit" id="remote-btn" class="bg-blue-600 hover:bg-blue-500 text-white text-sm px-8 py-3 rounded-xl font-semibold transition-colors shadow-lg shadow-blue-500/20">Link Server</button>
                    </div>
                </form>
            </div>
        </div>

    </div>

    <!-- ====== MEDIA PREVIEWER LIGHTBOX MODAL ====== -->
    <div id="lightbox-modal" class="fixed inset-0 bg-slate-950/90 z-50 flex items-center justify-center p-6 hidden">
        <div class="glass w-full max-w-5xl h-[85vh] rounded-3xl overflow-hidden border border-white/10 flex shadow-2xl relative">
            
            <!-- Close Button -->
            <button onclick="closeLightbox()" class="absolute top-4 right-4 z-20 p-2.5 bg-black/60 hover:bg-black/90 rounded-full text-slate-300 hover:text-white transition-all">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"/></svg>
            </button>

            <!-- Left Container: Asset Display -->
            <div class="flex-1 bg-black/40 flex items-center justify-center p-4 relative overflow-hidden">
                <div id="lightbox-loading" class="absolute flex flex-col items-center justify-center text-slate-500">
                    <div class="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mb-2"></div>
                    <span class="text-xs">Loading media...</span>
                </div>
                
                <img id="lightbox-img" src="" alt="Lightbox asset" class="max-h-full max-w-full object-contain select-none shadow-2xl hidden">
                <video id="lightbox-video" controls class="max-h-full max-w-full hidden"></video>
                
                <!-- Document Placeholder -->
                <div id="lightbox-doc-placeholder" class="hidden flex-col items-center justify-center text-slate-500">
                    <svg class="w-20 h-20 text-slate-700 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                    <span id="lightbox-doc-name" class="text-sm font-semibold mb-2">document_file.pdf</span>
                    <span class="text-xs text-slate-600">Preview not supported inside layout</span>
                </div>
            </div>

            <!-- Right Container: Metadata & Control Pane -->
            <div class="w-[320px] border-l border-white/5 p-6 flex flex-col justify-between flex-shrink-0 h-full">
                <div class="space-y-6 overflow-y-auto pr-1 custom-scrollbar">
                    <div>
                        <span id="lbl-lightbox-context" class="inline-block text-[9px] bg-blue-500/10 text-blue-400 font-bold px-2 py-0.5 rounded-full uppercase tracking-wider mb-2">Folder: root</span>
                        <h2 id="lbl-lightbox-filename" class="text-base font-bold break-all leading-snug">asset_name_placeholder.jpg</h2>
                    </div>

                    <div class="space-y-4 border-t border-white/5 pt-4">
                        <div>
                            <span class="text-[10px] text-slate-500 uppercase font-bold tracking-wider block mb-1">Creation Date</span>
                            <span id="lbl-lightbox-date" class="text-xs text-slate-300 font-medium">YYYY-MM-DD HH:MM:SS</span>
                        </div>

                        <div>
                            <span class="text-[10px] text-slate-500 uppercase font-bold tracking-wider block mb-1">File Size</span>
                            <span id="lbl-lightbox-size" class="text-xs text-slate-300 font-medium">0.00 MB</span>
                        </div>

                        <div id="row-lightbox-gps" class="hidden">
                            <span class="text-[10px] text-slate-500 uppercase font-bold tracking-wider block mb-1">GPS Coordinates</span>
                            <span id="lbl-lightbox-gps" class="text-xs text-blue-400 font-medium">--,--</span>
                        </div>
                    </div>
                </div>

                <div class="space-y-3 pt-6 border-t border-white/5">
                    <button onclick="triggerLocalOpen()" class="w-full bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs py-2.5 rounded-xl transition-colors flex items-center justify-center gap-1.5 shadow-lg shadow-blue-500/10">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
                        Open Locally on PC
                    </button>
                    
                    <a id="btn-lightbox-download" href="" download class="w-full bg-slate-900 border border-white/10 hover:border-white/20 text-slate-300 hover:text-white font-semibold text-xs py-2.5 rounded-xl transition-all flex items-center justify-center gap-1.5">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
                        Download File
                    </a>

                    <button id="btn-lightbox-delete" onclick="triggerDeleteAsset()" class="w-full bg-rose-600/10 hover:bg-rose-600 text-rose-500 hover:text-white font-semibold text-xs py-2.5 rounded-xl transition-all flex items-center justify-center gap-1.5">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                        Delete Permanently
                    </button>
                </div>
            </div>
        </div>
    </div>

    <!-- Script Block -->
    <script>
        let activeConnection = null;
        let activeGalleryItems = [];
        let activePreviewItem = null;
        let activeTimelineFilter = 'All';

        function formatBytes(bytes, decimals = 2) {
            if (!bytes || bytes === 0) return '0 Bytes';
            const k = 1024;
            const dm = decimals < 0 ? 0 : decimals;
            const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
        }

        function switchView(viewId) {
            document.getElementById('view-dashboard').style.display = 'none';
            document.getElementById('view-config').style.display = 'none';
            document.getElementById('view-mobile').style.display = 'none';
            document.getElementById('view-gallery').style.display = 'none';
            document.getElementById('view-uploader').style.display = 'none';
            document.getElementById('view-remote').style.display = 'none';
            
            document.getElementById('btn-nav-dashboard').classList.remove('nav-active');
            document.getElementById('btn-nav-config').classList.remove('nav-active');
            document.getElementById('btn-nav-mobile').classList.remove('nav-active');
            document.getElementById('btn-nav-gallery').classList.remove('nav-active');
            document.getElementById('btn-nav-uploader').classList.remove('nav-active');
            document.getElementById('btn-nav-remote').classList.remove('nav-active');
            
            document.getElementById(viewId).style.display = 'flex';
            document.getElementById('btn-nav-' + viewId.replace('view-', '')).classList.add('nav-active');
            
            if(viewId === 'view-config') loadConfig();
            if(viewId === 'view-mobile') generatePairing();
            if(viewId === 'view-gallery') loadGalleryData();
            if(viewId === 'view-uploader') populateContextDropdowns();
        }

        async function verifyConnection() {
            try {
                const conn = await window.pywebview.api.get_client_connection();
                activeConnection = conn;
                
                document.getElementById('indicator-client-url').innerText = conn.url;
                
                // Fetch stats as ping
                const response = await fetch(`${conn.url}/api/auth/me`, {
                    headers: { 'x-device-token': conn.token }
                });
                
                if (response.ok) {
                    const data = await response.json();
                    document.getElementById('indicator-client-status').className = "w-2 h-2 bg-emerald-500 rounded-full animate-pulse";
                    document.getElementById('indicator-client-status-txt').innerText = `Connected (${data.role})`;
                    return true;
                } else {
                    throw new Error("Auth failed");
                }
            } catch (e) {
                document.getElementById('indicator-client-status').className = "w-2 h-2 bg-rose-500 rounded-full";
                document.getElementById('indicator-client-status-txt').innerText = "Offline / Connection lost";
                return false;
            }
        }

        async function generatePairing() {
            try {
                const response = await fetch('/api/auth/request');
                const data = await response.json();
                document.getElementById('pairing-pin').innerText = data.pin;
                document.getElementById('pairing-qr').src = '/api/auth/qr?t=' + Date.now();
            } catch (e) {
                console.error(e);
            }
        }

        async function loadConfig() {
            try {
                const response = await fetch('/api/config');
                const data = await response.json();
                document.getElementById('input-STORAGE_DIR').value = data.STORAGE_DIR || '';
                document.getElementById('input-ENABLE_REMOTE_ACCESS').checked = String(data.ENABLE_REMOTE_ACCESS).toLowerCase() === 'true';
            } catch (e) {
                console.error(e);
            }
        }

        async function saveConfig() {
            const btn = document.getElementById('save-btn');
            const msg = document.getElementById('save-message');
            btn.innerText = "Saving...";
            btn.disabled = true;
            
            try {
                const storageDir = document.getElementById('input-STORAGE_DIR').value.trim();
                const enableRemote = document.getElementById('input-ENABLE_REMOTE_ACCESS').checked ? 'true' : 'false';
                
                await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ key: 'STORAGE_DIR', value: storageDir })
                });
                await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ key: 'ENABLE_REMOTE_ACCESS', value: enableRemote })
                });
                
                addLog("[Config] Server config updated. Restart local server to apply some parameters.");
                msg.style.display = 'block';
                setTimeout(() => { msg.style.display = 'none'; }, 3000);
            } catch(e) {
                console.error(e);
            } finally {
                btn.innerText = "Save Changes";
                btn.disabled = false;
            }
        }

        async function updateStats() {
            try {
                const response = await fetch('/api/system/status');
                const data = await response.json();
                
                document.getElementById('disk-text').innerText = Math.round(data.disk.percent) + '%';
                document.getElementById('disk-bar').style.width = data.disk.percent + '%';
                
                document.getElementById('cpu-text').innerText = Math.round(data.cpu.percent) + '%';
                document.getElementById('cpu-bar').style.width = data.cpu.percent + '%';
                
                document.getElementById('ram-text').innerText = Math.round(data.ram.percent) + '%';
                document.getElementById('ram-bar').style.width = data.ram.percent + '%';
            } catch (e) {}
        }

        async function fetchLogs() {
            try {
                const response = await fetch('/api/system/logs');
                if (response.ok) {
                    const data = await response.json();
                    const container = document.getElementById('log-container');
                    container.innerHTML = "";
                    data.logs.forEach(line => {
                        const div = document.createElement('div');
                        div.innerText = line;
                        container.appendChild(div);
                    });
                    container.scrollTop = container.scrollHeight;
                }
            } catch (e) {}
        }

        // Vault Client Gallery explorer functions
        async function loadGalleryData() {
            if (!activeConnection) return;
            const grid = document.getElementById('gallery-grid');
            const empty = document.getElementById('gallery-empty');
            grid.innerHTML = "";
            empty.style.display = "none";

            try {
                // Fetch items list
                const resItems = await fetch(`${activeConnection.url}/api/items`, {
                    headers: { 'x-device-token': activeConnection.token }
                });
                if (!resItems.ok) throw new Error("Could not load gallery");
                const list = await resItems.json();
                activeGalleryItems = list;
                
                // Fetch folders list
                const resFolders = await fetch(`${activeConnection.url}/api/folders`, {
                    headers: { 'x-device-token': activeConnection.token }
                });
                if (resFolders.ok) {
                    const fList = await resFolders.json();
                    const selector = document.getElementById('select-folder');
                    const uploaderSelector = document.getElementById('uploader-context');
                    
                    const savedFVal = selector.value;
                    const savedUVal = uploaderSelector.value;
                    
                    selector.innerHTML = '<option value="root">Timeline (All folders)</option>';
                    uploaderSelector.innerHTML = '<option value="root">root (Timeline)</option>';
                    
                    fList.forEach(folder => {
                        if (folder !== 'root') {
                            selector.innerHTML += `<option value="${folder}">${folder}</option>`;
                            uploaderSelector.innerHTML += `<option value="${folder}">${folder}</option>`;
                        }
                    });
                    selector.value = savedFVal;
                    uploaderSelector.value = savedUVal;
                }

                renderFilteredGallery();
            } catch (e) {
                console.error(e);
            }
        }

        function populateContextDropdowns() {
            loadGalleryData();
        }

        function renderFilteredGallery() {
            const grid = document.getElementById('gallery-grid');
            const empty = document.getElementById('gallery-empty');
            grid.innerHTML = "";
            
            const selectedFolder = document.getElementById('select-folder').value;
            const sortMode = document.getElementById('select-sort').value;
            
            let filtered = [...activeGalleryItems];
            
            // 1. Filter by Folder
            if (selectedFolder !== 'root') {
                filtered = filtered.filter(item => item.context === selectedFolder);
            }
            
            // 2. Extract years and months for timeline
            const yearsMap = new Set();
            filtered.forEach(item => {
                if (item.timestamp) {
                    const year = item.timestamp.substring(0, 4);
                    if (year && !isNaN(year)) yearsMap.add(year);
                }
            });
            
            // Render timeline buttons
            const timelineContainer = document.getElementById('timeline-filters-container');
            timelineContainer.innerHTML = `<button onclick="filterTimeline('All')" class="px-3 py-1 rounded-lg text-xs font-medium ${activeTimelineFilter === 'All' ? 'bg-blue-600 text-white' : 'bg-slate-900 text-slate-400 hover:text-white'}">All</button>`;
            
            Array.from(yearsMap).sort().reverse().forEach(year => {
                timelineContainer.innerHTML += `<button onclick="filterTimeline('${year}')" class="px-3 py-1 rounded-lg text-xs font-medium ${activeTimelineFilter === year ? 'bg-blue-600 text-white' : 'bg-slate-900 text-slate-400 hover:text-white'}">${year}</button>`;
            });

            // 3. Filter by Timeline
            if (activeTimelineFilter !== 'All') {
                filtered = filtered.filter(item => item.timestamp && item.timestamp.startsWith(activeTimelineFilter));
            }

            // 4. Sort
            if (sortMode === 'time-desc') {
                filtered.sort((a, b) => b.timestamp.localeCompare(a.timestamp));
            } else if (sortMode === 'time-asc') {
                filtered.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
            } else if (sortMode === 'name-asc') {
                filtered.sort((a, b) => a.name.localeCompare(b.name));
            } else if (sortMode === 'size-desc') {
                // Approximate since size not loaded initially, but let's fall back
                filtered.sort((a, b) => (b.size || 0) - (a.size || 0));
            }
            
            if (filtered.length === 0) {
                empty.style.display = "flex";
                return;
            }
            
            empty.style.display = "none";
            
            filtered.forEach(item => {
                const ext = item.name.substring(item.name.lastIndexOf('.')).toLowerCase();
                const isImage = ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.heic', '.heif'].includes(ext);
                const isVideo = ['.mp4', '.mov', '.avi', '.mkv'].includes(ext);
                
                let thumbSrc = "";
                if (isImage || isVideo) {
                    thumbSrc = `${activeConnection.url}/api/media/thumbnail/${item.id}?token=${activeConnection.token}`;
                }

                const itemDiv = document.createElement('div');
                itemDiv.className = "glass rounded-2xl overflow-hidden card-hover border border-white/5 cursor-pointer relative group flex flex-col justify-between aspect-square transition-all duration-300";
                itemDiv.onclick = () => openLightbox(item);

                let mediaBlock = "";
                if (thumbSrc) {
                    mediaBlock = `<img src="${thumbSrc}" class="w-full h-full object-cover select-none group-hover:scale-105 transition-all duration-500" loading="lazy">`;
                } else {
                    // Document Icon Placeholder
                    mediaBlock = `
                    <div class="w-full h-full bg-slate-900/50 flex flex-col items-center justify-center p-3 text-slate-500">
                        <svg class="w-10 h-10 mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                        <span class="text-[10px] uppercase font-bold text-slate-600 truncate max-w-full">${ext.replace('.', '')}</span>
                    </div>`;
                }

                itemDiv.innerHTML = `
                    <div class="w-full flex-1 overflow-hidden relative bg-black/20">
                        ${mediaBlock}
                    </div>
                    <div class="p-3 bg-slate-950/80 border-t border-white/5 flex flex-col">
                        <span class="text-xs font-semibold truncate text-slate-200 block">${item.name}</span>
                        <span class="text-[10px] text-slate-500 mt-0.5 block">${item.timestamp ? item.timestamp.substring(0, 10) : 'No Date'}</span>
                    </div>
                `;
                grid.appendChild(itemDiv);
            });
        }

        function filterTimeline(year) {
            activeTimelineFilter = year;
            renderFilteredGallery();
        }

        // Lightbox Media Previewer
        async function openLightbox(item) {
            activePreviewItem = item;
            const modal = document.getElementById('lightbox-modal');
            const loading = document.getElementById('lightbox-loading');
            const img = document.getElementById('lightbox-img');
            const video = document.getElementById('lightbox-video');
            const doc = document.getElementById('lightbox-doc-placeholder');
            
            modal.style.display = "flex";
            loading.style.display = "flex";
            img.style.display = "none";
            video.style.display = "none";
            doc.style.display = "none";
            
            document.getElementById('lbl-lightbox-context').innerText = `Folder: ${item.context || 'root'}`;
            document.getElementById('lbl-lightbox-filename').innerText = item.name;
            document.getElementById('lbl-lightbox-date').innerText = item.timestamp ? item.timestamp.replace('T', ' ').substring(0, 19) : '--';
            document.getElementById('lbl-lightbox-size').innerText = 'Loading...';
            document.getElementById('row-lightbox-gps').style.display = "none";
            
            // Download button configuration
            const dlBtn = document.getElementById('btn-lightbox-download');
            dlBtn.href = `${activeConnection.url}/api/media/file/${item.web_path}?token=${activeConnection.token}`;
            
            // Delete button authorization
            const delBtn = document.getElementById('btn-lightbox-delete');
            delBtn.style.display = activeConnection.role === 'admin' ? 'flex' : 'none';

            // Query complete info metadata from server
            try {
                const infoRes = await fetch(`${activeConnection.url}/api/items/${item.id}/info`, {
                    headers: { 'x-device-token': activeConnection.token }
                });
                if (infoRes.ok) {
                    const info = await infoRes.json();
                    document.getElementById('lbl-lightbox-size').innerText = formatBytes(info.size);
                    if (info.gps) {
                        document.getElementById('row-lightbox-gps').style.display = "block";
                        document.getElementById('lbl-lightbox-gps').innerText = `${info.gps.lat.toFixed(5)}, ${info.gps.lon.toFixed(5)}`;
                    }
                }
            } catch (err) {}

            // Load media correctly based on type
            const ext = item.name.substring(item.name.lastIndexOf('.')).toLowerCase();
            const isImage = ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.heic', '.heif'].includes(ext);
            const isVideo = ['.mp4', '.mov', '.avi', '.mkv'].includes(ext);

            if (isImage) {
                img.src = `${activeConnection.url}/api/media/file/${item.web_path}?token=${activeConnection.token}`;
                img.onload = () => {
                    loading.style.display = "none";
                    img.style.display = "block";
                };
            } else if (isVideo) {
                video.src = `${activeConnection.url}/api/media/file/${item.web_path}?token=${activeConnection.token}`;
                loading.style.display = "none";
                video.style.display = "block";
                video.play();
            } else {
                loading.style.display = "none";
                document.getElementById('lightbox-doc-name').innerText = item.name;
                doc.style.display = "flex";
            }
        }

        function closeLightbox() {
            document.getElementById('lightbox-modal').style.display = "none";
            const video = document.getElementById('lightbox-video');
            video.pause();
            video.src = "";
            activePreviewItem = null;
        }

        async function triggerLocalOpen() {
            if (!activePreviewItem) return;
            const res = await window.pywebview.api.open_file_locally(activePreviewItem.id);
            if (!res) {
                alert("This option is only available for files stored locally in the server directory.");
            }
        }

        async function triggerDeleteAsset() {
            if (!activePreviewItem) return;
            if (confirm(`Are you sure you want to permanently delete "${activePreviewItem.name}"?`)) {
                try {
                    const res = await fetch(`${activeConnection.url}/api/items/${activePreviewItem.id}`, {
                        method: 'DELETE',
                        headers: { 'x-device-token': activeConnection.token }
                    });
                    if (res.ok) {
                        closeLightbox();
                        loadGalleryData();
                    } else {
                        const err = await res.json();
                        alert("Delete error: " + err.detail);
                    }
                } catch (e) {
                    alert("Connection error deleting file.");
                }
            }
        }

        // Native Background uploader callbacks and actions
        async function triggerNativeUpload() {
            const folder = document.getElementById('uploader-context').value;
            const result = await window.pywebview.api.select_and_upload_files(folder);
            if (result.success) {
                document.getElementById('uploader-idle-state').style.display = "none";
                document.getElementById('uploader-active-state').style.display = "flex";
                pollUploadStatus();
            }
        }

        function updateUploadProgress(current, total, filename, percent) {
            document.getElementById('uploader-idle-state').style.display = "none";
            document.getElementById('uploader-active-state').style.display = "flex";
            
            document.getElementById('txt-upload-filename').innerText = filename;
            document.getElementById('txt-upload-queue').innerText = `Uploading file ${current} of ${total}`;
            document.getElementById('txt-upload-percent').innerText = `${percent}%`;
            document.getElementById('bar-upload-percent').style.width = `${percent}%`;
        }

        async function pollUploadStatus() {
            try {
                const status = await window.pywebview.api.get_upload_status();
                if (status.active) {
                    updateUploadProgress(status.current, status.total, status.current_name, status.percent);
                    setTimeout(pollUploadStatus, 300);
                } else {
                    onNativeUploadFinished();
                }
            } catch (e) {}
        }

        function onNativeUploadFinished() {
            document.getElementById('uploader-active-state').style.display = "none";
            document.getElementById('uploader-idle-state').style.display = "flex";
            loadGalleryData();
        }

        // Remote Vault connection
        async function linkRemoteVault() {
            const urlInput = document.getElementById('input-remote-url').value.trim();
            const pinInput = document.getElementById('input-remote-pin').value.trim();
            const btn = document.getElementById('remote-btn');
            const err = document.getElementById('remote-error-msg');
            
            btn.disabled = true;
            btn.innerText = "Linking...";
            err.style.display = "none";

            try {
                const res = await window.pywebview.api.link_remote_vault(urlInput, pinInput);
                if (res.success) {
                    document.getElementById('input-remote-url').value = "";
                    document.getElementById('input-remote-pin').value = "";
                    
                    addLog(`[Client] Remote linked successfully: ${res.settings.url}`);
                    alert("Successfully linked to remote Vault server!");
                    
                    await verifyConnection();
                    switchView('view-gallery');
                } else {
                    err.innerText = res.message;
                    err.style.display = "block";
                }
            } catch(e) {
                err.innerText = "Internal error connecting.";
                err.style.display = "block";
            } finally {
                btn.disabled = false;
                btn.innerText = "Link Server";
            }
        }

        async function disconnectRemoteVault() {
            if (confirm("Disconnect remote server and return to the Local Server?")) {
                const settings = await window.pywebview.api.disconnect_vault();
                addLog("[Client] Reverted connection to local engine.");
                await verifyConnection();
                switchView('view-gallery');
            }
        }

        function addLog(msg) {
            const container = document.getElementById('log-container');
            if (!container) return;
            const div = document.createElement('div');
            const time = new Date().toLocaleTimeString();
            div.innerHTML = `<span class="text-slate-600">[${time}]</span> ${msg}`;
            container.appendChild(div);
            container.scrollTop = container.scrollHeight;
        }

        setInterval(updateStats, 5000);
        setInterval(fetchLogs, 5000);
        
        window.onload = async () => {
             addLog("Verifying client credentials...");
             await verifyConnection();
             
             // If STORAGE_DIR is local, fetch stats
             updateStats();
             fetchLogs();
        };
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    # 1. Register a local admin token transparently so client boots linked by default
    local_token = "desktop_local_admin_token"
    try:
        if local_token not in fastapi_auth.linked_devices:
            fastapi_auth.linked_devices[local_token] = {
                "role": "admin",
                "allowed_folders": ["*"],
                "linked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "last_seen": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            fastapi_auth._save(fastapi_auth.state_file, fastapi_auth.linked_devices)
            print("[AUTH] transparently auto-registered local desktop client token.")
    except Exception as e:
        print(f"[AUTH_WARNING] Could not auto-register local token: {e}")

    # 2. Start FastAPI server in background
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    
    # 3. Wait a bit for the server to be ready
    time.sleep(1.5)

    # 4. Launch the desktop window
    api = Api()
    win = webview.create_window(UI_TITLE, html=HTML_CONTENT, width=1280, height=800, js_api=api)
    
    # Intercept closing: instead of destroying, hide the window (background mode)
    def on_closing():
        win.hide()
        # Returns False to prevent pywebview from closing/destroying the window
        return False
        
    win.events.closing += on_closing
    
    # 5. Start secondary thread for the System Tray
    threading.Thread(target=run_tray, args=(win,), daemon=True).start()

    # 6. Start main UI loop
    webview.start()
