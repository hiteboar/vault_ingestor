# Vault Ingestor - Tu Nube Privada y Descentralizada 🛡️📁

Vault Ingestor es un ecosistema avanzado de almacenamiento personal diseñado específicamente para funcionar de forma autónoma en una Raspberry Pi (o cualquier servidor Linux). El objetivo principal es proporcionar una alternativa privada a los servicios de nube comerciales, permitiéndote gestionar tus archivos, fotos y vídeos desde una aplicación móvil con total seguridad y sin configuraciones de red complejas.

### Objetivos Principales:
*   **Privacidad Total:** Tus datos nunca salen de tu hardware.
*   **Acceso Global sin Complicaciones:** Gracias a los túneles de Cloudflare, puedes acceder a tu servidor desde cualquier parte del mundo sin abrir puertos en tu router.
*   **Gestión Móvil Nativa:** Controla todo el sistema (usuarios, carpetas, estadísticas) desde una app moderna.
*   **Resiliencia:** Diseñado para funcionar 24/7 sin monitor (Headless), recuperándose automáticamente de fallos de red o reinicios.

---

## 🛠️ Manual de Instalación

Esta guía está diseñada para que puedas desplegar el sistema en cualquier dispositivo con Linux, como una Raspberry Pi.

### 1. Preparación e Instalación Básica
Clona el repositorio en tu dispositivo y ejecuta el instalador automático:

```bash
bash install_vault.sh
```
*Este script instalará las dependencias necesarias (Python, FFmpeg, etc.), configurará el entorno virtual y te pedirá la ruta donde quieres guardar los archivos.*

### 2. Configuración de Almacenamiento Externo (Recomendado)
Para usar un disco duro externo como unidad principal de almacenamiento, sigue estos pasos:

1.  **Identifica tu disco:** Conecta el disco y ejecuta `lsblk`. Identifica tu partición (ej: `/dev/sda1`).
2.  **Crea un punto de montaje:**
    ```bash
    sudo mkdir -p /mnt/vault_storage
    ```
3.  **Monta el disco:**
    ```bash
    sudo mount /dev/sda1 /mnt/vault_storage
    ```
4.  **Asegura el montaje automático (FSTAB):** Para que el disco se monte solo al reiniciar, edita el archivo `/etc/fstab`:
    ```bash
    # Obtén el UUID de tu disco
    sudo blkid /dev/sda1
    # Añade esta línea al final de /etc/fstab (reemplaza el UUID)
    UUID=tu-uuid-aqui /mnt/vault_storage ext4 defaults,nofail 0 2
    ```
5.  **Configura Vault:** Asegúrate de que en tu archivo `.env` la variable `STORAGE_DIR` apunte a `/mnt/vault_storage`.

### 3. Configuración de Arranque Automático
Para garantizar que el sistema se inicie solo cada vez que enciendas la Raspberry Pi, ejecuta el script de reparación que configura el servicio de sistema (`systemd`):

```bash
bash version_pi/tools/repair_system.sh
```
*Este comando crea un servicio llamado `vault_ingestor.service` que se encarga de vigilar el sistema y reiniciarlo automáticamente si detecta algún fallo.*

---

## 📱 Guía de Uso y Funcionalidades

El sistema se gestiona íntegramente desde la aplicación móvil.

### 1. Descarga de la App
Actualmente, la aplicación se puede obtener de dos formas:
*   **Para Usuarios:** Descarga el archivo `.apk` generado en la sección de "Releases" o compílalo tú mismo usando el comando `npx eas build -p android --profile preview` en la carpeta `vault_mobile`.
*   **Para Desarrolladores:** Instala [Expo Go](https://expo.dev/go) en tu móvil, entra en la carpeta `vault_mobile`, haz `npm install` y luego `npx expo start`.

### 2. Vincular la App con el Sistema
Una vez instalada la app:
1.  Inicia el servidor en la Raspberry Pi ejecutando `./run_vault.sh`.
2.  Aparecerá un **Código QR** y un **PIN** en la terminal.
3.  Abre la app en tu móvil y pulsa en **"Escanear QR"**.
4.  El primer dispositivo en vincularse será nombrado automáticamente como **Administrador**.

### 3. Funcionalidades Implementadas

*   **Panel de Estadísticas:** Visualiza en tiempo real el uso de CPU, RAM y espacio en disco de tu Raspberry Pi.
*   **Gestión de Roles:**
    *   **Admin:** Puede crear/borrar carpetas, ver todo el contenido y generar invitaciones.
    *   **Invitado (Standard):** Solo tiene acceso a las carpetas específicas para las que ha sido invitado.
*   **Invitaciones P2P:** El Administrador puede generar un código QR temporal desde una carpeta. Un invitado escanea ese código y obtiene acceso instantáneo a esa carpeta sin necesidad de crear cuentas.
*   **Streaming de Vídeo y Previsualización:** El sistema optimiza las imágenes y vídeos para que puedas verlos de forma fluida incluso con conexiones móviles.
*   **Subida Masiva:** Soporta la selección de múltiples archivos desde la galería del móvil para subidas rápidas.

---

*Desarrollado con ❤️ para la comunidad de auto-hospedaje.*
