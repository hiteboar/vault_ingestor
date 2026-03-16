
import asyncio
from unittest.mock import MagicMock, AsyncMock
from pathlib import Path
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from adapters.telegram_adapter import TelegramAdapter

async def test_permissions():
    # Mock dependencies
    state_store = MagicMock()
    hash_index = MagicMock()
    
    # Setup base dir
    base_dir = Path("test_vault")
    base_dir.mkdir(exist_ok=True)
    (base_dir / "invitado_folder").mkdir(exist_ok=True)
    (base_dir / "admin_folder").mkdir(exist_ok=True)
    (base_dir / "invitado_folder" / "test.txt").write_text("hello")
    (base_dir / "admin_folder" / "secret.txt").write_text("secret")

    adapter = TelegramAdapter(
        token="token",
        base_dir=base_dir,
        meta_log=MagicMock(),
        state_store=state_store,
        hash_index=hash_index,
        allowed_chat_ids={123} # Admin ID
    )

    # Helper to mock update
    def mock_update(user_id, text):
        update = MagicMock()
        update.effective_user.id = user_id
        update.effective_chat.id = user_id
        update.effective_message.text = text
        update.effective_message.reply_text = AsyncMock()
        return update

    print("--- Testing Guest Permissions ---")
    guest_id = 456
    state_store.get_allowed_folders.return_value = ["invitado_folder"]
    state_store.get_context.return_value = "invitado_folder"
    state_store.get_require_original.return_value = False

    # Test /invite (restricted)
    update = mock_update(guest_id, "/invite my_folder")
    await adapter._handle_command(update, MagicMock())
    update.effective_message.reply_text.assert_called_with("⛔ Solo administradores pueden crear invitaciones.")
    print("✓ Guest /invite blocked with feedback")

    # Test /vaultlist (restricted)
    update = mock_update(guest_id, "/vaultlist")
    await adapter._handle_command(update, MagicMock())
    update.effective_message.reply_text.assert_called_with("⛔ El Baúl es solo para administradores.")
    print("✓ Guest /vaultlist blocked with feedback")

    # Test /list allowed folder
    update = mock_update(guest_id, "/list invitado_folder")
    await adapter._handle_command(update, MagicMock())
    # Should not say "⛔ No tienes permiso"
    args, kwargs = update.effective_message.reply_text.call_args
    assert "Archivos en 'invitado_folder'" in args[0]
    print("✓ Guest /list allowed folder works")

    # Test /list forbidden folder
    update = mock_update(guest_id, "/list admin_folder")
    await adapter._handle_command(update, MagicMock())
    update.effective_message.reply_text.assert_called_with("⛔ No tienes permiso para acceder a la carpeta 'admin_folder'.")
    print("✓ Guest /list forbidden folder blocked")

    # Test /download allowed file
    update = mock_update(guest_id, "/download test.txt")
    update.effective_message.reply_document = AsyncMock()
    await adapter._handle_command(update, MagicMock())
    update.effective_message.reply_document.assert_called()
    print("✓ Guest /download allowed file works")

    # Test /download forbidden file
    update = mock_update(guest_id, "/download secret.txt")
    await adapter._handle_command(update, MagicMock())
    update.effective_message.reply_text.assert_called_with("❌ Archivo no encontrado o no tienes acceso.")
    print("✓ Guest /download forbidden file blocked")

    # Test /help (forked)
    update = mock_update(guest_id, "/help")
    await adapter._handle_command(update, MagicMock())
    help_text = update.effective_message.reply_text.call_args[0][0]
    assert "Baúl Seguro" not in help_text
    assert "Original:" not in help_text
    print("✓ Guest /help menu forked correctly")

    print("\n--- Testing Admin Permissions ---")
    admin_id = 123
    state_store.get_allowed_folders.return_value = [] # Admin doesn't rely on this but we check consistency
    
    # Test /invite (allowed)
    update = mock_update(admin_id, "/invite event_folder")
    state_store.create_invite.return_value = "ABC12345"
    await adapter._handle_command(update, MagicMock())
    assert "Invitación creada" in update.effective_message.reply_text.call_args[0][0]
    print("✓ Admin /invite allowed")

    # Test /list any folder
    update = mock_update(admin_id, "/list admin_folder")
    await adapter._handle_command(update, MagicMock())
    assert "Archivos en 'admin_folder'" in update.effective_message.reply_text.call_args[0][0]
    print("✓ Admin /list any folder allowed")

    # Cleanup
    import shutil
    shutil.rmtree(base_dir)

if __name__ == "__main__":
    asyncio.run(test_permissions())
