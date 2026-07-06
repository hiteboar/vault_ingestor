# Documentación Técnica - Vault Ingestor 🛡️📁

Esta documentación detalla los tres pilares del proyecto **Vault Ingestor**: la **API (Raspberry Pi/Servidor Linux)**, la **Aplicación Móvil (Android)** y la **Aplicación de Escritorio (Windows)**. Su objetivo es proporcionar una guía técnica rigurosa que permita dar continuidad al desarrollo y mantenimiento del ecosistema.

---

## 🗺️ 1. Estructura del Código y Arquitectura de Comunicación

Vault Ingestor se diseña como una arquitectura cliente-servidor descentralizada y modular. A continuación se describe la distribución general de archivos y el flujo de comunicación.

```mermaid
graph TD
    subgraph Cliente Móvil (Android)
        M[vault_mobile/App.js] -->|Axios/SecureStore| MA[vault_mobile/api.js]
    end

    subgraph Cliente de Escritorio (Windows)
        D[version_desktop/console_ui.py] -->|Bridge PyWebView| DH[Frontend HTML5/Tailwind/Leaflet]
        D -->|FastAPI local o requests remoto| MA_D[Requests API]
    end

    subgraph Servidor Central (Raspberry Pi / Linux)
        A[app.py: Bootstrap/Modos] -->|Modo API| API[api/main.py: FastAPI Server]
        A -->|Modo Bot| BOT[adapters/telegram_adapter.py: Telegram Bot]
        API -->|Carga/Deduplicación| C[core/]
        BOT -->|LLM Agent| LA[core/agent.py: Gemini AI Admin]
        BOT -->|Deduplicación/Pipeline| C
    end

    MA -->|Túnel Cloudflare o WAN / HTTPS| API
    MA_D -->|Túnel Cloudflare o LAN / HTTPS| API
```

### 📁 Estructura General del Workspace

```text
vault_ingestor/
├── api/
│   ├── __init__.py
│   └── main.py                 # Puntos de acceso FastAPI y lógica de imágenes/miniaturas
├── adapters/
│   └── telegram_adapter.py     # Integración del bot de Telegram
├── core/
│   ├── __init__.py
│   ├── agent.py                # Implementación del Agente IA (Gemini API)
│   ├── auth.py                 # Gestor de tokens, emparejamientos y PINs
│   ├── dedup.py                # Indexación de Hashes para evitar duplicaciones
│   ├── env_manager.py          # Gestión y sincronización del archivo .env
│   ├── housekeeping.py         # Limpieza de archivos temporales
│   ├── manager.py              # Gestor de actualizaciones
│   ├── models.py               # Esquemas y modelos de datos básicos
│   ├── network.py              # Funciones de utilidad de red local
│   ├── pipeline.py             # Procesamiento y guardado de archivos multimedia
│   ├── state.py                # Persistencia del estado y settings
│   └── storage.py              # Utilidades de nombres y rutas de almacenamiento
├── vault_mobile/               # Código de la aplicación nativa React Native (Expo)
│   ├── App.js                  # Lógica del cliente, carrusel y componentes UI
│   ├── api.js                  # Llamadas de red e integración del cliente Axios
│   ├── app.json                # Configuración del paquete Expo
│   └── eas.json                # Configuración de compilaciones EAS (Android Preview)
├── version_desktop/            # Código de la aplicación de escritorio Windows
│   ├── console_ui.py           # GUI (PyWebView + HTML5) y puente Javascript-Python
│   ├── diagnose_desktop.py     # Diagnóstico de librerías y dependencias locales
│   ├── launcher.py             # Gestor de instalaciones, actualizaciones y ejecución
│   └── setup_desktop.py        # Configuración visual de variables .env
├── version_pi/
│   └── tools/                  # Herramientas de diagnóstico y reindexación en Raspberry
├── app.py                      # Punto de entrada unificado del backend (API/Bot)
├── install_vault.sh            # Script inteligente de instalación/reparación en Linux
└── run_vault.sh                # Script de arranque y obtención de datos de emparejamiento
```

### 🔌 Protocolo y Flujo de Comunicación

1. **Autenticación (QR / PIN)**:
   - El servidor expone un endpoint (`/api/auth/request`) para obtener un PIN temporal.
   - El cliente móvil o de escritorio escanea el código QR generado por la API o consola, el cual contiene un JSON estructurado con la URL del servidor y el PIN actual.
   - El cliente envía una petición `POST /api/auth/verify` con el PIN. El servidor responde con un **Token Permanente** generado aleatoriamente (`secrets.token_hex(32)`).
   - Los dispositivos cliente almacenan de forma segura este token y lo adjuntan en cada llamada de red usando la cabecera HTTP `X-Device-Token`. Para componentes multimedia del móvil que omiten cabeceras personalizadas (como los componentes de carga nativa de imágenes), la API permite pasar el token a través del parámetro de consulta `?token=...`.
2. **Acceso Remoto (Túnel Cloudflare)**:
   - Al iniciar la API, si la opción `ENABLE_REMOTE_ACCESS` está activada en `.env`, el servidor lanza un subproceso de `cloudflared` para crear un túnel seguro temporal (TryCloudflare) o persistente (utilizando `CLOUDFLARE_TOKEN`). La dirección pública resultante se publica en la terminal o se actualiza dinámicamente en el entorno del bot.

---

## 🚀 2. Pilar 1: La API & Backend (Raspberry Pi / Servidor Linux)

### 📋 Descripción y Función
El backend actúa como el motor central headless del ecosistema. Ejecuta una API REST para la gestión de archivos, geolocalización y sincronización de dispositivos, un worker en segundo plano para procesar y optimizar contenido multimedia, y un bot de Telegram con inteligencia artificial para interactuar y administrar el servidor mediante lenguaje natural.

### ⚙️ Funcionalidades Implementadas
*   **API REST Segura**: FastAPI provee endpoints de carga masiva, descarga y visualización de recursos verificando privilegios por dispositivo y rol (`admin` o `standard`).
*   **Generador y Caché de Miniaturas**: Genera versiones WebP o JPEG ligeras (300x300px) de fotos y vídeos bajo demanda con un semáforo de concurrencia (`asyncio.Semaphore(3)`) para proteger el procesador de la Raspberry Pi.
*   **Auto-reparación de Metadatos (Self-Healing)**: Durante el arranque, el servidor verifica que las rutas lógicas del archivo `metadata.jsonl` sigan existiendo en el disco físico. Si un archivo fue movido, busca su nueva ubicación bajo la carpeta de subidas y actualiza la base de datos automáticamente.
*   **Túnel WAN Integrado**: Creación y reconexión automática de túneles Cloudflare para evitar abrir puertos en el enrutador.
*   **Bot de Administración IA**: Servicio autónomo de Telegram que procesa imágenes sin comprimir (guardándolas e indexándolas) y ejecuta instrucciones del administrador en el sistema mediante el agente Gemini (`LLMAgent`).
*   **Gestión de Arranque**: Configuración unificada mediante demonios `systemd` para asegurar tolerancia a fallos.

### 📦 Requisitos y Herramientas Desarrolladas
*   **Requisitos del sistema**: Linux (Raspberry Pi OS / Debian), Python 3.9+, Rust & Cargo (compilación de criptografía), FFmpeg (extracción de fotogramas), y el ejecutable oficial `cloudflared`.
*   **`install_vault.sh`**: Script en Bash que detecta arquitectura, instala dependencias del sistema, genera el entorno virtual `.venv`, escribe la configuración básica en `.env` y registra/habilita los servicios `vault_api.service` y `vault_bot.service` bajo `systemd`.
*   **`run_vault.sh`**: Wrapper en Bash para aplicar permisos del sistema (`chmod 775`), reiniciar los demonios, consultar la API y generar en la consola del servidor un código QR de emparejamiento en formato ASCII.

### 🔍 Detalle Técnico (Clases, Métodos y Variables)

#### A. Módulo `api.main` (`api/main.py`)
Expone la lógica de la API FastAPI y la persistencia de metadatos en memoria.
*   **Variables de Configuración**:
    *   `STORAGE_DIR` (Path): Ruta física raíz para los archivos multimedia.
    *   `SAFE_STORAGE_DIR` (Path): Ruta protegida contra errores de permisos de escritura.
    *   `META_LOG` (Path): Ubicación del archivo de base de datos JSONL (`metadata.jsonl`).
    *   `CACHE_DIR` (Path): Carpeta de caché para miniaturas optimizadas.
    *   `thumb_semaphore` (`asyncio.Semaphore`): Semáforo con límite de 3 generaciones de miniaturas simultáneas.
*   **Clase `MetadataManager`**:
    *   `_cache` (dict): Diccionario en memoria que indexa metadatos estructurados de los archivos (`{item_id: metadata}`).
    *   `load(self)`: Carga el archivo `metadata.jsonl` en memoria. Ejecuta la indexación de archivos físicos en `uploaded_files/` para auto-reparar rutas rotas y deduplicar registros en base a la ubicación real.
    *   `get_item(self, item_id: str) -> Optional[dict]`: Retorna el registro de un archivo.
    *   `get_path(self, item_id: str) -> Optional[str]`: Retorna la ruta física del archivo.
    *   `update(self, item: dict)`: Inserta o actualiza un registro en el caché.
    *   `remove(self, item_id: str)`: Remueve un archivo del caché.
*   **Métodos Auxiliares**:
    *   `extract_mp4_creation_time(file_path: Path) -> Optional[str]`: Parsea directamente átomos MP4 (`mvhd`) para extraer la fecha en formato ISO UTC.
    *   `extract_metadata_timestamp(file_path: Path, content_type: Optional[str] = None) -> Optional[str]`: Extrae la fecha cronológica desde EXIF (usando `exifread` y Pillow), FFprobe (vídeos), metadatos internos de MP4 o patrones en el nombre de archivo (ej. `IMG_YYYYMMDD_...`).
    *   `extract_gps(file_path: Path) -> Optional[dict]`: Extrae coordenadas decimales de latitud y longitud desde metadatos EXIF o metadatos de vídeo de Apple/QuickTime.
    *   `update_physical_gps(file_path: Path, lat: float, lon: float) -> bool`: Inserta físicamente coordenadas en los metadatos EXIF de un archivo de imagen compatible.
    *   `maintain_cache(cache_dir: Path, max_size_mb: int)`: Mantiene el almacenamiento de caché por debajo del límite eliminando el 20% de las miniaturas más antiguas.

#### B. Clase `AuthManager` (`core/auth.py`)
Controla la seguridad de accesos y emparejamiento.
*   **Variables**:
    *   `state_file` (Path): Ruta del archivo `linked_devices.json`.
    *   `linked_devices` (dict): Lista de tokens vinculados con sus roles y carpetas permitidas.
    *   `pending_pins` (dict): Estructura temporal en memoria para PINs generados pendientes de vincular.
*   **Métodos**:
    *   `generate_pin(self, role: str, allowed_folders: List[str]) -> str`: Genera un PIN aleatorio de 6 dígitos con expiración de 5 minutos.
    *   `verify_pin(self, pin: str) -> Optional[str]`: Valida un PIN. Si es correcto, genera un token persistente de 32 bytes en hexadecimal y lo guarda en `linked_devices.json`.
    *   `is_token_valid(self, token: str) -> bool`: Valida un token de dispositivo y actualiza su fecha de último avistamiento (`last_seen`).

#### C. Clase `LLMAgent` (`core/agent.py`)
Agente conversacional de soporte en lenguaje natural e interacción del sistema.
*   **Variables**:
    *   `model_name` (str): Nombre del modelo Gemini (`gemini-1.5-flash` por defecto).
    *   `chat` (object): Instancia de la sesión de chat activa.
*   **Métodos**:
    *   `run_bash_command(self, command: str) -> str`: Ejecuta un comando en bash del servidor y retorna su salida estándar y de error (con un límite de 4000 caracteres para preservar la ventana de tokens).
    *   `read_file(self, path: str) -> str`: Lee el contenido UTF-8 de un archivo.
    *   `write_file(self, path: str, content: str) -> str`: Escribe o sobrescribe un archivo del sistema.
    *   `list_directory(self, path: str) -> str`: Lista archivos y subcarpetas en un directorio.
    *   `chat_message(self, message: str) -> str`: Envía un texto al agente de forma asíncrona manejando advertencias de cuota diaria de la API de Gemini (basado en `state/agent_usage.json`).

#### D. Clase `TelegramAdapter` (`adapters/telegram_adapter.py`)
Maneja el polling y eventos del bot de Telegram.
*   **Variables**:
    *   `bot` (Bot): Instancia del cliente de Telegram.
    *   `agent` (LLMAgent): Instancia local del agente de inteligencia artificial.
    *   `upload_dir` (Path): Carpeta donde se guardan los archivos multimedia descargados.
*   **Métodos**:
    *   `_handle_command(self, update, context) -> bool`: Enruta los comandos válidos del sistema.
    *   `_cmd_system_reboot(self, msg, is_admin: bool)`: Ejecuta el reinicio por hardware (`sudo reboot`).
    *   `_cmd_status(self, msg, chat_id, is_admin: bool)`: Envía un reporte del sistema: estado de servicios, RAM, CPU y espacio libre.
    *   `_cmd_get_access(self, msg, is_admin: bool)`: Reinicia la API en segundo plano y devuelve la nueva dirección WAN y PIN mediante imagen QR.
    *   `_handle_message(self, update, context)`: Coordina la descarga en chunks (`requests.get`) de documentos, fotos y vídeos entrantes. Si el mensaje es texto simple, lo delega al Agente conversacional de IA.

---

## 📱 3. Pilar 2: La App Móvil (Android)

### 📋 Descripción y Función
La aplicación móvil está desarrollada con **React Native** y **Expo**. Proporciona una interfaz visual elegante e intuitiva en el dispositivo móvil para interactuar con la nube privada. Permite a los usuarios visualizar el timeline multimedia, organizar archivos, realizar copias de seguridad de la galería y compartir contenido directamente desde Android.

### ⚙️ Funcionalidades Implementadas
*   **Sincronización por QR**: Configuración instantánea escaneando el código QR generado por la API central.
*   **Línea de Tiempo y Carpetas**: Rejilla fluida que agrupa las fotos y vídeos dinámicamente por Año y Mes (Timeline). Permite la navegación hacia subcarpetas personalizadas.
*   **Subida Masiva con Conservación de Metadatos**: El usuario puede seleccionar múltiples archivos. La aplicación extrae las fechas originales (usando `exif.DateTimeOriginal` en fotos e información del sistema en archivos) para que se cataloguen en el mes correspondiente del servidor.
*   **Visor Multimedia con Gestos (Lightbox)**: Galería táctil con carrusel lateral mediante gestos deslizantes (`PanResponder`) para pasar fotos/vídeos.
*   **Android Share Intent**: La app intercepta archivos enviados desde otras aplicaciones del sistema Android (por ejemplo, Google Photos o el Administrador de Archivos) mediante `expo-share-intent` y permite subirlos directamente a la carpeta seleccionada del Vault.
*   **Descarga Nativa e Invitaciones P2P**: Descarga archivos temporalmente a la memoria del teléfono (`expo-file-system`) y los comparte a través del diálogo de Android (`expo-sharing`). Permite a los administradores generar códigos QR de invitación para permitir accesos de lectura a carpetas específicas.

### 📦 Requisitos y Herramientas Desarrolladas
*   **Requisitos del sistema**: Android OS (APK compilada o ejecución en desarrollo vía Expo Go).
*   **`vault_mobile/api.js`**: Abstracción de red que expone métodos para interactuar con la API del servidor central mediante Axios, inyectando de forma automática las credenciales guardadas en el almacenamiento encriptado del dispositivo (`expo-secure-store`).

### 🔍 Detalle Técnico (Funciones, Componentes y Estado)

#### A. Módulo `api.js` (`vault_mobile/api.js`)
*   **Variables de Persistencia**:
    *   `TOKEN_KEY = 'vault_device_token'`: Clave de SecureStore para el token de autorización.
    *   `URL_KEY = 'vault_server_url'`: Clave de SecureStore para la dirección del servidor (local o WAN).
*   **Métodos Exportados**:
    *   `saveConnection(url, token)`: Guarda las credenciales encriptadas en el dispositivo.
    *   `getConnection()`: Retorna un objeto `{ url, token }` con la configuración actual.
    *   `clearConnection()`: Remueve las credenciales almacenadas del dispositivo.
    *   `uploadFile(uri, name, mimeType, folder, originalDate, onProgress)`: Genera un objeto `FormData` y realiza una petición multipart `POST /api/upload` con callbacks que reportan el progreso porcentual de subida.
    *   `getMediaUrl(item)`: Genera una URL de acceso multimedia firmada que incluye el token de seguridad como parámetro de consulta.

#### B. Componente Principal `App` (`vault_mobile/App.js`)
*   **Variables de Estado Críticas**:
    *   `connected` (boolean): `true` si el dispositivo se encuentra autenticado con un servidor.
    *   `view` ('gallery' | 'stats'): Vista activa de la pantalla de inicio.
    *   `items` (array): Colección de archivos e información indexada obtenida del backend.
    *   `currentFolder` (string): Identificador de la carpeta física o virtual actual (ej. `'root'`).
    *   `uploadState` (object): Registra el progreso de la subida masiva: `{ active, current, total, percent }`.
    *   `previewItem` (object): Metadatos del archivo actualmente abierto en el visor Lightbox.
    *   `shareFiles` (array): Lista de archivos cacheados pendientes de subir interceptados por el Share Intent de Android.
    *   `selectedInviteFolders` (array): Carpetas seleccionadas para el ámbito de una nueva invitación.
*   **Funciones Críticas de Ciclo de Vida y Eventos**:
    *   `loadData(showLoading)`: Consulta en paralelo los elementos indexados (`api.fetchItems`), el estado del hardware de la Raspberry (`api.fetchStatus`) y el rango de fechas de las carpetas físicas (`api.fetchFoldersMeta`).
    *   `processUploads(assets)`: Itera de forma asíncrona sobre una lista de archivos multimedia, extrae las fechas correspondientes e invoca a `api.uploadFile` mientras actualiza la barra de progreso de la interfaz.
    *   `handleBarcodeScanned({ data })`: Evento disparado al leer un código QR de emparejamiento. Extrae la URL del servidor y el PIN para realizar la vinculación.
    *   `panResponder`: Controlador táctil del visor Lightbox configurado para detectar movimientos horizontales (`dx > 50` o `dx < -50`) y deslizar de forma interactiva entre las imágenes de la galería.

---

## 💻 4. Pilar 3: La Aplicación de Escritorio (Windows)

### 📋 Descripción y Función
La aplicación de escritorio para Windows funciona en una modalidad dual: actúa como un **Cliente Gráfico Premium** capaz de conectarse a cualquier servidor central Vault (local o remoto) y, al mismo tiempo, integra un **Servidor Local Autónomo** que permite a los usuarios transformar su propio PC con Windows en el servidor de almacenamiento.

### ⚙️ Funcionalidades Implementadas
*   **Servidor Local Integrado**: Ejecuta el servidor FastAPI unificado en Windows en un hilo independiente (`uvicorn.run`), creando automáticamente las carpetas locales de almacenamiento y registrando tokens administradores transparentes.
*   **GUI Fluida en PyWebView**: Renderiza un panel de control HTML5 local utilizando Tailwind CSS.
*   **Explorador Geográfico (Map Explorer)**: Visor de mapas interactivo que agrupa y localiza geográficamente en el mapa (`Leaflet` y `MarkerCluster`) las fotos y vídeos del Vault basándose en sus coordenadas GPS EXIF.
*   **Gestor de Subidas Nativo con Drag & Drop**: Abre el diálogo nativo de Windows para la selección de múltiples archivos y arranca un hilo (`_select_and_upload_worker`) para transferir los archivos con actualizaciones de progreso visual.
*   **Tray de Windows (System Tray)**: Integra un icono en la barra de tareas de Windows (`pystray`) que mantiene la aplicación ejecutándose en segundo plano y provee un menú contextual rápido.
*   **Actualizador Automático Integrado**: Al arrancar, consulta la API de GitHub y actualiza de forma segura el código local descargando y extrayendo la última versión de la rama principal, omitiendo archivos sensibles.

### 📦 Requisitos y Herramientas Desarrolladas
*   **Requisitos del sistema**: Windows 10/11, Python 3.9+, librerías del sistema para Tkinter, y conectividad HTTPS para mapas remotos.
*   **`launcher.py`**: El instalador/iniciador primario de Windows. Oculta las ventanas negras de consola mediante llamadas de bajo nivel al sistema (`ShowWindow(hwnd, SW_HIDE)` de `ctypes`) y ejecuta `console_ui.py` utilizando el binario `pythonw.exe`.
*   **`setup_desktop.py`**: Interfaz auxiliar con cuadros de diálogo nativos de Tkinter para registrar las rutas iniciales del entorno en el archivo `.env`.
*   **`diagnose_desktop.py`**: Script de diagnóstico de dependencias gráficas locales.

### 🔍 Detalle Técnico (Clases, Métodos y Variables)

#### Clase `Api` (`version_desktop/console_ui.py`)
Define el puente bidireccional que expone funciones de Python hacia el entorno de ejecución de Javascript dentro del navegador empotrado.
*   **Métodos**:
    *   `is_local_server_running(self) -> bool`: Retorna el estado del servidor local integrado.
    *   `get_local_server_config(self) -> dict`: Parsea el archivo `.env` local y expone sus claves hacia el frontend.
    *   `select_storage_folder(self) -> str`: Invoca el selector de carpetas de Windows y retorna la ruta absoluta de la carpeta elegida.
    *   `activate_local_server(self, port, storage_dir, enable_remote) -> dict`: Escribe las variables en el `.env`, actualiza las referencias de configuración en caliente (`reinitialize_config()`), registra el token local y lanza el servidor en un hilo daemon.
    *   `link_remote_vault(self, url, pin) -> dict`: Realiza una petición POST de emparejamiento con un servidor remoto y guarda las credenciales en `client_settings.json`.
    *   `select_and_upload_files(self, folder) -> dict`: Abre el diálogo nativo `OPEN_DIALOG` para la selección múltiple y lanza el worker de subidas en un hilo secundario.
    *   `_select_and_upload_worker(self, file_paths, folder)`: Itera sobre los archivos seleccionados, extrae metadatos EXIF locales y realiza la petición POST multipart al servidor. Llama al método Javascript `updateUploadProgress` del frontend mediante `evaluate_js` para actualizar el porcentaje de barra en tiempo real.
    *   `download_url_to_file(self, url, filename, is_post, post_data_str) -> dict`: Invoca al diálogo `SAVE_DIALOG` de Windows para seleccionar la ruta de descarga, y escribe el flujo de datos HTTP recibido de forma incremental.
