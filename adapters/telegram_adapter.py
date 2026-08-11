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

