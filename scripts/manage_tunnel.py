import os
import subprocess
import time
import sys
from pathlib import Path

def update_env(public_url):
    env_path = Path(".env")
    if not env_path.exists():
        print("[!] .env file not found")
        return

    content = env_path.read_text()
    lines = content.splitlines()
    new_lines = []
    found = False
    
    for line in lines:
        if line.startswith("PUBLIC_URL="):
            new_lines.append(f"PUBLIC_URL={public_url}")
            found = True
        else:
            new_lines.append(line)
            
    if not found:
        new_lines.append(f"PUBLIC_URL={public_url}")
        
    env_path.write_text("\n".join(new_lines))
    print(f"[*] .env file updated with: {public_url}")

def start_tunnel():
    print("[*] Starting Cloudflare tunnel...")
    port = os.getenv("API_PORT", "8000")
    
    # Try to use cloudflared directly
    try:
        # Start an ephemeral tunnel (Quick Tunnel)
        process = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", f"http://localhost:{port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        url = None
        for line in process.stdout:
            print(line, end="")
            if "trycloudflare.com" in line:
                # Extract the URL
                parts = line.split()
                for p in parts:
                    if "https://" in p and "trycloudflare.com" in p:
                        url = p.strip()
                        break
            if url:
                update_env(url)
                print(f"\n[✔] TUNNEL READY: {url}")
                print("[*] You can now generate a QR code from the app and it will work anywhere.")
                break
                
        process.wait()
    except FileNotFoundError:
        print("[!] Error: 'cloudflared' is not installed on the system.")
        print("[*] Download it from: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/install-run/")
    except Exception as e:
        print(f"[!] Error: {e}")

if __name__ == "__main__":
    start_tunnel()
