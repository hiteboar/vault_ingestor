from __future__ import annotations
from datetime import datetime, timezone
from typing import Iterator, Optional, Set
import re

import requests
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters

import shutil
import tempfile
from pathlib import Path

from core.models import IncomingMedia
from core.pipeline import process_one
from core.state import ChatStateStore
from core.storage import sanitize_context, atomic_write, ext_from_content_type
from core.dedup import HashIndex

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
                if re.match(r"^\d{4}$", name):
                    continue
                ctx = sanitize_context(name)
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
            target_dir = self.base_dir / ctx
            
            if target_dir.exists() and target_dir.is_dir() and ctx != self.state_store.get_context(chat_id, self.default_context):
                self.state_store.set_pending_action(chat_id, {"action": "confirm_setfolder", "folder": ctx})
                await msg.reply_text(f"⚠️ La carpeta '{ctx}' ya existe.\n¿Quieres moverte a la carpeta ya existente? (si/no)")
                return True

            self.state_store.set_context(chat_id, ctx)
            self.state_store.clear_pending_action(chat_id)
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

        if text.startswith("/downloadfolder"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                await msg.reply_text("Uso: /downloadfolder <nombre_carpeta>\nEj: /downloadfolder viaje_roma")
                return True
            
            folder_name = sanitize_context(parts[1])
            target_dir = self.base_dir / folder_name
            
            if not target_dir.exists() or not target_dir.is_dir():
                await msg.reply_text(f"❌ La carpeta '{folder_name}' no existe.")
                return True
            
            await msg.reply_text(f"📦 Comprimiendo carpeta '{folder_name}'...")
            
            try:
                # Comprimir la carpeta en _tmp/
                tmp_dir = self.base_dir / "_tmp"
                tmp_dir.mkdir(exist_ok=True)
                
                with tempfile.NamedTemporaryFile(dir=tmp_dir, prefix=f"{folder_name}_", suffix=".zip", delete=False) as tf:
                    zip_path = tf.name
                
                # shutil.make_archive appends .zip automatically, so we remove the .zip to pass the prefix
                base_zip_path = str(Path(zip_path).with_suffix(''))
                shutil.make_archive(base_zip_path, 'zip', target_dir)
                
                final_zip = Path(base_zip_path + ".zip")
                
                try:
                    await msg.reply_document(document=final_zip, filename=f"{folder_name}.zip")
                except Exception as e:
                    await msg.reply_text(f"❌ Error al enviar el ZIP: {e}")
                finally:
                    # Limpiar el temporales
                    final_zip.unlink(missing_ok=True)
                    Path(zip_path).unlink(missing_ok=True)
                    
            except Exception as e:
                await msg.reply_text(f"❌ Error al crear el ZIP: {e}")
                print(f"[error] {e}")
            
            return True

        # ---- NUEVO: /delete ----
        if text.startswith("/delete"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                await msg.reply_text("Uso: /delete <nombre_archivo_o_carpeta>")
                return True
            
            target_name = parts[1].strip()
            
            # Busqueda
            found_path = None
            try:
                for p in self.base_dir.rglob(target_name):
                    # Check that found file/folder matches exact name
                    if p.name == target_name:
                        found_path = p
                        break
            except Exception as e:
                print(f"[error] Error buscando objetivo: {e}")
            
            if not found_path:
                await msg.reply_text("❌ Archivo o carpeta no encontrado.")
                return True
            
            rel_path = found_path.relative_to(self.base_dir).as_posix()
            
            self.state_store.set_pending_action(chat_id, {
                "action": "confirm_delete",
                "target": str(found_path)
            })
            
            tipo = "carpeta" if found_path.is_dir() else "archivo"
            await msg.reply_text(f"⚠️ ¿Estás seguro de que deseas eliminar este {tipo}: '{rel_path}'? (si/no)")
            return True

        if text.startswith("/vaultadd"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                await msg.reply_text("Uso: /vaultadd <etiqueta>\nEj: /vaultadd pasaporte")
                return True
            
            tag = sanitize_context(parts[1])
            self.state_store.set_pending_action(chat_id, {"action": "await_vault", "tag": tag})
            await msg.reply_text(f"🔐 Modo Baúl activado.\nEnvía ahora el archivo que se guardará con la etiqueta: '{tag}'.")
            return True

        if text.startswith("/vaultget"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                await msg.reply_text("Uso: /vaultget <etiqueta>")
                return True
            
            tag = sanitize_context(parts[1])
            vault_dir = self.base_dir / "_vault"
            
            if not vault_dir.exists() or not vault_dir.is_dir():
                await msg.reply_text("❌ El baúl está vacío.")
                return True
                
            found = None
            for p in vault_dir.iterdir():
                if p.is_file() and p.stem == tag:
                    found = p
                    break
                    
            if not found:
                await msg.reply_text(f"❌ No se encontró nada con la etiqueta '{tag}' en el baúl.")
                return True
                
            assert found is not None
            await msg.reply_document(document=found, filename=found.name)
            return True

        if text.startswith("/vaultlist"):
            vault_dir = self.base_dir / "_vault"
            if not vault_dir.exists() or not vault_dir.is_dir():
                await msg.reply_text("📂 El baúl está vacío.")
                return True
                
            tags = []
            for p in vault_dir.iterdir():
                if p.is_file():
                    tags.append(p.stem)
                    
            if not tags:
                await msg.reply_text("📂 El baúl está vacío.")
                return True
                
            lines = "\n".join(f"- {t}" for t in sorted(tags))
            await msg.reply_text(f"🔐 Archivos en el baúl ({len(tags)}):\n{lines}")
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
                "/downloadfolder <carpeta>  → descarga carpeta en ZIP\n"
                "/original on|off     → exige original (Documento) o permite Foto\n"
                "/original            → ver estado\n"
                "/download <archivo>  → descargar un archivo\n"
                "/delete <ruta>       → elimina archivo o carpeta (pedirá conformación)\n"
                "/vaultadd <tag>      → prepara para guardar un archivo en el baúl bajo el tag\n"
                "/vaultget <tag>      → recupera el archivo del baúl\n"
                "/vaultlist           → lista los archivos en tu baúl\n"
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

        chat_id = str(chat.id) if chat else "unknown"

        pending = self.state_store.get_pending_action(chat_id)
        if pending and msg.text:
            ans = msg.text.strip().lower()
            if pending.get("action") == "confirm_setfolder":
                if ans in ("si", "sí", "s", "yes", "y"):
                    folder = pending.get("folder")
                    self.state_store.set_context(chat_id, folder)
                    self.state_store.clear_pending_action(chat_id)
                    await msg.reply_text(f"📁 Carpeta activa: {folder}")
                    return
                elif ans in ("no", "n"):
                    self.state_store.clear_pending_action(chat_id)
                    await msg.reply_text("❌ Acción cancelada.")
                    return
                else:
                    await msg.reply_text("Por favor responde 'si' o 'no' a la pregunta del /setfolder pendiente.")
                    return
            
            elif pending.get("action") == "confirm_delete":
                if ans in ("si", "sí", "s", "yes", "y"):
                    target_str = pending.get("target")
                    self.state_store.clear_pending_action(chat_id)
                    if target_str:
                        target = Path(target_str)
                        if target.exists():
                            try:
                                if target.is_dir():
                                    shutil.rmtree(target)
                                else:
                                    target.unlink()
                                await msg.reply_text("✅ Eliminado con éxito.")
                            except Exception as e:
                                await msg.reply_text(f"❌ Error al eliminar: {e}")
                        else:
                            await msg.reply_text("❌ El objetivo ya no existe.")
                    return
                elif ans in ("no", "n"):
                    self.state_store.clear_pending_action(chat_id)
                    await msg.reply_text("❌ Eliminación cancelada.")
                    return
                else:
                    await msg.reply_text("Por favor responde 'si' o 'no' para confirmar la eliminación.")
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

        if pending and pending.get("action") == "await_vault":
            tag = pending.get("tag")
            self.state_store.clear_pending_action(chat_id)
            
            if not tag:
                await msg.reply_text("❌ Error: Etiqueta no válida en el baúl.")
                return
                
            file_obj = await context.bot.get_file(tg_file.file_id)
            file_url = file_obj.file_path
            
            ext = ext_from_content_type(content_type)
            vault_dir = self.base_dir / "_vault"
            vault_dir.mkdir(parents=True, exist_ok=True)
            
            dest_path = vault_dir / f"{tag}{ext}"

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

            try:
                atomic_write(dest_path, stream(), fsync=True)
                await msg.reply_text(f"✅ Archivo guardado secretamente en el baúl bajo la etiqueta: '{tag}'")
            except Exception as e:
                await msg.reply_text(f"❌ Error guardando en el baúl: {e}")
                print(f"[error] {e}")
            
            # Stop further processing
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