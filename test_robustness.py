import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Añadir el directorio actual al path para importar app
sys.path.append(os.getcwd())

import app

def test_storage_validation():
    print("--- Test: Validación de Almacenamiento ---")
    
    # 1. Test carpeta normal (debe pasar)
    test_dir = Path("./test_vault_local")
    test_dir.mkdir(exist_ok=True)
    ok, msg = app.is_storage_ready(test_dir)
    print(f"Local dir: {msg}")
    assert ok is True
    
    # 2. Test ruta externa NO montada (debe fallar)
    with patch("os.name", "posix"):
        with patch("os.path.ismount", return_value=False):
            # Usar un mock para evitar instanciar PosixPath
            mock_mnt = MagicMock(spec=Path)
            mock_mnt.resolve.return_value = mock_mnt
            mock_mnt.__str__.return_value = "/mnt/external_drive"
            mock_mnt.exists.return_value = True
            mock_mnt.iterdir.return_value = iter([])
            
            ok, msg = app.is_storage_ready(mock_mnt)
            print(f"External (not mounted): {msg}")
            assert ok is False
            assert "NO está montado" in msg

    # 3. Test ruta externa SI montada (debe pasar)
    with patch("os.name", "posix"):
        with patch("os.path.ismount", return_value=True):
            mock_mnt = MagicMock(spec=Path)
            mock_mnt.resolve.return_value = mock_mnt
            mock_mnt.__str__.return_value = "/mnt/external_drive"
            mock_mnt.exists.return_value = True
            
            ok, msg = app.is_storage_ready(mock_mnt)
            print(f"External (mounted): {msg}")
            assert ok is True

    print("✅ Pruebas de validación de almacenamiento completadas.")

if __name__ == "__main__":
    try:
        test_storage_validation()
    except Exception as e:
        print(f"❌ Error en los tests: {e}")
        sys.exit(1)
