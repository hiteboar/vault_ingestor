import os
import subprocess
import asyncio
import json
from datetime import datetime
from pathlib import Path

class LLMAgent:
    def __init__(self, api_key: str = None, model_name: str = None):
        self.api_key = api_key or os.getenv("AGENT_API_KEY")
        self.model_name = model_name or os.getenv("AGENT_LLM_MODEL", "gemini-1.5-flash")
        self.chat = None
        self._init_agent()

    def _init_agent(self):
        if not self.api_key:
            print("[agent] Warning: AGENT_API_KEY is not set. Agent will not work.")
            return

        try:
            import google.generativeai as genai
        except ImportError:
            print("[agent] google-generativeai is not installed.")
            return

        genai.configure(api_key=self.api_key)
        
        system_instruction = (
            "You are the Vault OS Agent, a highly capable AI system administrator and developer operating directly "
            "on the Raspberry Pi hosting the Vault Ingestor project.\n\n"
            "You have admin privileges (sudo) and can interact with the system using bash commands and file operations.\n"
            "Your goals are to help the user manage the system, run diagnoses, implement or update code, "
            "and push changes to the repository if needed.\n\n"
            "Rules:\n"
            "1. Be concise, precise, and highly professional in Spanish. Avoid excessive chatter.\n"
            "2. When modifying the Vault Ingestor codebase, always ensure it is correct and valid before pushing.\n"
            "3. If you make changes and want to commit/push, use run_bash_command to run git commands. "
            "Ensure you configure user.name and user.email first if they are not set, using AGENT_GIT_USER and AGENT_GIT_EMAIL env vars.\n"
            "4. You are talking to the primary administrator of this Pi, so you can execute any requested command safely.\n"
            "5. TOKEN SAVING RULES (CRITICAL):\n"
            "   - Try to resolve tasks in the minimum number of steps/tool calls.\n"
            "   - Do not call multiple tools if a single tool call can achieve the result.\n"
            "   - When running bash commands, always filter large outputs (e.g. use `grep`, `head -n 50`, `tail` or file redirections). "
            "Never execute raw commands that output hundreds of lines of logs or text as it will exhaust your token limits."
        )

        tools = [
            self.run_bash_command,
            self.read_file,
            self.write_file,
            self.list_directory
        ]

        try:
            model = genai.GenerativeModel(
                model_name=self.model_name,
                tools=tools,
                system_instruction=system_instruction
            )
            self.chat = model.start_chat(enable_automatic_function_calling=True)
            print(f"[agent] Initialized with model {self.model_name}")
        except Exception as e:
            print(f"[agent] Error initializing Gemini model: {e}")

    def run_bash_command(self, command: str) -> str:
        """Executes a bash command in the system (Raspberry Pi) and returns stdout and stderr.
        
        Args:
            command: The exact shell command to run on the system.
        """
        print(f"[agent tool] Executing bash command: {command}")
        try:
            res = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=120)
            
            # Truncate output to avoid exhausting tokens on long output
            limit = 4000
            stdout = res.stdout or ""
            stderr = res.stderr or ""
            
            if len(stdout) > limit:
                stdout = stdout[:limit] + "\n... [SALIDA ESTÁNDAR TRUNCADA POR LÍMITE DE TOKENS] ..."
            if len(stderr) > limit:
                stderr = stderr[:limit] + "\n... [SALIDA DE ERROR TRUNCADA POR LÍMITE DE TOKENS] ..."
                
            return f"Exit Code: {res.returncode}\nStdout:\n{stdout}\nStderr:\n{stderr}"
        except Exception as e:
            return f"Error executing command: {str(e)}"

    def read_file(self, path: str) -> str:
        """Reads the contents of a file in the filesystem.
        
        Args:
            path: The absolute or relative path to the file.
        """
        print(f"[agent tool] Reading file: {path}")
        try:
            p = Path(path).resolve()
            if not p.exists():
                return f"Error: File {path} does not exist."
            if p.is_dir():
                return f"Error: {path} is a directory. Use list_directory instead."
                
            content = p.read_text(encoding="utf-8", errors="replace")
            
            # Truncate large files to avoid exhausting token window
            limit = 4000
            if len(content) > limit:
                content = content[:limit] + "\n... [CONTENIDO DEL ARCHIVO TRUNCADO POR LÍMITE DE TOKENS] ..."
                
            return content
        except Exception as e:
            return f"Error reading file: {str(e)}"

    def write_file(self, path: str, content: str) -> str:
        """Writes or overwrites content to a file in the filesystem.
        
        Args:
            path: The path to the file.
            content: The text content to write.
        """
        print(f"[agent tool] Writing to file: {path}")
        try:
            p = Path(path).resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"Successfully wrote {len(content)} characters to {path}."
        except Exception as e:
            return f"Error writing to file: {str(e)}"

    def list_directory(self, path: str) -> str:
        """Lists the files and folders inside a directory.
        
        Args:
            path: The path to the directory.
        """
        print(f"[agent tool] Listing directory: {path}")
        try:
            p = Path(path).resolve()
            if not p.exists():
                return f"Error: Directory {path} does not exist."
            if not p.is_dir():
                return f"Error: {path} is a file, not a directory."
            items = []
            for x in p.iterdir():
                t = "📁" if x.is_dir() else "📄"
                items.append(f"{t} {x.name}")
            return "\n".join(items) if items else "(directory is empty)"
        except Exception as e:
            return f"Error listing directory: {str(e)}"

    def _increment_and_check_quota(self) -> str:
        """Increments daily API usage and returns a warning string if quota usage exceeds 80%."""
        # Determine daily limit based on the configured model
        limit = 1500
        model_lower = self.model_name.lower()
        if "pro" in model_lower:
            limit = 50
        elif "flash" in model_lower:
            limit = 1500

        today = datetime.now().strftime("%Y-%m-%d")
        
        # Save usage relative to project directory
        usage_file = Path("state/agent_usage.json")
        usage_file.parent.mkdir(parents=True, exist_ok=True)

        data = {"date": today, "count": 0}
        if usage_file.exists():
            try:
                with open(usage_file, "r") as f:
                    saved = json.load(f)
                    if saved.get("date") == today:
                        data = saved
            except:
                pass

        data["count"] += 1
        try:
            with open(usage_file, "w") as f:
                json.dump(data, f)
        except:
            pass

        count = data["count"]
        warning_threshold = int(limit * 0.8) # 80%
        if count >= warning_threshold:
            pct = int((count / limit) * 100)
            return f"\n\n⚠️ *Alerta de Cuota*: Has consumido el {pct}% de tus consultas diarias permitidas para el modelo actual ({count}/{limit} consultas hoy)."
        return ""

    async def chat_message(self, message: str) -> str:
        """Sends a message to the agent chat session and returns the final text response."""
        if not self.chat:
            return "❌ Error: El agente no está inicializado. Verifica AGENT_API_KEY en .env."
            
        # Increment request count and check daily quota
        quota_warning = self._increment_and_check_quota()
            
        loop = asyncio.get_running_loop()
        try:
            # Run the synchronous function in an executor to avoid blocking the async event loop
            response = await loop.run_in_executor(None, self.chat.send_message, message)
            
            # Append quota warning if 80% is exceeded
            return response.text + quota_warning
        except Exception as e:
            print(f"[agent] Error during chat_message: {e}")
            return f"❌ Error de comunicación con la IA: {e}"
