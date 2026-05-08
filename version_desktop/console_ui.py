import os
import threading
import time
import sys
from pathlib import Path

# Ensure core is importable from the subfolder
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

import webview
import uvicorn
import pystray
from PIL import Image, ImageDraw
from api.main import app as fastapi_app
from app import bootstrap # Import startup logic from app.py

# Basic configuration
API_PORT = int(os.getenv("API_PORT", "8001"))
API_URL = f"http://localhost:{API_PORT}"
UI_TITLE = "Vault Ingestor - Management Console"

def run_server():
    """Launches the FastAPI server in a separate thread."""
    # Ensure bootstrap runs before starting uvicorn
    bootstrap()
    uvicorn.run(fastapi_app, host="0.0.0.0", port=API_PORT)

class Api:
    """Bridge class between Python and JavaScript."""
    def get_status(self):
        # This function can call the backend directly or be a wrapper
        return {"status": "ok", "message": "Console Bridge Active"}

    def open_folder(self, path):
        """Opens a folder in Windows explorer."""
        if os.name == "nt":
            os.startfile(path)
        return True

def run_tray(window):
    """Runs the icon in the system tray in the background."""
    def create_image():
        # Generate a stylized icon programmatically
        image = Image.new('RGBA', (64, 64), color=(0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        # Rounded dark background
        draw.rounded_rectangle((4, 4, 60, 60), radius=16, fill=(15, 23, 42))
        # Blue accent
        draw.ellipse((20, 20, 44, 44), fill=(59, 130, 246))
        return image

    def on_open(icon, item):
        window.show()

    def on_exit(icon, item):
        icon.stop()
        os._exit(0) # Forcefully shut down all daemon threads (FastAPI, Webview and Pystray)

    menu = pystray.Menu(
        pystray.MenuItem('Open Dashboard', on_open, default=True),
        pystray.MenuItem('Stop and Exit', on_exit)
    )
    
    icon = pystray.Icon("Vault Ingestor", create_image(), "Vault Ingestor", menu)
    icon.run()

# Full HTML with Tailwind and Premium design
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vault Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Outfit', sans-serif; background: #0f172a; color: white; overflow: hidden; }
        .glass { background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(12px); border: 1px solid rgba(255,255,255,0.1); }
        .sidebar { width: 260px; height: 100vh; }
        .main-content { height: 100vh; overflow-y: auto; }
        .radial-bg { background: radial-gradient(circle at 50% 50%, #1e1b4b 0%, #0f172a 100%); }
        .nav-btn { cursor: pointer; }
        .nav-active { background: rgba(59, 130, 246, 0.1); color: #60a5fa; font-weight: 600; border-radius: 0.75rem; }
    </style>
</head>
<body class="radial-bg">
    <div class="flex h-screen w-screen">
        <!-- Sidebar -->
        <div class="sidebar glass p-6 flex flex-col justify-between">
            <div>
                <div class="flex items-center gap-3 mb-10">
                    <div class="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center shadow-lg shadow-blue-500/50">
                        <svg class="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                        </svg>
                    </div>
                    <span class="text-xl font-semibold tracking-tight">Vault Ingestor</span>
                </div>
                
                <nav class="space-y-2">
                    <a id="btn-nav-dashboard" onclick="switchView('view-dashboard')" class="nav-btn flex items-center gap-3 text-slate-400 hover:text-white transition-colors p-3 nav-active">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"/></svg>
                        Dashboard
                    </a>
                    
                    <a id="btn-nav-config" onclick="switchView('view-config')" class="nav-btn flex items-center gap-3 text-slate-400 hover:text-white transition-colors p-3 rounded-xl mt-2">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37a1.724 1.724 0 002.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
                        Configuration Wizard
                    </a>

                    <a id="btn-nav-mobile" onclick="switchView('view-mobile')" class="nav-btn flex items-center gap-3 text-slate-400 hover:text-white transition-colors p-3 rounded-xl mt-2">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>
                        Link Mobile App
                    </a>
                </nav>
            </div>

            <div class="p-4 bg-white/5 rounded-2xl">
                <div class="text-xs text-slate-500 uppercase font-bold mb-2">Engine Status</div>
                <div class="flex items-center gap-2">
                    <div class="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                    <span class="text-sm">Online</span>
                </div>
            </div>
        </div>

        <!-- Main Content -->
        <div class="main-content flex-1 p-10">
            
            <!-- ====== VIEW: DASHBOARD ====== -->
            <div id="view-dashboard">
                <header class="flex justify-between items-center mb-10">
                    <h1 class="text-3xl font-bold">System Monitor</h1>
                    <div class="flex gap-4">
                        <button onclick="updateStats()" class="p-2 glass rounded-lg hover:bg-white/10 transition-all text-blue-400">
                            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
                        </button>
                    </div>
                </header>

                <div class="grid grid-cols-3 gap-6 mb-10">
                    <div class="glass p-6 rounded-3xl relative overflow-hidden group">
                        <div class="z-10 relative">
                            <div class="text-slate-400 text-sm mb-1 uppercase font-bold">Storage</div>
                            <div id="disk-text" class="text-4xl font-bold">-- %</div>
                            <div class="w-full bg-white/10 h-2 rounded-full mt-4 overflow-hidden">
                                <div id="disk-bar" class="bg-blue-500 h-full transition-all duration-1000" style="width: 0%"></div>
                            </div>
                        </div>
                    </div>

                    <div class="glass p-6 rounded-3xl">
                        <div class="text-slate-400 text-sm mb-1 uppercase font-bold">CPU Load</div>
                        <div id="cpu-text" class="text-4xl font-bold">-- %</div>
                        <div class="w-full bg-white/10 h-2 rounded-full mt-4 overflow-hidden">
                            <div id="cpu-bar" class="bg-purple-500 h-full transition-all duration-1000" style="width: 0%"></div>
                        </div>
                    </div>

                    <div class="glass p-6 rounded-3xl">
                        <div class="text-slate-400 text-sm mb-1 uppercase font-bold">RAM Usage</div>
                        <div id="ram-text" class="text-4xl font-bold">-- %</div>
                        <div class="w-full bg-white/10 h-2 rounded-full mt-4 overflow-hidden">
                            <div id="ram-bar" class="bg-cyan-500 h-full transition-all duration-1000" style="width: 0%"></div>
                        </div>
                    </div>
                </div>

                <div class="glass rounded-3xl p-8 h-[400px] flex flex-col">
                    <div class="flex justify-between items-center mb-6">
                        <h2 class="text-xl font-bold">Latest Activity</h2>
                        <span class="text-xs text-slate-500">Live logs</span>
                    </div>
                    <div id="log-container" class="flex-1 overflow-y-auto font-mono text-sm text-slate-300 space-y-2 pr-4 custom-scrollbar">
                        <div class="text-slate-500">[System] Initializing interface...</div>
                    </div>
                </div>
            </div>

            <!-- ====== VIEW: CONFIGURATION ====== -->
            <div id="view-config" style="display: none;">
                <header class="flex justify-between items-center mb-10">
                    <h1 class="text-3xl font-bold">Configuration Wizard</h1>
                </header>

                <div class="glass rounded-3xl p-8 max-w-3xl">
                    <p class="text-slate-300 mb-8 font-light text-lg">Visually configure your central storage engine options.</p>
                    
                    <form id="config-form" class="space-y-6" onsubmit="event.preventDefault(); saveConfig();">
                        <div class="bg-white/5 p-6 rounded-2xl border border-white/5">
                            <label class="block text-sm font-semibold mb-2 text-cyan-300">Main Storage Folder (STORAGE_DIR)</label>
                            <p class="text-xs text-slate-400 mb-3">Absolute or relative path where processed files and their metadata will be saved.</p>
                            <input type="text" id="input-STORAGE_DIR" placeholder="e.g.: vault_storage" class="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-cyan-500 transition-colors">
                        </div>

                        <div class="bg-white/5 p-6 rounded-2xl border border-white/5 mt-4">
                            <label class="flex items-center gap-3 cursor-pointer">
                                <input type="checkbox" id="input-ENABLE_REMOTE_ACCESS" class="w-5 h-5 accent-cyan-500 bg-black/40 border border-white/10 rounded-lg">
                                <span class="text-sm font-semibold text-cyan-300">Enable Remote Access via Internet</span>
                            </label>
                            <p class="text-xs text-slate-400 mt-2">Generates a secure and temporary URL (Cloudflare) so your mobile can connect without being on the same WiFi. The URL will change after each restart.</p>
                        </div>
                        
                        <div class="pt-6 flex justify-end">
                            <button type="submit" id="save-btn" class="bg-blue-600 hover:bg-blue-500 text-white px-8 py-3 rounded-xl font-semibold transition-colors shadow-lg shadow-blue-500/40">Save Changes</button>
                        </div>
                        <div id="save-message" class="text-right text-sm text-green-400 font-medium hidden">Saved successfully!</div>
                    </form>
                </div>
            </div>

            <!-- ====== VIEW: MOBILE LINKING ====== -->
            <div id="view-mobile" style="display: none;">
                <header class="mb-10">
                    <h1 class="text-3xl font-bold">Link Mobile Device</h1>
                    <p class="text-slate-400 mt-2">Connect your Android phone to manage the Vault from anywhere.</p>
                </header>

                <div class="grid grid-cols-2 gap-10">
                    <div class="glass rounded-3xl p-8 flex flex-col items-center">
                        <div class="w-full text-center mb-6">
                            <h2 class="text-xl font-bold">1. Scan the code</h2>
                            <p class="text-sm text-slate-400 mt-1">Open the Vault App on your mobile and choose "Link".</p>
                        </div>
                        
                        <div class="bg-white p-4 rounded-3xl shadow-2xl shadow-blue-500/20 mb-6">
                            <img id="pairing-qr" src="" alt="Pairing QR" class="w-64 h-64">
                        </div>
                        
                        <button onclick="generatePairing()" class="text-blue-400 hover:text-blue-300 text-sm flex items-center gap-2">
                             <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
                             Generate new code
                        </button>
                    </div>

                    <div class="space-y-6">
                        <div class="glass rounded-3xl p-8">
                            <h2 class="text-xl font-bold mb-4">2. Enter the PIN</h2>
                            <p class="text-sm text-slate-400 mb-6">If the camera doesn't work, enter this code manually in the App.</p>
                            
                            <div id="pairing-pin" class="text-6xl font-black tracking-widest text-center py-6 bg-white/5 rounded-2xl text-blue-500 border border-blue-500/20">
                                ------
                            </div>
                            
                            <div class="mt-4 text-center">
                                <span class="text-xs text-slate-500 uppercase font-bold">Valid for 5 minutes</span>
                            </div>
                        </div>

                        <div class="bg-blue-600/10 border border-blue-500/20 rounded-3xl p-8">
                            <h3 class="font-bold flex items-center gap-2 text-blue-400 mb-2">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                What does this allow?
                            </h3>
                            <ul class="text-sm text-slate-300 space-y-2 list-disc list-inside">
                                <li>View images without downloading them</li>
                                <li>Upload photos directly from your mobile</li>
                                <li>See storage status in real time</li>
                                <li>Secure access via cryptographic token</li>
                            </ul>
                        </div>
                    </div>
                </div>
            </div>

        </div>
    </div>

    <script>
        function switchView(viewId) {
            document.getElementById('view-dashboard').style.display = 'none';
            document.getElementById('view-config').style.display = 'none';
            document.getElementById('view-mobile').style.display = 'none';
            
            document.getElementById('btn-nav-dashboard').classList.remove('nav-active');
            document.getElementById('btn-nav-config').classList.remove('nav-active');
            document.getElementById('btn-nav-mobile').classList.remove('nav-active');
            
            document.getElementById(viewId).style.display = 'block';
            document.getElementById('btn-nav-' + viewId.replace('view-', '')).classList.add('nav-active');
            
            if(viewId === 'view-config') {
                loadConfig();
            }
            if(viewId === 'view-mobile') {
                generatePairing();
            }
        }

        async function generatePairing() {
            try {
                // Get PIN and pairing session URL
                const response = await fetch('/api/auth/request');
                const data = await response.json();
                
                document.getElementById('pairing-pin').innerText = data.pin;
                
                // Load the QR representing the same session
                const qrImg = document.getElementById('pairing-qr');
                qrImg.src = '/api/auth/qr?t=' + Date.now();
                
            } catch (e) {
                console.error("Error generating pairing", e);
            }
        }

        async function loadConfig() {
            try {
                const response = await fetch('/api/config');
                const data = await response.json();
                
                document.getElementById('input-STORAGE_DIR').value = data.STORAGE_DIR || '';
                document.getElementById('input-ENABLE_REMOTE_ACCESS').checked = String(data.ENABLE_REMOTE_ACCESS).toLowerCase() === 'true';
                
            } catch (e) {
                console.error("Error fetching config", e);
            }
        }

        async function updateSingleConfig(key, value) {
            if (!value || value.trim() === '') return;
            await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key: key, value: value.trim() })
            });
        }

        async function saveConfig() {
            const btn = document.getElementById('save-btn');
            const msg = document.getElementById('save-message');
            btn.innerText = "Saving...";
            btn.disabled = true;
            
            try {
                await updateSingleConfig('STORAGE_DIR', document.getElementById('input-STORAGE_DIR').value);
                await updateSingleConfig('ENABLE_REMOTE_ACCESS', document.getElementById('input-ENABLE_REMOTE_ACCESS').checked ? 'true' : 'false');
                
                addLog("[Config] Environment updated. Some changes may require restarting the application.");
                
                msg.style.display = 'block';
                setTimeout(() => { msg.style.display = 'none'; }, 3000);
                
                loadConfig(); 
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
        
        window.onload = async () => {
             addLog("[System] Verifying installation environment...");
             setTimeout(async () => {
                 try {
                     const response = await fetch('/api/config');
                     const data = await response.json();
                     
                     // If critical values are not configured, force wizard
                     if (data.STORAGE_DIR === '') {
                         addLog("[System] First run: Starting configuration wizard...");
                         switchView('view-config');
                     } else {
                         addLog("Dashboard ready and connected.");
                         updateStats();
                         // Show QR by default on first successful start
                         switchView('view-mobile');
                     }
                 } catch (e) {
                     // If it fails, go to default dashboard
                     updateStats();
                 }
             }, 1000);
        };
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    # 1. Start FastAPI server in background
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    
    # 2. Wait a bit for the server to be ready
    time.sleep(1.5)

    # 3. Launch the desktop window
    api = Api()
    win = webview.create_window(UI_TITLE, html=HTML_CONTENT, width=1280, height=800, js_api=api)
    
    # Intercept closing: instead of destroying, hide the window (background mode)
    def on_closing():
        win.hide()
        # Notify user the first time it hides
        return False
        
    win.events.closing += on_closing
    
    # 4. Start secondary thread for the System Tray
    threading.Thread(target=run_tray, args=(win,), daemon=True).start()

    # 5. Start main UI loop
    webview.start()
