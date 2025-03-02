from spade.behaviour import OneShotBehaviour
from loguru import logger
import json

import requests
import re
import os

# ------------------ Estructura carpetas --------------------

BASE_DIR = "LlmDecisionMaking"
STRUCTURE = {
    "Agents": {
        "decisions": {"1_day_decisions.json": {}},
        "actions.json": {},
        "memory.json": {},
        "profiles.json": {},
    },
    "LogsForDays": {
        "days": {"1_day_events_simulation.json": {}},
        "events_simulation.json": {},
    },
    "Config": {
        "days": {},
        "config_simulation.json": {},
    },
    "llm_config.json": {}
}


@staticmethod
def verify_and_create_structure():
    """
    Verifies if the directory structure and necessary files exist.
    If any file or folder is missing, it creates them with default values.
    """

    base_dir = True

    for folder, contents in STRUCTURE.items():
        folder_path = os.path.join(BASE_DIR, folder)

        # Crear carpeta si no existe
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            logger.warning(f"The directory: {folder_path} dont exist")
            logger.info(f"Created directory: {folder_path}")
            base_dir = False

        for file_name, default_content in contents.items():
            file_path = os.path.join(folder_path, file_name) if isinstance(default_content, dict) else folder_path

            # Si es un archivo, crearlo si no existe
            if isinstance(default_content, dict):  # Es un archivo JSON
                if not os.path.exists(file_path):
                    with open(file_path, "w", encoding="utf-8") as file:
                        json.dump(default_content, file, indent=4)
                    logger.info(f"Created file: {file_path}")
            else:  # Es una subcarpeta
                sub_folder_path = os.path.join(folder_path, file_name)
                if not os.path.exists(sub_folder_path):
                    os.makedirs(sub_folder_path)
                    logger.info(f"Created subdirectory: {sub_folder_path}")
    return base_dir

# ------------------ Llamadas LLM --------------------

async def oneshot_request_llm(agent, config=None, prompt=None):

    instance = RequestApiLLM(config, prompt)
    agent.add_behaviour(instance)

    # Wait for the behaviour to complete
    await instance.join()

    return instance.response


class RequestApiLLM(OneShotBehaviour):

    def __init__(self, config, prompt):
        super().__init__()
        self.config = config
        self.prompt = prompt
        self.response = None

    async def call_llm(self, config, prompt):
        """
        Calls the remote Ollama API to get a decision.
        """
        # Obtener configuración del LLM
        model = config.get("model")
        api_url = config.get("api_url")
        temperature = config.get("temperature")

        self.response = self.query_llm(prompt, model=model, api_url=api_url, temperature=temperature)


    def query_llm(self, prompt, model, api_url, temperature=0.7):
        """
        Sends a prompt to the LLM API and retrieves a structured JSON response.

        Returns:
            dict: The generated response from the model in JSON format.
        """
        payload = {
            "model": model,
            "prompt": prompt,
            "options": {
                "temperature": temperature
            }
        }

        try:
            response = requests.post(api_url, json=payload)
            response.raise_for_status()

            # Obtener la respuesta cruda
            response_text = response.text.strip()
            logger.info(f"Respuesta cruda del LLM: {response_text}")

            # Extraer solo las respuestas de "response": "..."
            json_fragments = []
            for line in response_text.splitlines():
                try:
                    parsed_line = json.loads(line)
                    if "response" in parsed_line:
                        json_fragments.append(parsed_line["response"])
                except json.JSONDecodeError:
                    logger.warning(f"Ignorando línea no válida: {line}")

            # Unir todos los fragmentos en un solo string
            combined_response = "".join(json_fragments).strip()

            # Intentar extraer el JSON final con regex
            match = re.search(r'\{.*\}', combined_response, re.DOTALL)
            if match:
                json_str = match.group(0)
                try:
                    parsed_json = json.loads(json_str)
                    return parsed_json
                except json.JSONDecodeError as e:
                    logger.error(f"Error al decodificar JSON final: {e}")
                    return None
            else:
                logger.error("No se encontró un JSON válido en la respuesta combinada.")
                return None

        except requests.exceptions.RequestException as e:
            logger.exception(f"Error conectando con el LLM: {e}")
            return None

    async def run(self):
        """
            Executes the behavior to request and receive the list of agent positions.
        """
        if self.config is None:
            logger.warning("Agent haven't LLM configured.")
        else:
            await self.call_llm(config=self.config, prompt=self.prompt)
            logger.info("Agent receive prompt.")