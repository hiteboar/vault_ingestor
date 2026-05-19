from __future__ import annotations
import os
import asyncio
from datetime import datetime, timezone
from typing import Iterator, Optional, Set, List
import shutil
import subprocess
import requests
import json
import io
import qrcode
from pathlib import Path

from telegram import Update, Bot
from telegram.ext import Application, MessageHandler, ContextTypes, filters

from core.models import IncomingMedia
from core.pipeline import process_one
from core.state import ChatStateStore
from core.storage import sanitize_context
from core.dedup import HashIndex
from core.agent import LLMAgent

class TelegramAdapter:
    def __init__(
        self,
        token: str,
        base_dir,
        meta_log,
        state_store: ChatStateStore,
        hash_index: HashIndex,
        default_context: str = "default",
        require_original_default: bool = False,
        allowed_chat_ids: Optional[Set[int]] = None,
        max_bytes: Optional[int] = None,
        update_manager=None,
        env_path: Optional[Path] = None,
        reduced_mode: bool = False,
        reduced_mode_error: str = None,
    ):
        self.token = token
        self.base_dir = base_dir
        self.upload_dir = base_dir / "uploaded_files"
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.meta_log = meta_log
        self.state_store = state_store
        self.hash_index = hash_index
        self.default_context = sanitize_context(default_context)
        self.require_original_default = require_original_default
        self.allowed_chat_ids = allowed_chat_ids or set()
        self.max_bytes = max_bytes
        self.update_manager = update_manager
        self.env_path = env_path or Path(".env")
        self.bot = Bot(token)
        self.reduced_mode = reduced_mode
        self.reduced_mode_error = reduced_mode_error
        
        # Iniciar agente IA
        self.agent = LLMAgent()

    def _is_allowed(self, update: Update) -> bool:
        if not self.allowed_chat_ids:
            return True
        chat = update.effective_chat
        if not chat:
            return False
        return chat.id in self.allowed_chat_ids

    def _is_admin(self, update: Update) -> bool:
        return self._is_allowed(update)

    async def _handle_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        msg = update.effective_message
        chat = update.effective_chat
        if not msg or not chat or not msg.text:
            return False

        text = msg.text.strip()
        if not text.startswith("/"):
            return False

        parts = text.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1].strip() if len(parts) > 1 else ""

        chat_id = str(chat.id)
        is_admin = self._is_admin(update)

        if command == "/system_reboot":
            return await self._cmd_system_reboot(msg, is_admin)
        elif command == "/get_access":
            return await self._cmd_get_access(msg, is_admin)
        elif command == "/status":
            return await self._cmd_status(msg, chat_id, is_admin)
        elif command == "/help":
            return await self._cmd_help(msg, is_admin)
        elif command == "/resetservice":
            # Alias for backward compatibility if user types it out of habit
            return await self._cmd_get_access(msg, is_admin)
            
        # Desactivamos los comandos antiguos.
        return False

    async def _cmd_system_reboot(self, msg, is_admin: bool) -> bool:
        if not is_admin:
            await msg.reply_text("⛔ Solo administradores.")
            return True
        await msg.reply_text("🔄 Reiniciando el sistema Raspberry Pi en 3 segundos...")
        await asyncio.sleep(3)
        try:
            subprocess.run(["sudo", "reboot"], check=False)
        except Exception as e:
            await msg.reply_text(f"❌ Error al reiniciar: {e}")
        return True

    async def _cmd_status(self, msg, chat_id: str, is_admin: bool) -> bool:
        if not is_admin:
            await msg.reply_text("⛔ Solo administradores.")
            return True

        # Espacio en disco
        total, used, free = shutil.disk_usage(self.base_dir)
        pct = (used / total) * 100

        # RAM
        import psutil
        mem = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.5)

        # Estado de la API (Servicio independiente)
        api_status = self._get_service_status("vault_api")
        bot_status = self._get_service_status("vault_bot")

        text = (
            "📊 *Estado del Sistema*\n\n"
            f"🚀 *API Storage:* {api_status}\n"
            f"🤖 *Bot Agent:* {bot_status}\n\n"
            f"🧠 *CPU:* {cpu}%\n"
            f"⚡ *RAM:* {mem.percent}% ({mem.used / (1024**3):.1f}GB / {mem.total / (1024**3):.1f}GB)\n"
            f"💾 *Disco:* {pct:.1f}% ocupado\n"
            f"└ Libre: {free / (1024**3):.1f} GB de {total / (1024**3):.1f} GB\n"
        )
        await msg.reply_text(text, parse_mode="Markdown")
        return True

    def _get_service_status(self, service_name: str) -> str:
        if os.name != "posix":
            return "N/A (Windows)"
        try:
            res = subprocess.run(["systemctl", "is-active", service_name], capture_output=True, text=True, timeout=2)
            status = res.stdout.strip()
            if status == "active": return "✅ Online"
            if status == "inactive": return "⚪ Offline"
            if status == "failed": return "🔴 Error"
            return f"❓ {status}"
        except Exception:
            return "❔ Desconocido"

    async def _cmd_help(self, msg, is_admin: bool) -> bool:
        if not is_admin:
            return True

        help_text = (
            "🤖 *Vault OS Agent - Comandos Administrativos*\n\n"
            "/system_reboot  → Reinicia la Raspberry Pi\n"
            "/get_access     → Reinicia la API y muestra QR de vinculación\n"
            "/status         → Ver métricas (CPU, RAM, Disco) y servicios\n"
            "/help           → Muestra este menú\n\n"
            "💬 *Asistente IA*: Cualquier otro mensaje de texto será procesado "
            "automáticamente por el Agente de IA para administración y desarrollo."
        )
        await msg.reply_text(help_text, parse_mode="Markdown")
        return True

    async def _notify_reset_complete(self, target_chat: str, application: Optional[Application] = None):
        """Espera a que la API esté lista y envía el QR al usuario."""
        bot = application.bot if application else self.bot
        reset_file = self.base_dir / "state" / ".reset_pending"

        if not reset_file.exists():
            return

        print(f"[reset] Iniciando espera de API para chat {target_chat}...")
        try:
            await bot.send_message(chat_id=target_chat, text="⏳ El sistema se está reiniciando. Te avisaré en cuanto la conexión esté lista...")

            port = int(os.getenv("API_PORT", "8001"))
            recovery_param = ""
            recovery_file = Path("vault_internal/.recovery_token")
            if recovery_file.exists():
                recovery_param = f"?recovery={recovery_file.read_text().strip()}"
            
            api_url = f"http://localhost:{port}/api/auth/request{recovery_param}"
            
            data = None
            for i in range(20):
                if not reset_file.exists():
                    return
                try:
                    resp = requests.get(api_url, timeout=5)
                    if resp.status_code == 200:
                        data = resp.json()
                        break
                    elif resp.status_code == 403:
                        await bot.send_message(chat_id=target_chat, text="⚠️ El sistema ha arrancado pero el dispositivo administrador ya está vinculado.")
                        if reset_file.exists(): reset_file.unlink()
                        return
                except:
                    await asyncio.sleep(3)
            
            if data and reset_file.exists():
                url = data['url']
                pin = data['pin']
                
                qr = qrcode.QRCode(version=1, box_size=10, border=1)
                qr.add_data(json.dumps({"url": url, "pin": pin}))
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG')
                img_byte_arr.seek(0)
                
                await bot.send_photo(
                    chat_id=target_chat,
                    photo=img_byte_arr,
                    caption=(
                        "✅ *Sistema Listo*\n\n"
                        f"🔗 *URL:* `{url}`\n"
                        f"🔢 *PIN:* `{pin}`\n\n"
                        "Ya puedes vincular tu dispositivo móvil."
                    ),
                    parse_mode="Markdown"
                )
                if reset_file.exists(): reset_file.unlink()
            elif reset_file.exists():
                await bot.send_message(chat_id=target_chat, text="❌ La API tardó demasiado en responder. Prueba a usar `/status` en unos momentos.")
                if reset_file.exists(): reset_file.unlink()
                
        except Exception as e:
            print(f"[error] Notify reset failure: {e}")

    async def _cmd_get_access(self, msg, is_admin: bool) -> bool:
        if not is_admin:
            await msg.reply_text("⛔ Solo administradores.")
            return True
            
        chat_id = str(msg.chat_id)
        try:
            reset_file = self.base_dir / "state" / ".reset_pending"
            reset_file.parent.mkdir(parents=True, exist_ok=True)
            reset_file.write_text(chat_id, encoding="utf-8")
        except Exception as e:
            await msg.reply_text(f"❌ Error al preparar el reinicio: {e}")
            return True

        await msg.reply_text("🔄 Reiniciando API de almacenamiento y actualizando conexión...\nEspera unos segundos.", parse_mode="Markdown")
        
        try:
            subprocess.Popen(["bash", "run_vault.sh"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            asyncio.create_task(self._notify_reset_complete(chat_id))
        except Exception as e:
            await msg.reply_text(f"❌ Error al lanzar el script: {e}")
            if reset_file.exists(): reset_file.unlink()
            
        return True

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = update.effective_message
        if not msg:
            return

        chat = update.effective_chat
        if not self._is_allowed(update):
            # Strict mode: Only ALLOWED_CHAT_IDS can interact.
            return

        chat_id = str(chat.id) if chat else "unknown"
        is_admin = self._is_admin(update)

        if self.reduced_mode:
            if msg.text and msg.text.startswith("/status"):
                await msg.reply_text(f"🔴 *MODO REDUCIDO ACTIVADO*\n\n{self.reduced_mode_error}\n\nEl bot no aceptará archivos hasta que se solucione.", parse_mode="Markdown")
                return
            await msg.reply_text(f"⚠️ El bot está en modo reducido debido a un error de almacenamiento:\n`{self.reduced_mode_error}`\nUsar /status para ver detalles.", parse_mode="Markdown")
            return

        # 1. Comandos
        if msg.text and msg.text.strip().startswith("/"):
            handled = await self._handle_command(update, context)
            if handled:
                return

        # 2. Textos libres -> Agente LLM
        if msg.text:
            text = msg.text.strip()
            processing_msg = await msg.reply_text("🧠 *Agente analizando...*", parse_mode="Markdown")
            try:
                response = await self.agent.chat_message(text)
                try:
                    await processing_msg.edit_text(response, parse_mode="Markdown")
                except Exception:
                    # Fallback to plain text if Markdown parsing fails (e.g., due to unescaped underscores/special chars)
                    await processing_msg.edit_text(response)
            except Exception as e:
                try:
                    await processing_msg.edit_text(f"❌ Error del Agente: {e}", parse_mode="Markdown")
                except Exception:
                    await processing_msg.edit_text(f"❌ Error del Agente: {e}")
            return

        # 3. Procesamiento de archivos
        sender = update.effective_user
        sender_id = str(sender.id) if sender else "unknown"
        sender_name = sender.full_name if sender else None
        
        # En esta nueva versión el contexto siempre es 'default' o 'root', se simplifica el manejo de subcarpetas por chat
        ctx = self.default_context

        tg_file = None
        content_type = None
        size_bytes = None
        suggested_filename = None
        external_ids = {"message_id": str(msg.message_id)}
        kind = None

        if msg.document:
            tg_file = msg.document
            size_bytes = tg_file.file_size
            content_type = tg_file.mime_type or "application/octet-stream"
            suggested_filename = tg_file.file_name
            external_ids["file_id"] = tg_file.file_id
            kind = "document"

        elif msg.video:
            tg_file = msg.video
            size_bytes = tg_file.file_size
            content_type = tg_file.mime_type or "video/mp4"
            suggested_filename = getattr(tg_file, "file_name", None)
            external_ids["file_id"] = tg_file.file_id
            kind = "video"

        elif msg.photo:
            if self.require_original_default:
                await msg.reply_text(
                    "❗ Original ON: para conservar la calidad, envía la imagen como *Archivo/Documento* (sin compresión)."
                )
                return
            tg_file = msg.photo[-1]
            size_bytes = tg_file.file_size
            content_type = "image/jpeg"
            external_ids["file_id"] = tg_file.file_id
            kind = "photo"

        else:
            return

        external_ids["kind"] = kind or "unknown"

        if self.max_bytes and self.max_bytes > 0 and size_bytes and size_bytes > self.max_bytes:
            await msg.reply_text(f"❌ Archivo demasiado grande ({size_bytes} bytes).")
            return

        file_obj = await context.bot.get_file(tg_file.file_id)
        file_url = file_obj.file_path

        def stream() -> Iterator[bytes]:
            with requests.get(file_url, stream=True, timeout=60) as r:
                r.raise_for_status()
                total = 0
                for chunk in r.iter_content(chunk_size=256 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if self.max_bytes and self.max_bytes > 0 and total > self.max_bytes:
                        raise ValueError("Archivo excede MAX_BYTES durante descarga")
                    yield chunk

        media = IncomingMedia(
            source="telegram",
            sender_id=sender_id,
            sender_name=sender_name,
            received_at=datetime.now(timezone.utc),
            content_type=content_type,
            size_bytes=size_bytes,
            suggested_filename=suggested_filename,
            stream=stream(),
            external_ids=external_ids,
        )

        try:
            path_to_report, is_dup, _, _ = process_one(
                self.upload_dir,
                self.meta_log,
                media,
                context=ctx,
                max_bytes=self.max_bytes,
                hash_index=self.hash_index,
                formats_dict=self.state_store.get_global_setting("file_formats", None),
                allowed_prefixes=self.state_store.get_global_setting("allowed_prefixes", None),
            )

            rel = path_to_report.relative_to(self.upload_dir)

            if is_dup:
                await msg.reply_text(
                    "♻️ Duplicado detectado (no se ha guardado de nuevo)\n"
                    f"📁 Carpeta: {ctx}\n"
                    f"🗂️ Ya existe en: {rel.as_posix()}"
                )
            else:
                await msg.reply_text(
                    "✅ Guardado\n"
                    f"📁 Carpeta: {ctx}\n"
                    f"🗂️ Ruta: {rel.as_posix()}"
                )

        except Exception as e:
            await msg.reply_text(f"❌ Error guardando: {e}")
            print(f"[error] {e}")

    def run(self) -> None:
        async def send_startup_alerts(application: Application):
            print("[startup] Ejecutando alertas de inicio...")
            startup_msg = "🤖 *Vault OS Agent está en línea*\nListo para recibir comandos o administrar el sistema."
            
            for admin_id in self.allowed_chat_ids:
                try: 
                    await application.bot.send_message(chat_id=admin_id, text=startup_msg, parse_mode="Markdown")
                except Exception as e:
                    print(f"[startup] Error enviando saludo a {admin_id}: {e}")

            reset_file = self.base_dir / "state" / ".reset_pending"
            if reset_file.exists():
                try:
                    target_chat = reset_file.read_text().strip()
                    await self._notify_reset_complete(target_chat, application=application)
                except Exception as e:
                    print(f"[error] Startup reset check: {e}")

            if self.reduced_mode:
                alert = f"🚨 *ALERTA DE ALMACENAMIENTO*\n\nError: `{self.reduced_mode_error}`"
                for admin_id in self.allowed_chat_ids:
                    try: await application.bot.send_message(chat_id=admin_id, text=alert, parse_mode="Markdown")
                    except: pass

        app = Application.builder().token(self.token).post_init(send_startup_alerts).build()
        app.add_handler(MessageHandler(filters.ALL, self._handle_message))
        
        print(f"[telegram] Bot arrancado (polling). ReducedMode={self.reduced_mode}")
        app.run_polling(close_loop=False, stop_signals=None)