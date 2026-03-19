import logging
from typing import List, Dict, Any, Optional, Callable
import google.generativeai as genai
from core import agent_tools

logger = logging.getLogger(__name__)

class VaultAgent:
    """
    Agente IA Core para gestión y análisis del Vault.
    Independiente de la interfaz de usuario (Telegram, etc).
    """
    def __init__(self, api_key: str, model_name: str = "gemini-flash-latest", storage_dir: str = "./vault_storage"):
        if not api_key:
            raise ValueError("Se requiere GEMINI_API_KEY para inicializar el agente.")
        
        genai.configure(api_key=api_key)
        
        # Registrar herramientas
        self.storage_dir = storage_dir
        self.available_tools = [
            agent_tools.get_disk_usage,
            agent_tools.list_vault_structure,
            agent_tools.file_operation,
            agent_tools.read_project_file,
            agent_tools.write_project_file,
            agent_tools.run_system_command
        ]
        
        self.model = genai.GenerativeModel(
            model_name=model_name,
            tools=self.available_tools,
            system_instruction=(
                "Eres el Asistente de Gestión del Vault Ingestor. "
                "Tu objetivo es ayudar al administrador a gestionar archivos, analizar código y generar reportes. "
                f"La carpeta base del Vault es: {self.storage_dir}. "
                "Cualquier operación de archivo debe realizarse respetando esta ruta. "
                "Sé conciso y profesional. Antes de realizar cambios destructivos (borrar, sobreescribir), "
                "pide siempre confirmación explícita detallando lo que vas a hacer."
            )
        )
        self.chat_sessions: Dict[str, Any] = {}
        self.tools: Dict[str, Callable] = {f.__name__: f for f in self.available_tools}

    def register_tool(self, name: str, func: Callable):
        """Registra una función como herramienta para la IA."""
        self.tools[name] = func
        logger.info(f"Herramienta registrada: {name}")

    async def chat(self, session_id: str, message: str) -> str:
        """
        Envía un mensaje al agente y devuelve la respuesta.
        Mantiene el contexto por session_id. Soporta llamadas a funciones automáticas.
        """
        if session_id not in self.chat_sessions:
            # Habilitar el envío automático de respuestas de funciones
            self.chat_sessions[session_id] = self.model.start_chat(enable_automatic_function_calling=True)
        
        chat = self.chat_sessions[session_id]
        
        try:
            # Note: start_chat with enable_automatic_function_calling=True handles the loop.
            response = await chat.send_message_async(message)
            return response.text
        except Exception as e:
            logger.error(f"Error en comunicación con Gemini: {e}")
            return f"❌ Error en el agente: {str(e)}"

    def clear_session(self, session_id: str):
        self.chat_sessions.pop(session_id, None)
