import logging
from typing import List, Dict, Any, Optional, Callable
import google.generativeai as genai
from core import agent_tools

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-1.5-flash-latest"

class VaultAgent:
    """
    Agente IA Core para gestión y análisis del Vault.
    Independiente de la interfaz de usuario (Telegram, etc).
    """
    def __init__(self, api_key: str, model_name: Optional[str] = None, storage_dir: str = "./vault_storage"):
        if not api_key:
            raise ValueError("Se requiere GEMINI_API_KEY para inicializar el agente.")
        
        # Default model if not provided
        self.model_name = model_name or DEFAULT_MODEL
        
        genai.configure(api_key=api_key)
        
        # Registrar herramientas base
        self.storage_dir = storage_dir
        self.available_tools = [
            agent_tools.get_disk_usage,
            agent_tools.list_vault_structure,
            agent_tools.file_operation,
            agent_tools.read_project_file,
            agent_tools.write_project_file,
            agent_tools.run_system_command,
            agent_tools.execute_app_command
        ]
        
        self.model = genai.GenerativeModel(
            model_name=model_name,
            tools=self.available_tools,
            system_instruction=(
                "Eres el Asistente de Gestión del Vault Ingestor. "
                "Tu objetivo es ayudar al administrador a gestionar archivos, analizar código y ejecutar comandos de sistema. "
                f"La carpeta base del Vault es: {self.storage_dir}. "
                "Cualquier operación de archivo debe realizarse respetando esta ruta.\n\n"
                "HERRAMIENTAS:\n"
                "1. Comandos de App: Usa `execute_app_command` para acciones nativas del bot (ej: /invite, /list, /preview, /download). "
                "Casi siempre es mejor usar el comando nativo si existe.\n"
                "2. Comandos de Sistema: Usa `run_system_command` para tareas de administración de Linux/OS (ej: df, ls, systemctl, tail).\n"
                "3. Gestión de archivos: Tienes herramientas para leer/escribir archivos del proyecto.\n\n"
                "IMPORTANTE: Procura ser proactivo. Si el usuario pide ayuda para gestionar usuarios, usa /access o /invite. "
                "Si pide espacio, usa df o du. Si detectas problemas, revisa los logs del sistema.\n\n"
                "Sé conciso y profesional. Antes de realizar cambios destructivos (borrar, sobreescribir código), "
                "pide siempre confirmación explícita detallando lo que vas a hacer."
            )
        )
        self.chat_sessions: Dict[str, Any] = {}
        self.tools: Dict[str, Callable] = {f.__name__: f for f in self.available_tools}

    def set_model(self, model_name: str):
        """Actualiza el modelo de Gemini utilizado."""
        # Copiar instrucciones del modelo actual si existe
        instr = getattr(self.model, "_system_instruction", None) if hasattr(self, "model") else None
        
        self.model_name = model_name
        self.model = genai.GenerativeModel(
            model_name=model_name,
            tools=self.available_tools,
            system_instruction=instr
        )
        logger.info(f"Modelo cambiado a: {model_name}")

    def test_model(self) -> bool:
        """Realiza una pequeña prueba para verificar si el modelo es accesible."""
        try:
            # Una llamada mínima que no gaste muchos tokens
            self.model.generate_content("ping", generation_config={"max_output_tokens": 1})
            return True
        except Exception as e:
            logger.error(f"Error probando modelo {self.model_name}: {e}")
            return False

    def register_tool(self, name: str, func: Callable):
        """Registra o actualiza una función como herramienta para la IA."""
        self.tools[name] = func
        logger.info(f"Herramienta registrada/actualizada: {name}")

    async def chat(self, session_id: str, message: str) -> str:
        """
        Envía un mensaje al agente y devuelve la respuesta.
        Mantiene el contexto por session_id. Maneja llamadas a funciones manualmente para soportar herramientas dinámicas.
        """
        if session_id not in self.chat_sessions:
            # Iniciamos chat sin automatic_function_calling para controlar el bucle nosotros
            self.chat_sessions[session_id] = self.model.start_chat()
        
        chat = self.chat_sessions[session_id]
        
        try:
            response = await chat.send_message_async(message)
            
            # Bucle de ejecución de funciones (máximo 10 iteraciones por seguridad)
            for _ in range(10):
                if not response.candidates[0].content.parts:
                    break
                
                # Buscar si hay llamadas a funciones
                function_calls = [p.function_call for p in response.candidates[0].content.parts if p.function_call]
                if not function_calls:
                    break
                
                responses = []
                for fc in function_calls:
                    f_name = fc.name
                    f_args = fc.args
                    
                    if f_name in self.tools:
                        try:
                            # Ejecutar la función (soportando tanto síncronas como asíncronas)
                            import inspect
                            if inspect.iscoroutinefunction(self.tools[f_name]):
                                result = await self.tools[f_name](**f_args)
                            else:
                                result = self.tools[f_name](**f_args)
                        except Exception as e:
                            result = f"Error ejecutando {f_name}: {str(e)}"
                    else:
                        result = f"Error: Tool {f_name} no encontrada."
                    
                    responses.append(genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=f_name,
                            response={'result': result}
                        )
                    ))
                
                # Enviar los resultados de vuelta al modelo
                response = await chat.send_message_async(responses)
            
            return response.text
        except Exception as e:
            logger.error(f"Error en comunicación con Gemini: {e}")
            return f"❌ Error en el agente: {str(e)}"

    def clear_session(self, session_id: str):
        self.chat_sessions.pop(session_id, None)
