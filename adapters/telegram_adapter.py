from __future__ import annotations
from datetime import datetime, timezone
from typing import Iterator, Optional, Set
import re
import random

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
        system_dirs = {"_tmp", "state", "dedup", "_vault"}
        try:
            for p in self.base_dir.iterdir():
                if not p.is_dir():
                    continue
                name = p.name
                # Ocultar carpetas ocultas (.) y carpetas de sistema/vault
                if name.startswith(".") or name in system_dirs or "vault" in name.lower():
                    continue
                # Ocultar carpetas que son solo números (buckets por fecha)
                if re.match(r"^\d{4}$", name):
                    continue
                
                # Ocultar carpetas vacías
                try:
                    contains_files = any(f.is_file() for f in p.iterdir())
                    if not contains_files:
                        continue
                except Exception:
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
            await msg.reply_text("⛔ Solo administradores pueden crear invitaciones.")
            return True
        if not args:
            await msg.reply_text("Uso: /invite <carpeta> [etiqueta]\nEj: /invite boda_pepito Pepito")
            return True
            
        parts = args.split(maxsplit=1)
        folder = sanitize_context(parts[0])
        tag = parts[1] if len(parts) > 1 else f"invitado_{datetime.now(timezone.utc).strftime('%H%M%S')}"
        
        code = self.state_store.create_invite(folder, tag)
        await msg.reply_text(
            f"🎟️ Invitación creada para la carpeta '{folder}'.\n"
            f"🏷️ Etiqueta: {tag}\n"
            f"⏳ Válida por: 24 horas\n"
            f"El invitado debe usar:\n\n/join {code}"
        )
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
            await msg.reply_text("⛔ Solo administradores pueden resetear la carpeta a default.")
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
            await msg.reply_text("⛔ Solo administradores pueden cambiar la calidad de subida.")
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

    async def _cmd_downloadfolder(self, msg, chat_id: str, args: str, is_admin: bool, allowed_folders: set) -> bool:
        current_ctx = self.state_store.get_context(chat_id, self.default_context)
        folder_name = sanitize_context(args.split()[0]) if args else current_ctx
        
        if not is_admin and folder_name not in allowed_folders:
            await msg.reply_text(f"⛔ No tienes permiso para acceder a la carpeta '{folder_name}'.")
            return True
        
        if folder_name == "default":
            await msg.reply_text("⚠️ Estás en la carpeta 'default'. Especifica una carpeta: /downloadfolder <carpeta>")
            return True
        
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

    async def _cmd_download(self, msg, args: str, is_admin: bool, allowed_folders: set) -> bool:
        if not args:
            await msg.reply_text("Uso: /download <nombre_archivo>")
            return True
        
        filename = args
        await msg.reply_text(f"🔍 Buscando '{filename}'...")
        
        found_path = None
        try:
            for p in self.base_dir.rglob(filename):
                if p.is_file():
                    # Para no administradores, verificar que el archivo esté en una carpeta permitida
                    if not is_admin:
                        # Verificamos si alguna parte de la ruta relativa coincide con allowed_folders
                        rel = p.relative_to(self.base_dir)
                        # El primer componente suele ser el nombre de la carpeta (contexto)
                        if rel.parts[0] in allowed_folders:
                            found_path = p
                            break
                    else:
                        found_path = p
                        break
        except Exception as e:
            print(f"[error] Error buscando archivo: {e}")
        
        if not found_path:
            await msg.reply_text("❌ Archivo no encontrado o no tienes acceso.")
            return True
        
        try:
            await msg.reply_document(document=found_path, filename=found_path.name)
        except Exception as e:
            await msg.reply_text(f"❌ Error al enviar el archivo: {e}")
            print(f"[error] {e}")
        
        return True

    async def _cmd_delete(self, msg, chat_id: str, args: str, is_admin: bool, allowed_folders: set) -> bool:
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
            
        # Seguridad: Solo admin o si está dentro de allowed_folders
        if not is_admin:
            try:
                rel = found_path.relative_to(self.base_dir)
                if rel.parts[0] not in allowed_folders:
                    await msg.reply_text("⛔ No tienes permiso para eliminar archivos fuera de tus carpetas.")
                    return True
            except Exception:
                await msg.reply_text("⛔ Error de permisos.")
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
            await msg.reply_text("⛔ El Baúl es solo para administradores.")
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
            await msg.reply_text("⛔ El Baúl es solo para administradores.")
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
            await msg.reply_text("⛔ El Baúl es solo para administradores.")
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

    async def _cmd_preview(self, msg, chat, chat_id: str, args: str, is_admin: bool, allowed_folders: set, context: ContextTypes.DEFAULT_TYPE) -> bool:
        current_ctx = self.state_store.get_context(chat_id, self.default_context)
        folder_name = sanitize_context(args.split()[0]) if args else current_ctx
        
        if folder_name == "default":
            await msg.reply_text("⚠️ Estás en la carpeta 'default'. Especifica una carpeta: /preview <carpeta>")
            return True
            
        if not is_admin and folder_name not in allowed_folders:
            await msg.reply_text(f"⛔ No tienes permiso para acceder a la carpeta '{folder_name}'.")
            return True
            
        target_dir = self.base_dir / folder_name
        
        if not target_dir.exists() or not target_dir.is_dir():
            await msg.reply_text(f"❌ La carpeta '{folder_name}' no existe.")
            return True
            
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
            
        # Seleccionar 10 imágenes al azar (o todas si hay menos de 10)
        limit = 10
        subset = random.sample(images, min(len(images), limit))
        
        # Sort them by name just for consistency in display even if random
        subset.sort(key=lambda x: x.name)
        
        media_group = []
        # Need to keep file handles open until send_media_group finishes
        files = []
        try:
            for img in subset:
                f = open(img, "rb")
                files.append(f)
                media_group.append(InputMediaPhoto(media=f))
                
            await msg.reply_text(f"🎲 Mostrando {len(subset)} imágenes aleatorias de {len(images)} totales.\nCarpeta: '{folder_name}'")
            await context.bot.send_media_group(chat_id=chat.id, media=media_group)
            
        except Exception as e:
            await msg.reply_text(f"❌ Error al enviar la preview: {e}")
            print(f"[error] {e}")
        finally:
            for f in files:
                f.close()

        return True

    async def _cmd_vaultlist(self, msg, is_admin: bool) -> bool:
        if not is_admin:
            await msg.reply_text("⛔ El Baúl es solo para administradores.")
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

    async def _cmd_access(self, msg, is_admin: bool) -> bool:
        if not is_admin:
            await msg.reply_text("⛔ Solo administradores pueden ver la lista de accesos.")
            return True
            
        report = self.state_store.get_access_report()
        
        text = "🎟️ *Control de Acceso*\n\n"
        
        # Pendientes
        text += "⏳ *Invitaciones Pendientes (24h)*:\n"
        if not report["pending"]:
            text += "_No hay códigos activos_\n"
        else:
            for p in report["pending"]:
                created = datetime.fromisoformat(p["created_at"])
                # Calcular tiempo restante aprox
                rem = 24 - (datetime.now(timezone.utc) - created).total_seconds() / 3600
                text += f"- `{p['code']}` → {p['folder']} | {p['tag']} ({rem:.1f}h rest.)\n"
        
        text += "\n👥 *Usuarios con Acceso*:\n"
        if not report["active"]:
            text += "_No hay usuarios externos registrados_\n"
        else:
            for a in report["active"]:
                text += f"- User: `{a['chat_id']}` | Carpeta: `{a['folder']}` | Tag: `{a['tag']}`\n"
                
        text += "\n_Usa /revoke <ID|tag> para quitar un acceso._"
        await msg.reply_text(text, parse_mode="Markdown")
        return True

    async def _cmd_revoke(self, msg, args: str, is_admin: bool) -> bool:
        if not is_admin:
            await msg.reply_text("⛔ Solo administradores pueden revocar accesos.")
            return True
            
        if not args:
            await msg.reply_text("Uso: /revoke <ID_usuario | Tag_etiqueta>")
            return True
            
        target = args.strip()
        success = self.state_store.revoke_access(target)
        
        if success:
            await msg.reply_text(f"✅ Acceso revocado para: '{target}'")
        else:
            await msg.reply_text(f"❌ No se encontró ningún acceso con: '{target}'")
        return True

    async def _cmd_list(self, msg, chat_id: str, args: str, is_admin: bool, allowed_folders: set) -> bool:
        current_ctx = self.state_store.get_context(chat_id, self.default_context)
        folder_name = sanitize_context(args.split()[0]) if args else current_ctx
        
        if folder_name == "default":
            await msg.reply_text("⚠️ Estás en la carpeta 'default'. Especifica una carpeta: /list <carpeta>")
            return True
            
        if not is_admin and folder_name not in allowed_folders:
            await msg.reply_text(f"⛔ No tienes permiso para acceder a la carpeta '{folder_name}'.")
            return True
            
        target_dir = self.base_dir / folder_name
        
        if not target_dir.exists() or not target_dir.is_dir():
            await msg.reply_text(f"❌ La carpeta '{folder_name}' no existe.")
            return True
            
        files = []
        try:
            for p in target_dir.iterdir():
                if p.is_file():
                    size_kb = p.stat().st_size / 1024
                    files.append(f"📄 `{p.name}` ({size_kb:.1f} KB)")
        except Exception as e:
            print(f"[error] Leyendo carpeta para list: {e}")
            
        if not files:
            await msg.reply_text(f"📂 La carpeta '{folder_name}' está vacía.")
            return True
            
        files.sort()
        lines = "\n".join(files)
        await msg.reply_text(f"📂 Archivos en '{folder_name}':\n{lines}")
        return True

    async def _cmd_help(self, msg, chat_id: str, is_admin: bool) -> bool:
        current_ctx = self.state_store.get_context(chat_id, self.default_context)
        current_original = self.state_store.get_require_original(chat_id, self.require_original_default)

        # Base del mensaje
        help_text = (
            f"📍 *Estado Actual*\n"
            f"📁 Carpeta: `{current_ctx}`\n"
        )
        
        if is_admin:
            help_text += f"📷 Original: {self._fmt_original_status(current_original)}\n\n"
        else:
            help_text += "\n"

        # Categorías
        help_text += (
            "📂 *Gestión de Carpetas*\n"
            "/setfolder <nombre> → Cambia de carpeta activa\n"
            "/folder              → Muestra la carpeta actual\n"
        )
        
        if is_admin:
            help_text += "/clearfolder         → Vuelve a la carpeta default\n"
            help_text += "/folders             → Lista todas las carpetas\n\n"
        else:
            help_text += "/folders             → Lista tus carpetas permitidas\n\n"

        # Acceso
        if is_admin:
            help_text += (
                "🎟️ *Acceso*\n"
                "/invite <c> [tag]   → Crea invitación (24h)\n"
                "/access             → Lista de códigos y usuarios\n"
                "/revoke <ID|tag>    → Quita el acceso a un usuario\n"
                "/join <código>      → Unirse a una carpeta\n\n"
            )
        else:
            help_text += (
                "🎟️ *Acceso*\n"
                "/join <código>      → Unirse a una carpeta con invitación\n\n"
            )

        # Archivos
        help_text += (
            "📦 *Archivos y Vistas*\n"
            "/list <carpeta?>      → Lista archivos de una carpeta\n"
            "/preview <carpeta?>   → Miniaturas aleatorias (10)\n"
            "/download <archivo>   → Descarga un archivo concreto\n"
            "/downloadfolder <c?>  → Descarga carpeta en ZIP\n"
            "/delete <ruta>        → Elimina archivo o carpeta\n\n"
        )

        # Baúl (Solo Admin)
        if is_admin:
            help_text += (
                "🔐 *Baúl Seguro (Vault)*\n"
                "/vaultadd <tag>      → Guarda archivo en baúl\n"
                "/vaultget <tag>      → Recupera archivo de baúl\n"
                "/vaultdelete <tag>   → Elimina archivo de baúl\n"
                "/vaultlist           → Lista archivos del baúl\n\n"
            )

        # Configuración
        help_text += "🔧 *Configuración*\n"
        if is_admin:
            help_text += "/original on|off     → Calidad de imagen (ON/OFF)\n"
        
        help_text += "/help                → Muestra este menú\n\n"
        help_text += "_Nota: Si no especificas <carpeta> en los comandos marcados con '?', se usará tu carpeta activa._"
        
        await msg.reply_text(help_text, parse_mode="Markdown")
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
        allowed_folders = set(self.state_store.get_allowed_folders(chat_id))

        if command == "/invite":
            return await self._cmd_invite(msg, args, is_admin)
        elif command == "/access":
            return await self._cmd_access(msg, is_admin)
        elif command == "/revoke":
            return await self._cmd_revoke(msg, args, is_admin)
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
            return await self._cmd_downloadfolder(msg, chat_id, args, is_admin, allowed_folders)
        elif command == "/download":
            return await self._cmd_download(msg, args, is_admin, allowed_folders)
        elif command == "/list":
            return await self._cmd_list(msg, chat_id, args, is_admin, allowed_folders)
        elif command == "/delete":
            return await self._cmd_delete(msg, chat_id, args, is_admin, allowed_folders)
        elif command == "/vaultadd":
            return await self._cmd_vaultadd(msg, chat_id, args, is_admin)
        elif command == "/vaultget":
            return await self._cmd_vaultget(msg, args, is_admin)
        elif command == "/vaultdelete":
            return await self._cmd_vaultdelete(msg, chat_id, args, is_admin)
        elif command == "/preview":
            return await self._cmd_preview(msg, chat, chat_id, args, is_admin, allowed_folders, context)
        elif command == "/vaultlist":
            return await self._cmd_vaultlist(msg, is_admin)
        elif command == "/help":
            return await self._cmd_help(msg, chat_id, is_admin)

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
        allowed_folders = set(self.state_store.get_allowed_folders(chat_id))

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
        allowed_folders = set(self.state_store.get_allowed_folders(chat_id))
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