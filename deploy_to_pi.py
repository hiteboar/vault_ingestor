import paramiko
import os

def deploy():
    hostname = '192.168.1.148'
    username = 'hiteboar'
    password = 'Barcallampo13'
    
    # Files to upload
    files_to_upload = [
        ('api/main.py', 'api/main.py'),
        ('version_desktop/console_ui.py', 'version_desktop/console_ui.py')
    ]
    
    print(f"Connecting to {hostname}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(hostname, username=username, password=password, timeout=10)
        print("Connected successfully!")
        
        # Find project directory
        print("Searching for project directory...")
        stdin, stdout, stderr = ssh.exec_command('find ~ -maxdepth 3 -name "vault_ingestor" -type d | head -n 1')
        project_dir = stdout.read().decode('utf-8').strip()
        
        if not project_dir:
            # Maybe inside another vault_ingestor?
            stdin, stdout, stderr = ssh.exec_command('find ~ -maxdepth 4 -name "api" -type d | grep vault_ingestor | head -n 1')
            api_dir = stdout.read().decode('utf-8').strip()
            if api_dir:
                project_dir = os.path.dirname(api_dir)
                
        if not project_dir:
            print("ERROR: Could not find vault_ingestor directory on the remote machine.")
            return
            
        print(f"Project directory found at: {project_dir}")
        
        # SFTP transfer
        sftp = ssh.open_sftp()
        for local_path, remote_rel_path in files_to_upload:
            remote_path = f"{project_dir}/{remote_rel_path}"
            print(f"Uploading {local_path} to {remote_path}...")
            
            # Ensure remote directory exists
            remote_dir = os.path.dirname(remote_path)
            ssh.exec_command(f'mkdir -p {remote_dir}')
            
            sftp.put(local_path, remote_path)
            print("Upload complete.")
        sftp.close()
        
        # Restart the server
        print("Finding and restarting python process...")
        # Check if there's a systemd service
        stdin, stdout, stderr = ssh.exec_command('systemctl list-units --type=service | grep vault')
        services = stdout.read().decode('utf-8')
        
        if 'vault' in services:
            service_name = services.strip().split()[0]
            print(f"Restarting systemd service: {service_name}")
            ssh.exec_command(f'sudo systemctl restart {service_name}')
        else:
            # Fallback to killing python process
            print("No systemd service found, killing running python processes matching vault_ingestor...")
            ssh.exec_command("pkill -f 'uvicorn api.main:app'")
            ssh.exec_command("pkill -f 'console_ui.py'")
            
            print("If the server was running in a screen/tmux or systemd, you might need to restart it manually.")
            
        print("Done! Updates deployed to Raspberry Pi.")
        
    except Exception as e:
        print(f"Deployment failed: {e}")
    finally:
        ssh.close()

if __name__ == '__main__':
    deploy()
