import paramiko
import os
import sys
import time

import getpass

def deploy():
    hostname = os.getenv("PI_HOSTNAME", "192.168.1.148")
    username = os.getenv("PI_USERNAME", "hiteboar")
    password = os.getenv("PI_PASSWORD")
    if not password:
        password = getpass.getpass(f"Ingresa la contraseña SSH para {username}@{hostname}: ")
    
    # Comandos a ejecutar en orden
    commands = [
        # 1. Asegurar dependencias de sistema
        f"echo {password} | sudo -S apt-get update && echo {password} | sudo -S apt-get install -y libssl-dev libffi-dev python3-dev",
        
        # 2. Actualizar repositorio
        "cd ~/vault_ingestor && git checkout MobileApp && git pull origin MobileApp",
        
        # 3. Configurar .env si no tiene el acceso remoto
        "grep -q 'ENABLE_REMOTE_ACCESS=true' ~/vault_ingestor/.env || echo 'ENABLE_REMOTE_ACCESS=true' >> ~/vault_ingestor/.env",
        
        # 4. Deshabilitar reload en app.py para evitar errores de puerto en servidor
        "sed -i 's/reload=True/reload=False/g' ~/vault_ingestor/app.py",
        
        # 5. Ejecutar setup de venv y dependencias python
        "cd ~/vault_ingestor && bash version_pi/setup_pi.sh",
        
        # 6. Limpieza agresiva de procesos viejos si los hubiera manualmente
        f"echo {password} | sudo -S systemctl stop vault_ingestor || true",
        f"echo {password} | sudo -S fuser -k 8000/tcp || true",
        f"echo {password} | sudo -S fuser -k 8001/tcp || true",
        f"echo {password} | sudo -S killall -9 python || true",
        
        # 7. Crear archivo de servicio Systemd para el arranque automático delegando en el Supervisor
        f"echo -e '[Unit]\\nDescription=Vault Ingestor API\\nAfter=network.target\\n\\n[Service]\\nUser={username}\\nWorkingDirectory=/home/{username}/vault_ingestor\\nExecStart=/home/{username}/vault_ingestor/.venv/bin/python /home/{username}/vault_ingestor/version_pi/autorun_pi.py\\nRestart=always\\nRestartSec=10\\nStandardOutput=append:/home/{username}/vault_ingestor/vault_app.log\\nStandardError=append:/home/{username}/vault_ingestor/vault_app.log\\n\\n[Install]\\nWantedBy=multi-user.target' > ~/vault_ingestor.service",
        f"echo {password} | sudo -S mv ~/vault_ingestor.service /etc/systemd/system/",
        f"echo {password} | sudo -S systemctl daemon-reload",
        f"echo {password} | sudo -S systemctl enable vault_ingestor",
        
        # 8. Arranque limpio en background persistente
        "rm ~/vault_ingestor/vault_app.log || true",
        f"echo {password} | sudo -S systemctl restart vault_ingestor",
        
        # 9. Verificación
        "sleep 5 && tail -n 15 ~/vault_ingestor/vault_app.log"
    ]
    
    try:
        if sys.platform == "win32":
            import io
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        print(f"[*] Conectando a {hostname}...")
        client.connect(hostname, username=username, password=password)
        
        for cmd in commands:
            print(f"\n[*] Ejecutando: {cmd}")
            stdin, stdout, stderr = client.exec_command(cmd, get_pty=True)
            
            # Leer salida en tiempo real
            while not stdout.channel.exit_status_ready():
                if stdout.channel.recv_ready():
                    data = stdout.channel.recv(1024).decode('utf-8', errors='replace')
                    print(data, end='')
                time.sleep(0.1)
            
            # Leer restante
            print(stdout.read().decode('utf-8', errors='replace'), end='')
                
        client.close()
        print("\n[*] Despliegue completado.")
        
    except Exception as e:
        print(f"\n[!] Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    deploy()
