from __future__ import annotations
from datetime import datetime, timezone
from typing import Iterator, Optional, Set
import re

import requests
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters

import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Iterator, Optional, Set, List

import requests
from telegram import Update, InputMediaPhoto
from telegram.ext import Application, MessageHandler, ContextTypes, filters

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

    def _is_admin(self, update: Update) -> bool:
        if self.allowed_chat_ids is None:
            return True
        user_id = update.effective_user.id
        return user_id in self.allowed_chat_ids

    async def _cmd_invite(self, msg, args: str, is_admin: bool) -> bool:
        if not is_admin:
            return True
        if not args:
            await msg.reply_text("Uso: /invite <carpeta>")
            return True
        folder = sanitize_context(args)
        code = self.state_store.create_invite(folder)
        await msg.reply_text(f"🎟️ Invitación creada para la carpeta '{folder}'.\nEl invitado debe usar:\n\n/join {code}")
        return True

    async def _cmd_join(self, msg, chat_id: str, args: str) -> bool:
        if not args:
            await msg.reply_text("Uso: /join <código>")
            return True
        code = args.split()[0]
        folder = self.state_store.claim_invite(chat_id, code)
        if not folder:
            await msg.reply_text("❌ Código de invitación inválido o ya usado.")
            return True
        self.state_store.set_context(chat_id, folder)
        await msg.reply_text(f"✅ Has sido invitado a la carpeta '{folder}'. Tu carpeta activa es ahora '{folder}'.")
        return True

    async def _cmd_setfolder(self, msg, chat_id: str, args: str, is_admin: bool, allowed_folders: set) -> bool:
        if not args:
            await msg.reply_text("Uso: /setfolder nombre_carpeta\nEj: /setfolder viaje_roma")
            return True
        ctx = sanitize_context(args)
        
        if not is_admin and ctx not in allowed_folders:
            return True
            
        target_dir = self.base_dir / ctx
        
        if target_dir.exists() and target_dir.is_dir() and ctx != self.state_store.get_context(chat_id, self.default_context):
            self.state_store.set_pending_action(chat_id, {"action": "confirm_setfolder", "folder": ctx})
            await msg.reply_text(f"⚠️ La carpeta '{ctx}' ya existe.\n¿Quieres moverte a la carpeta ya existente? (si/no)")
            return True

        self.state_store.set_context(chat_id, ctx)
        self.state_store.clear_pending_action(chat_id)
        await msg.reply_text(f"📁 Carpeta activa: {ctx}")
        return True

    async def _cmd_clearfolder(self, msg, chat_id: str, is_admin: bool) -> bool:
        if not is_admin:
            return True
        self.state_store.clear_context(chat_id)
        await msg.reply_text(f"📁 Carpeta activa: {self.default_context}")
        return True

    async def _cmd_folders(self, msg, is_admin: bool, allowed_folders: set) -> bool:
        if not is_admin:
            lines = "\n".join(f"- {f}" for f in sorted(allowed_folders))
            if not lines:
                lines = "(ninguna)"
            await msg.reply_text(f"📂 Carpetas permitidas ({len(allowed_folders)}):\n{lines}")
            return True
            
        contexts = self._list_named_contexts()
        if not contexts:
            await msg.reply_text("📂 No hay carpetas con nombre todavía.")
            return True
        lines = "\n".join(f"- {c}" for c in contexts)
        await msg.reply_text(f"📂 Carpetas con nombre ({len(contexts)}):\n{lines}")
        return True

    async def _cmd_folder(self, msg, chat_id: str) -> bool:
        ctx = self.state_store.get_context(chat_id, self.default_context)
        await msg.reply_text(f"📁 Carpeta activa: {ctx}")
        return True

    async def _cmd_original(self, msg, chat_id: str, args: str, is_admin: bool) -> bool:
        if not is_admin:
            return True
            
        if not args:
            current = self.state_store.get_require_original(chat_id, self.require_original_default)
            await msg.reply_text(f"📷 Original: {self._fmt_original_status(current)}")
            return True

        arg = args.lower()
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

    async def _cmd_downloadfolder(self, msg, args: str) -> bool:
        if not args:
            await msg.reply_text("Uso: /downloadfolder <nombre_carpeta>\nEj: /downloadfolder viaje_roma")
            return True
        
        folder_name = sanitize_context(args)
        target_dir = self.base_dir / folder_name
        
        if not target_dir.exists() or not target_dir.is_dir():
            await msg.reply_text(f"❌ La carpeta '{folder_name}' no existe.")
            return True
        
        await msg.reply_text(f"📦 Comprimiendo carpeta '{folder_name}'...")
        
        try:
            tmp_dir = self.base_dir / "_tmp"
            tmp_dir.mkdir(exist_ok=True)
            
            base_zip_name = f"{folder_name}_{uuid.uuid4().hex}"
            base_zip_path = str(tmp_dir / base_zip_name)
            
            shutil.make_archive(base_zip_path, 'zip', target_dir)
            
            final_zip = Path(base_zip_path + ".zip")
            
            try:
                await msg.reply_document(document=final_zip, filename=f"{folder_name}.zip")
            except Exception as e:
                await msg.reply_text(f"❌ Error al enviar el ZIP: {e}")
            finally:
                final_zip.unlink(missing_ok=True)
                
        except Exception as e:
            await msg.reply_text(f"❌ Error al crear el ZIP: {e}")
            print(f"[error] {e}")
        
        return True

    async def _cmd_download(self, msg, args: str) -> bool:
        if not args:
            await msg.reply_text("Uso: /download <nombre_archivo>")
            return True
        
        filename = args
        await msg.reply_text(f"🔍 Buscando '{filename}'...")
        
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
            await msg.reply_document(document=found_path, filename=found_path.name)
        except Exception as e:
            await msg.reply_text(f"❌ Error al enviar el archivo: {e}")
            print(f"[error] {e}")
        
        return True

    async def _cmd_delete(self, msg, chat_id: str, args: str, is_admin: bool) -> bool:
        if not is_admin:
            return True
            
        if not args:
            await msg.reply_text("Uso: /delete <nombre_archivo_o_carpeta>")
            return True
        
        target_name = args
        found_path = None
        try:
            for p in self.base_dir.rglob(target_name):
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

    async def _cmd_vaultadd(self, msg, chat_id: str, args: str, is_admin: bool) -> bool:
        if not is_admin:
            return True
        if not args:
            await msg.reply_text("Uso: /vaultadd <etiqueta>\nEj: /vaultadd pasaporte")
            return True
        
        tag = sanitize_context(args)
        self.state_store.set_pending_action(chat_id, {"action": "await_vault", "tag": tag})
        await msg.reply_text(f"🔐 Modo Baúl activado.\nEnvía ahora el archivo que se guardará con la etiqueta: '{tag}'.")
        return True

    async def _cmd_vaultget(self, msg, args: str, is_admin: bool) -> bool:
        if not is_admin:
            return True
        if not args:
            await msg.reply_text("Uso: /vaultget <etiqueta>")
            return True
        
        tag = sanitize_context(args)
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

    async def _cmd_vaultdelete(self, msg, chat_id: str, args: str, is_admin: bool) -> bool:
        if not is_admin:
            return True
        if not args:
            await msg.reply_text("Uso: /vaultdelete <etiqueta>")
            return True
        
        tag = sanitize_context(args)
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
            await msg.reply_text(f"❌ No se encontró nada con la etiqueta '{tag}' en el baúl para eliminar.")
            return True
        
        self.state_store.set_pending_action(chat_id, {
            "action": "confirm_delete",
            "target": str(found)
        })
        
        await msg.reply_text(f"⚠️ ¿Estás seguro de que deseas eliminar el archivo importante '{tag}' del baúl? (si/no)")
        return True

    async def _cmd_preview(self, msg, chat, args: str, is_admin: bool, allowed_folders: set, context: ContextTypes.DEFAULT_TYPE) -> bool:
        raw_parts = args.split()
        if not raw_parts:
            await msg.reply_text("Uso: /preview <carpeta> [pagina]\nEj: /preview viaje_roma 1")
            return True
            
        folder_name = sanitize_context(raw_parts[0])
        
        if not is_admin and folder_name not in allowed_folders:
            return True
            
        target_dir = self.base_dir / folder_name
        
        if not target_dir.exists() or not target_dir.is_dir():
            await msg.reply_text(f"❌ La carpeta '{folder_name}' no existe.")
            return True
            
        page = 1
        if len(raw_parts) >= 2 and raw_parts[1].isdigit():
            page = int(raw_parts[1])
            if page < 1:
                page = 1
        
        limit = 10
        
        image_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
        images: List[Path] = []
        try:
            for p in target_dir.iterdir():
                if p.is_file() and p.suffix.lower() in image_extensions:
                    images.append(p)
        except Exception as e:
            print(f"[error] Leyendo carpeta para preview: {e}")
            
        if not images:
            await msg.reply_text(f"❌ No se encontraron imágenes en la carpeta '{folder_name}'.")
            return True
            
        images.sort(key=lambda x: x.name)
        
        total_images = len(images)
        total_pages = (total_images + limit - 1) // limit
        
        if page > total_pages:
            page = total_pages
            
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        
        subset = images[start_idx:end_idx]
        
        media_group = []
        for img in subset:
            with open(img, "rb") as f:
                media_group.append(InputMediaPhoto(media=open(img, "rb")))
                
        try:
            await msg.reply_text(f"🖼️ Mostrando {len(subset)} de {total_images} imágenes.\nCarpeta: '{folder_name}' - Página {page}/{total_pages}")
            await context.bot.send_media_group(chat_id=chat.id, media=media_group)
            
            if page < total_pages:
                await msg.reply_text(f"👉 Usa `/preview {folder_name} {page+1}` para ver la siguiente página.")
        except Exception as e:
            await msg.reply_text(f"❌ Error al enviar la preview: {e}")
            print(f"[error] {e}")

        return True

    async def _cmd_vaultlist(self, msg, is_admin: bool) -> bool:
        if not is_admin:
            return True
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

    async def _cmd_help(self, msg, chat_id: str) -> bool:
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
            "/downloadfolder <carpeta>  → descarga carpeta en ZIP\n"
            "/preview <carpeta> [pag] → previsualiza imágenes de una carpeta\n"
            "/delete <ruta>       → elimina archivo o carpeta (pedirá conformación)\n"
            "/vaultadd <tag>      → prepara para guardar un archivo en el baúl bajo el tag\n"
            "/vaultget <tag>      → recupera el archivo del baúl\n"
            "/vaultdelete <tag>   → elimina el archivo del baúl (pedirá confirmación)\n"
            "/vaultlist           → lista los archivos en tu baúl\n"
        )
        return True

    async def _handle_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        msg = update.effective_message
        chat = update.effective_chat
        if not msg or not chat or not msg.text:
            return False

        text = msg.text.strip()
        if not text.startswith("/"):
            return False

        # Extraer el comando exacto (se usa maxsplit=1 para obtener comando + posibles args)
        parts = text.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1].strip() if len(parts) > 1 else ""

        chat_id = str(chat.id)
        is_admin = self._is_admin(update)
        allowed_folders = self.state_store.get_allowed_folders(chat_id)

        if command == "/invite":
            return await self._cmd_invite(msg, args, is_admin)
        elif command == "/join":
            return await self._cmd_join(msg, chat_id, args)
        elif command == "/setfolder":
            return await self._cmd_setfolder(msg, chat_id, args, is_admin, allowed_folders)
        elif command == "/clearfolder":
            return await self._cmd_clearfolder(msg, chat_id, is_admin)
        elif command == "/folders":
            return await self._cmd_folders(msg, is_admin, allowed_folders)
        elif command == "/folder":
            return await self._cmd_folder(msg, chat_id)
        elif command == "/original":
            return await self._cmd_original(msg, chat_id, args, is_admin)
        elif command == "/downloadfolder":
            return await self._cmd_downloadfolder(msg, args)
        elif command == "/download":
            return await self._cmd_download(msg, args)
        elif command == "/delete":
            return await self._cmd_delete(msg, chat_id, args, is_admin)
        elif command == "/vaultadd":
            return await self._cmd_vaultadd(msg, chat_id, args, is_admin)
        elif command == "/vaultget":
            return await self._cmd_vaultget(msg, args, is_admin)
        elif command == "/vaultdelete":
            return await self._cmd_vaultdelete(msg, chat_id, args, is_admin)
        elif command == "/preview":
            return await self._cmd_preview(msg, chat, args, is_admin, allowed_folders, context)
        elif command == "/vaultlist":
            return await self._cmd_vaultlist(msg, is_admin)
        elif command == "/help":
            return await self._cmd_help(msg, chat_id)

        return False

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = update.effective_message
        if not msg:
            return

        chat = update.effective_chat
        if chat:
            print(f"[telegram] chat_id={chat.id} type={chat.type}")

        if not self._is_allowed(update):
            #await msg.reply_text("⛔ No autorizado.")
            return

        chat_id = str(chat.id) if chat else "unknown"
        is_admin = self._is_admin(update)
        allowed_folders = self.state_store.get_allowed_folders(chat_id)

        # Si el usuario no tiene ninguna carpeta permitida y no es admin,
        # su única forma de interactuar es usando /join. Si no, lo ignoramos.
        msg_text = msg.text or msg.caption or ""
        if not is_admin and not allowed_folders and not msg_text.strip().startswith("/join"):
            return

        handled = await self._handle_command(update, context)
        if handled:
            return

        chat_id = str(chat.id) if chat else "unknown"
        is_admin = self._is_admin(update)
        allowed_folders = self.state_store.get_allowed_folders(chat_id)
        current_ctx = self.state_store.get_context(chat_id, self.default_context)

        # Check permissions for upload
        if not is_admin and current_ctx not in allowed_folders:
            return

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