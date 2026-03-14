from __future__ import annotations
from datetime import datetime, timezone
from typing import Iterator, Optional, Set
import re

import requests
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters

from core.models import IncomingMedia
from core.pipeline import process_one
from core.state import ChatStateStore
from core.storage import sanitize_context
from core.dedup import HashIndex

BUCKET_NAMED_RE = re.compile(r"^\d{4}_\d{2}_(.+)$")  # YYYY_MM_<context>

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
    ):
        self.token = token
        self.base_dir = base_dir
        self.meta_log = meta_log
        self.state_store = state_store
        self.hash_index = hash_index
        self.default_context = sanitize_context(default_context)
        self.require_original_default = require_original_default
        self.allowed_chat_ids = allowed_chat_ids
        self.max_bytes = max_bytes

    def _is_allowed(self, update: Update) -> bool:
        if not self.allowed_chat_ids:
            return True
        chat = update.effective_chat
        return bool(chat and chat.id in self.allowed_chat_ids)

    def _list_named_contexts(self) -> list[str]:
        contexts = set()
        try:
            for p in self.base_dir.iterdir():
                if not p.is_dir():
                    continue
                name = p.name
                if name in ("_tmp", "state", "dedup"):
                    continue
                m = BUCKET_NAMED_RE.match(name)
                if not m:
                    continue
                ctx = sanitize_context(m.group(1))
                if ctx and ctx != "default":
                    contexts.add(ctx)
        except Exception:
            pass
        return sorted(contexts)

    def _fmt_original_status(self, require_original: bool) -> str:
        return "ON (solo Documento/Archivo, sin compresión)" if require_original else "OFF (permite Foto, puede comprimirse)"

    async def _handle_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        msg = update.effective_message
        chat = update.effective_chat
        if not msg or not chat or not msg.text:
            return False

        text = msg.text.strip()
        if not text.startswith("/"):
            return False

        chat_id = str(chat.id)

        if text.startswith("/setfolder"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                await msg.reply_text("Uso: /setfolder nombre_carpeta\nEj: /setfolder viaje_roma")
                return True
            ctx = sanitize_context(parts[1])
            self.state_store.set_context(chat_id, ctx)
            await msg.reply_text(f"📁 Carpeta activa: {ctx}")
            return True

        if text.startswith("/folder"):
            ctx = self.state_store.get_context(chat_id, self.default_context)
            await msg.reply_text(f"📁 Carpeta activa: {ctx}")
            return True

        if text.startswith("/clearfolder"):
            self.state_store.clear_context(chat_id)
            await msg.reply_text(f"📁 Carpeta activa: {self.default_context}")
            return True

        if text.startswith("/folders"):
            contexts = self._list_named_contexts()
            if not contexts:
                await msg.reply_text("📂 No hay carpetas con nombre todavía.")
                return True
            lines = "\n".join(f"- {c}" for c in contexts)
            await msg.reply_text(f"📂 Carpetas con nombre ({len(contexts)}):\n{lines}")
            return True

        # ---- NUEVO: /original ----
        if text.startswith("/original"):
            parts = text.split(maxsplit=1)
            if len(parts) == 1:
                current = self.state_store.get_require_original(chat_id, self.require_original_default)
                await msg.reply_text(f"📷 Original: {self._fmt_original_status(current)}")
                return True

            arg = parts[1].strip().lower()
            if arg in ("on", "true", "1", "yes", "si", "sí"):
                self.state_store.set_require_original(chat_id, True)
                await msg.reply_text("📷 Original: ON ✅\nA partir de ahora, envía imágenes como *Archivo/Documento*.")
                return True
            if arg in ("off", "false", "0", "no"):
                self.state_store.set_require_original(chat_id, False)
                await msg.reply_text("📷 Original: OFF ✅\nSe permiten fotos normales (pueden venir comprimidas).")
                return True

            await msg.reply_text("Uso: /original on | /original off | /original")
            return True

        if text.startswith("/download"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                await msg.reply_text("Uso: /download <nombre_archivo>\nEj: /download a1b2c3d4e5f6.jpg")
                return True
            
            filename = parts[1].strip()
            
            await msg.reply_text(f"🔍 Buscando '{filename}'...")
            
            # Buscar recursivamente en base_dir
            found_path = None
            try:
                for p in self.base_dir.rglob(filename):
                    if p.is_file():
                        found_path = p
                        break
            except Exception as e:
                print(f"[error] Error buscando archivo: {e}")
            
            if not found_path:
                await msg.reply_text("❌ Archivo no encontrado.")
                return True
            
            try:
                # Enviar de vuelta como Documento para evitar compresión y mantener el nombre
                await msg.reply_document(document=found_path, filename=found_path.name)
            except Exception as e:
                await msg.reply_text(f"❌ Error al enviar el archivo: {e}")
                print(f"[error] {e}")
            
            return True

        if text.startswith("/help"):
            current_ctx = self.state_store.get_context(chat_id, self.default_context)
            current_original = self.state_store.get_require_original(chat_id, self.require_original_default)

            await msg.reply_text(
                "Estado actual:\n"
                f"📁 Carpeta: {current_ctx}\n"
                f"📷 Original: {self._fmt_original_status(current_original)}\n"
                "\n"
                "Comandos:\n"
                "/setfolder <nombre>  → cambia carpeta\n"
                "/folder              → muestra carpeta actual\n"
                "/clearfolder         → vuelve a default\n"
                "/folders             → lista carpetas con nombre\n"
                "/original on|off     → exige original (Documento) o permite Foto\n"
                "/original            → ver estado\n"
                "/download <archivo>  → descargar un archivo\n"
            )
            return True

        return False

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = update.effective_message
        if not msg:
            return

        chat = update.effective_chat
        if chat:
            print(f"[telegram] chat_id={chat.id} type={chat.type}")

        if not self._is_allowed(update):
            await msg.reply_text("⛔ No autorizado.")
            return

        handled = await self._handle_command(update, context)
        if handled:
            return

        sender = update.effective_user
        sender_id = str(sender.id) if sender else "unknown"
        sender_name = sender.full_name if sender else None

        chat_id = str(chat.id) if chat else "unknown"
        ctx = self.state_store.get_context(chat_id, self.default_context)
        require_original = self.state_store.get_require_original(chat_id, self.require_original_default)

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
            if require_original:
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
                self.base_dir,
                self.meta_log,
                media,
                context=ctx,
                max_bytes=self.max_bytes,
                hash_index=self.hash_index,
            )

            rel = path_to_report.relative_to(self.base_dir)

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
        app = Application.builder().token(self.token).build()
        app.add_handler(MessageHandler(filters.ALL, self._handle_message))
        print("[telegram] Bot arrancado (polling). Usa /help para comandos.")
        app.run_polling(close_loop=False)