from spade.behaviour import OneShotBehaviour
from loguru import logger
import json

import requests
import re
import os


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