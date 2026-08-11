import sys
import os
import platform
import subprocess
import socket

def check_module(module_name):
    try:
        __import__(module_name)
        return True, "✅ Installed"
    except ImportError as e:
        return False, f"❌ Not found ({str(e)})"

def is_venv():
    return sys.prefix != sys.base_prefix

def test_port(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def main():
    print("=== Vault Ingestor: Environment Diagnostics (Raspberry Pi) ===")
    print(f"Operating System: {platform.system()} {platform.release()}")
    print(f"Python Version  : {sys.version.split()[0]}")
    print(f"Virtual Env     : {'✅ Yes' if is_venv() else '⚠️  No (System)'}")
    
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    print(f"Working Directory: {project_dir}")
    print("-" * 40)
    
    modules = [
        "dotenv",           
        "fastapi",
        "uvicorn",
        "PIL",               # Pillow requires compilation sometimes
        "pycloudflared"      # Remote tunnel (Fallback)
    ]
    
    print("Critical Modules and Network Dependencies:")
    all_found = True
    for mod in modules:
        found, status = check_module(mod)
        print(f"  - {mod:20}: {status}")
        if not found and mod != "pycloudflared": # pycloudflared is optional if the official binary is present
            all_found = False
            
    # Check for the official cloudflared binary
    try:
        import subprocess
        subprocess.run(["cloudflared", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        print(f"  - {'cloudflared (bin)':20}: ✅ Installed (Native)")
    except Exception:
        print(f"  - {'cloudflared (bin)':20}: ⚠️  Not found (Using Fallback)")
        
    print("-" * 40)
    print("Network Status and Vault Ingestor Processes:")
    
    # Check port 8000 or 8001
    port_open = test_port(8000) or test_port(8001)
    if port_open:
        print("  - API (8000/8001)       : ✅ Listening and ready")
    else:
        print("  - API (8000/8001)       : ⚠️  Closed or Not Available")
        
    print("-" * 40)
    print("Remote Access Configuration:")
    
    # Try to load .env to read real values
    try:
        from dotenv import load_dotenv
        env_path = os.path.join(project_dir, ".env")
        load_dotenv(dotenv_path=env_path)
    except ImportError:
        pass
        
    remote_enabled = os.getenv("ENABLE_REMOTE_ACCESS", "false").lower() == "true"
    print(f"  - Remote Access Enabled: {'✅ Yes' if remote_enabled else '❌ No (Local Only)'}")
    
    public_url = os.getenv("PUBLIC_URL")
    if public_url:
        print(f"  - Public URL Detected    : ✅ {public_url}")
    elif remote_enabled:
        print(f"  - .env Configured        : {'✅ OK' if os.path.exists(os.path.join(project_dir, '.env')) else '❌ Missing .env file'}")
        print(f"  - Public URL             : ⚠️  Waiting for tunnel startup (check logs)...")
    
    print("-" * 40)
    
    if not all_found:
        print("⚠️  Critical dependencies missing.")
        print("Please run ./version_pi/tools/repair_system.sh to get everything ready.")
    else:
        print("✅ Key operative dependencies are correctly installed.")
        print("To track network activity or possible failures, check the master log:")
        print(f"  tail -n 20 {os.path.join(project_dir, 'app.log')}")

if __name__ == "__main__":
    main()
