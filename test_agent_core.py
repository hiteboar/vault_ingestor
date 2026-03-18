import asyncio
import os
from dotenv import load_dotenv
from core.agent import VaultAgent

async def test_agent():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ Error: GEMINI_API_KEY no encontrada en .env")
        return

    print("--- Iniciando Agente de Prueba ---")
    agent = VaultAgent(api_key, storage_dir="./vault_storage")
    
    # Prueba 1: Consulta de espacio en disco
    print("\nPregunta: ¿Cuánto espacio queda en el disco?")
    response = await agent.chat("test_user", "¿Cuánto espacio queda en el disco?")
    print(f"Respuesta Agent: {response}")
    
    # Prueba 2: Análisis de archivos
    print("\nPregunta: ¿Qué hace el archivo requirements.txt?")
    response = await agent.chat("test_user", "¿Qué puedes decirme del archivo requirements.txt de este proyecto?")
    print(f"Respuesta Agent: {response}")

if __name__ == "__main__":
    # Asegurarse de que existe la carpeta de storage para evitar errores de herramienta
    os.makedirs("./vault_storage", exist_ok=True)
    asyncio.run(test_agent())
