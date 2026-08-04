import os
import sys
import time
import requests
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.manager import UpdateManager
from app import is_storage_ready, bootstrap

def send_telegram_message(token, chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.json()
    except Exception as e:
        print(f"[!] Error sending Telegram message: {e}")
        return None

def edit_telegram_message(token, chat_id, message_id, text):
    url = f"https://api.telegram.org/bot{token}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception:
        pass

def wait_for_telegram_reply(token, chat_id, timeout=60):
    """
    Polls getUpdates looking for a callback_query.
    Returns True if 'yes', False if 'no' or timeout.
    """
    print(f"[*] Waiting {timeout}s for Telegram response...")
    start_time = time.time()
    offset = None

    while time.time() - start_time < timeout:
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        params = {"timeout": 5, "allowed_updates": ["callback_query"]}
        if offset:
            params["offset"] = offset

        try:
            res = requests.get(url, params=params, timeout=10)
            if res.status_code == 200:
                data = res.json()
                if data.get("ok"):
                    for update in data.get("result", []):
                        offset = update["update_id"] + 1
                        if "callback_query" in update:
                            cb = update["callback_query"]
                            cb_data = cb.get("data", "")
                            cb_from = str(cb.get("from", {}).get("id"))
                            
                            # Answer callback query to stop loading circle
                            requests.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery", 
                                          json={"callback_query_id": cb["id"]}, timeout=5)

                            if cb_from == str(chat_id):
                                if cb_data.startswith("boot_update_yes"):
                                    return True
                                elif cb_data == "boot_update_no":
                                    return False
        except Exception as e:
            print(f"[!] Polling error: {e}")
            
        time.sleep(1)

    print("[*] Timeout reached without response.")
    return False

def main():
    print("==========================================")
    print("   Vault Ingestor: Boot Updater & Health Check")
    print("==========================================")
    
    bootstrap()
    
    storage_dir_str = os.getenv("STORAGE_DIR", "./vault_storage")
    storage_dir = Path(storage_dir_str).resolve()
    
    # 1. Validar Almacenamiento
    storage_ready, storage_error = is_storage_ready(storage_dir)
    if not storage_ready:
        print(f"[!] ADVERTENCIA: El almacenamiento no está listo o montado.")
        print(f"    Razón: {storage_error}")
        print("    Saltando comprobación de actualizaciones para proteger los datos.")
        sys.exit(0)
        
    print(f"[*] Almacenamiento validado correctamente: {storage_dir}")
    
    # 2. Inicializar Gestor de Actualizaciones
    manager = UpdateManager(PROJECT_ROOT, storage_dir)
    
    # 3. Comprobar si hay un test de salud pendiente por un reinicio de actualización
    manager.verify_health_or_rollback()
    
    # 4. Intentar realizar una actualización interactiva
    has_updates, new_tag = manager.check_git_updates()
    
    if has_updates:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("ADMIN_CHAT_ID")
        
        if not token or not chat_id:
            print("[!] Token de Telegram o Admin Chat ID no configurados. Omitiendo actualización interactiva.")
            sys.exit(0)
            
        print(f"[*] Se ha detectado la versión {new_tag}. Solicitando permiso por Telegram...")
        
        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "✅ Sí, Actualizar", "callback_data": f"boot_update_yes_{new_tag}"},
                    {"text": "❌ Omitir", "callback_data": "boot_update_no"}
                ]
            ]
        }
        
        msg_text = (
            f"🔄 *Actualización Detectada durante el Arranque*\n\n"
            f"Se ha detectado una nueva versión en GitHub: `{new_tag}`\n\n"
            f"¿Deseas aplicar esta actualización ahora mismo antes de arrancar el sistema?\n\n"
            f"⏳ _Tienes 60 segundos para responder._"
        )
        
        msg_data = send_telegram_message(token, chat_id, msg_text, reply_markup)
        
        should_update = False
        msg_id = None
        if msg_data and msg_data.get("ok"):
            msg_id = msg_data["result"]["message_id"]
            should_update = wait_for_telegram_reply(token, chat_id, timeout=60)
            
        if should_update:
            if msg_id:
                edit_telegram_message(token, chat_id, msg_id, f"✅ *Actualizando a {new_tag}...*")
            manager.apply_update(new_tag)
        else:
            if msg_id:
                edit_telegram_message(token, chat_id, msg_id, f"⏭️ *Actualización a {new_tag} omitida.* Continuando el arranque normal.")
            print("[*] Actualización cancelada/omitida. Continuando arranque...")
            
    print("[*] Proceso de arranque completado.")

if __name__ == "__main__":
    main()
