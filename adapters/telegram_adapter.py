<<<<<<< HEAD
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
        elif command == "/update_check":
            return await self._cmd_update_check(msg, is_admin)
        elif command == "/rollback":
            return await self._cmd_rollback(msg, is_admin)
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
            subprocess.run(["sudo", "reboot"], check=True)
        except Exception as e:
            await msg.reply_text(f"❌ Error al reiniciar: {str(e)}")
        return True

    async def _cmd_get_access(self, msg, is_admin: bool) -> bool:
        if not is_admin:
            await msg.reply_text("⛔ Solo administradores.")
            return True
        
        # Generar QR para vinculación
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(f"VAULT_AUTH_TOKEN:{self.token}")
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        
        await msg.reply_text("🔑 **Acceso de Seguridad**\nReiniciando servicios y generando token de vinculación:")
        await msg.reply_photo(photo=buf)
        return True

    async def _cmd_status(self, msg, chat_id: str, is_admin: bool) -> bool:
        if not is_admin:
            await msg.reply_text("⛔ Solo administradores.")
            return True
            
        # Obtener métricas
        cpu = "25%"
        ram = "40%"
        disk = "60%"
        
        status_text = (
            "📊 *Estado del Sistema*\n\n"
            f"CPU: {cpu}\n"
            f"RAM: {ram}\n"
            f"Disco: {disk}\n\n"
            "✅ Sistema operativo."
        )
        await msg.reply_text(status_text, parse_mode="Markdown")
        return True

    async def _cmd_help(self, msg, is_admin: bool) -> bool:
        if not is_admin:
            return True

        help_text = (
            "🤖 *Vault OS Agent - Comandos Administrativos*\n\n"
            "/system\\_reboot  → Reinicia la Raspberry Pi\n"
            "/get\\_access     → Reinicia la API y muestra QR de vinculación\n"
            "/status         → Ver métricas (CPU, RAM, Disco) y servicios\n"
            "/update\\_check   → Comprobar estado de actualización en GitHub\n"
            "/rollback       → Restaurar versión anterior desde copia de seguridad\n"
            "/help           → Muestra este menú\n\n"
            "💬 *Asistente IA*: Cualquier otro mensaje de texto será procesado "
            "automáticamente por el Agente de IA para administración y desarrollo."
        )
        try:
            await msg.reply_text(help_text, parse_mode="Markdown")
        except Exception as e:
            print(f"[telegram] Error in help command: {e}")
        return True

    async def _cmd_update_check(self, msg, is_admin: bool) -> bool:
        if not is_admin:
            await msg.reply_text("⛔ Solo administradores.")
            return True
        await msg.reply_text("🔍 Comprobando actualizaciones...")
        return True

    async def _cmd_rollback(self, msg, is_admin: bool) -> bool:
        if not is_admin:
            await msg.reply_text("⛔ Solo administradores.")
            return True
        await msg.reply_text("⏪ Iniciando proceso de rollback...")
        return True

    def run(self):
        async def post_init(application: Application):
            print("[telegram] Enviando mensaje de inicio...", flush=True)
            for chat_id in self.allowed_chat_ids:
                try:
                    await application.bot.send_message(
                        chat_id=chat_id,
                        text="🚀 Vault Ingestor Bot iniciado y listo para recibir comandos."
                    )
                except Exception as e:
                    print(f"[telegram] Error enviando a {chat_id}: {e}")

        application = Application.builder().token(self.token).post_init(post_init).build()

        async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.effective_message or not update.effective_message.text:
                return
            
            print(f"[telegram] Mensaje recibido de {update.effective_chat.id}: {update.effective_message.text}", flush=True)
            
            is_cmd = await self._handle_command(update, context)
            if not is_cmd:
                if self._is_allowed(update):
                    text = update.effective_message.text
                    await update.effective_message.reply_text("⏳ Procesando...")
                    try:
                        response = await self.agent.chat_message(text)
                        await update.effective_message.reply_text(response)
                    except Exception as e:
                        print(f"[telegram] Error en IA: {e}")
                        await update.effective_message.reply_text(f"❌ Error interno: {e}")


        application.add_handler(MessageHandler(filters.TEXT, message_handler))
        
        print("[telegram] Iniciando polling...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

=======
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
        elif command == "/update_check":
            return await self._cmd_update_check(msg, is_admin, args)
        elif command == "/rollback":
            return await self._cmd_rollback(msg, is_admin)
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
            "\\/system\\_reboot  → Reinicia la Raspberry Pi\n"
            "\\/get\\_access     → Reinicia la API y muestra QR de vinculación\n"
            "\\/status         → Ver métricas (CPU, RAM, Disco) y servicios\n"
            "\\/update\\_check   → Comprobar estado de actualización en GitHub\n"
            "\\/rollback       → Restaurar versión anterior desde copia de seguridad\n"
            "\\/help           → Muestra este menú\n\n"
            "💬 *Asistente IA*: Cualquier otro mensaje de texto será procesado "
            "automáticamente por el Agente de IA para administración y desarrollo."
        )
        await msg.reply_text(help_text, parse_mode="Markdown")
        return True

    async def _cmd_update_check(self, msg, is_admin: bool, target_tag: str = "") -> bool:
        if not is_admin:
            await msg.reply_text("⛔ Solo administradores.")
            return True

        if not self.update_manager:
            await msg.reply_text("⚠️ El gestor de actualizaciones no está configurado.")
            return True

        target_tag = target_tag.strip()
        search_msg = f"🔍 *Comprobando Release `{target_tag}` en GitHub...*" if target_tag else "🔍 *Comprobando última Release en GitHub...*"
        status_msg = await msg.reply_text(search_msg, parse_mode="Markdown")
        try:
            has_updates, remote_tag = self.update_manager.check_git_updates(target_tag=target_tag if target_tag else None)
            
            state = self.update_manager._get_state() if hasattr(self.update_manager, '_get_state') else {}
            local_tag = state.get("current_version", "unknown")
            last_stable = state.get('last_stable', 'Ninguna')
            
            msg_text = "📦 *Estado de Actualizaciones*\n\n"
            msg_text += f"▪️ Versión instalada: `{local_tag}`\n"
            msg_text += f"▪️ Último backup estable: `{last_stable}`\n\n"
            
            if has_updates:
                msg_text += f"🚀 *¡Nueva Release disponible!*\nTag: `{remote_tag}`\n"
                msg_text += "_La actualización se aplicará automáticamente en el próximo reinicio._"
            elif target_tag and remote_tag == "not_found":
                msg_text += f"❌ *El tag `{target_tag}` no existe* o no está publicado como Release."
            else:
                msg_text += "✅ *El sistema está en la última versión.*"
                
            await status_msg.edit_text(msg_text, parse_mode="Markdown")
        except Exception as e:
            await status_msg.edit_text(f"❌ *Error al comprobar actualizaciones:* {e}", parse_mode="Markdown")
        return True

    async def _cmd_rollback(self, msg, is_admin: bool) -> bool:
        if not is_admin:
            await msg.reply_text("⛔ Solo administradores.")
            return True

        if not self.update_manager:
            await msg.reply_text("⚠️ El gestor de actualizaciones no está configurado.")
            return True

        status_msg = await msg.reply_text("🔄 *Iniciando proceso de Rollback offline...*", parse_mode="Markdown")
        try:
            # Call rollback on update manager
            if hasattr(self.update_manager, 'rollback_to_last_stable'):
                success, reason = self.update_manager.rollback_to_last_stable("Solicitado vía Telegram")
            else:
                # Fallback to current rollback method if new one is not ready yet
                success, reason = self.update_manager.rollback()

            if success:
                await status_msg.edit_text(
                    "✅ *Sistema restaurado con éxito a la copia de seguridad local (sin conexión a GitHub).*\n\n"
                    "Reiniciando servicios...",
                    parse_mode="Markdown"
                )
                # Restart services after a short delay
                async def restart_services():
                    await asyncio.sleep(2)
                    subprocess.run(["sudo", "systemctl", "restart", "vault_api", "vault_bot"], check=False)
                asyncio.create_task(restart_services())
            else:
                await status_msg.edit_text(f"❌ *Error en Rollback:* {reason}", parse_mode="Markdown")

        except Exception as e:
            await status_msg.edit_text(f"❌ *Error crítico al ejecutar rollback:* {e}", parse_mode="Markdown")
        return True

    async def _cmd_get_access(self, msg, is_admin: bool) -> bool:
        if not is_admin:
            await msg.reply_text("⛔ Solo administradores.")
            return True

        chat_id = str(msg.chat_id)
        status_msg = await msg.reply_text(
            "🔄 *Ejecutando run_vault.sh y reiniciando API...*\n"
            "Esto puede tardar hasta 45 segundos mientras se verifica la conexión y el túnel Cloudflare. Por favor, espera...",
            parse_mode="Markdown"
        )

        try:
            # Resolving project directory
            project_dir = Path(__file__).resolve().parent.parent
            script_path = project_dir / "run_vault.sh"

            # Ejecutar run_vault.sh de forma asíncrona y esperar al resultado
            proc = await asyncio.create_subprocess_exec(
                "bash", str(script_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(project_dir)
            )

            stdout_bytes, stderr_bytes = await proc.communicate()
            stdout = stdout_bytes.decode("utf-8", errors="ignore")
            stderr = stderr_bytes.decode("utf-8", errors="ignore")

            print(f"[get_access] run_vault.sh finalizado con código {proc.returncode}")

            import re
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            clean_stdout = ansi_escape.sub('', stdout)

            url = None
            pin = None
            
            for line in clean_stdout.splitlines():
                if "URL:" in line:
                    url = line.split("URL:", 1)[1].strip()
                if "PIN:" in line:
                    pin = line.split("PIN:", 1)[1].strip()

            if "ADMIN DEVICE ALREADY LINKED" in clean_stdout:
                await status_msg.edit_text(
                    "⚠️ *Dispositivo Administrador ya Vinculado*\n\n"
                    "El sistema ha arrancado correctamente, pero el dispositivo administrador ya está vinculado.\n"
                    "Si has perdido el acceso o necesitas desvincularlo, elimina el archivo `devices.json` en tu almacenamiento y vuelve a ejecutar `/get_access`.",
                    parse_mode="Markdown"
                )
            elif url and pin:
                # Generar QR
                qr = qrcode.QRCode(version=1, box_size=10, border=1)
                qr.add_data(json.dumps({"url": url, "pin": pin}))
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG')
                img_byte_arr.seek(0)
                
                await status_msg.delete()
                await msg.reply_photo(
                    photo=img_byte_arr,
                    caption=(
                        "✅ *Sistema Listo*\n\n"
                        f"🔗 *URL:* `{url}`\n"
                        f"🔢 *PIN:* `{pin}`\n\n"
                        "Ya puedes vincular tu dispositivo móvil."
                    ),
                    parse_mode="Markdown"
                )
            else:
                err_msg = "❌ *Error al configurar el acceso*\n\n"
                if "Timeout" in clean_stdout:
                    err_msg += "⏳ Tiempo de espera agotado. La API o el túnel Cloudflare tardaron demasiado en responder."
                else:
                    err_msg += "Ocurrió un error inesperado durante la ejecución del script. Detalles:\n"
                    err_msg += f"```\n{clean_stdout[-300:]}\n{stderr[-300:]}\n```"
                
                await status_msg.edit_text(err_msg, parse_mode="Markdown")

        except Exception as e:
            await status_msg.edit_text(f"❌ *Error al lanzar el comando:* {e}", parse_mode="Markdown")

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
                err_str = str(e).lower()
                if "429" in err_str or "exhausted" in err_str or "quota" in err_str:
                    model_name = self.agent.model_name
                    model_lower = model_name.lower()
                    limit_info = "50 solicitudes al día" if "pro" in model_lower else "1,500 solicitudes al día"
                    if "3.1-flash-lite" in model_lower:
                        limit_info = "500 solicitudes al día y 15 por minuto"
                    
                    user_msg = (
                        "⚠️ *Límite de Cuota Alcanzado*\n\n"
                        "Se ha superado el límite de consultas permitidas de la API de Gemini para este periodo.\n\n"
                        f"El límite asignado para tu modelo actual (`{model_name}`) es de **{limit_info}**.\n\n"
                        "Por favor, espera unos minutos o cambia tu clave de API si has agotado el cupo diario.\n"
                        "Para más información, consulta: https://ai.dev/rate-limit"
                    )
                else:
                    user_msg = f"❌ Error del Agente: {e}"
                
                try:
                    await processing_msg.edit_text(user_msg, parse_mode="Markdown")
                except Exception:
                    await processing_msg.edit_text(user_msg)
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

            if self.reduced_mode:
                alert = f"🚨 *ALERTA DE ALMACENAMIENTO*\n\nError: `{self.reduced_mode_error}`"
                for admin_id in self.allowed_chat_ids:
                    try: await application.bot.send_message(chat_id=admin_id, text=alert, parse_mode="Markdown")
                    except: pass

        app = Application.builder().token(self.token).post_init(send_startup_alerts).build()
        app.add_handler(MessageHandler(filters.ALL, self._handle_message))
        
        print(f"[telegram] Bot arrancado (polling). ReducedMode={self.reduced_mode}")
        app.run_polling(close_loop=False, stop_signals=None)
>>>>>>> a6ed4626738e52cad35164fd58f9f0752e3bdc4b
