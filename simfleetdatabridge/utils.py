from pydantic.v1.validators import validate_json
from spade.behaviour import OneShotBehaviour
from loguru import logger
import json
import re
import requests
import openai


async def oneshot_request_llm(agent, config=None, prompt=None):
    instance = RequestApiLLM(config, prompt)
    agent.add_behaviour(instance)
    await instance.join()
    return instance.response


class RequestApiLLM(OneShotBehaviour):

    def __init__(self, config, prompt):
        super().__init__()
        self.config = config
        self.prompt = prompt
        self.response = None

    async def run(self):
        if self.config is None:
            logger.warning("El agente no tiene configuración LLM.")
            return

        use_sdk = self.config.get("use_openai_sdk", True)

        if use_sdk:
            await self.call_llm_with_sdk(self.config, self.prompt)
        else:
            await self.call_llm_with_requests(self.config, self.prompt)

        logger.info("El agente recibió la respuesta.")

    # ------------------ MODO SDK OpenAI ------------------

    async def call_llm_with_sdk(self, config, prompt):
        model = config.get("model")
        base_url = config.get("api_url")
        api_key = config.get("api_key")
        temperature = config.get("temperature", 0.7)

        try:
            client = openai.OpenAI(
                base_url=base_url,
                api_key=api_key or None  # Permite modelos sin key
            )

            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=500
            )

            raw_text = response.choices[0].message.content.strip()
            logger.debug(f"Texto combinado:\n{raw_text}")

            self.response = self.extract_json(raw_text)

        except Exception as e:
            logger.exception(f"Error llamando al LLM con SDK: {e}")
            self.response = None

    # ------------------ MODO requests.post() ------------------

    async def call_llm_with_requests(self, config, prompt):
        model = config.get("model")
        api_url = config.get("api_url")
        temperature = config.get("temperature", 0.7)

        payload = {
            "model": model,
            "prompt": prompt,
            "options": {"temperature": temperature}
        }

        try:
            response = requests.post(api_url, json=payload)
            response.raise_for_status()
            response_text = response.text.strip()
            #logger.debug(f"Respuesta cruda del LLM:\n{response_text}")

            # Extraer fragmentos de tipo "response"
            json_fragments = []
            for line in response_text.splitlines():
                try:
                    parsed_line = json.loads(line)
                    if "response" in parsed_line:
                        json_fragments.append(parsed_line["response"])
                except json.JSONDecodeError:
                    logger.warning(f"Línea ignorada no válida: {line}")

            combined_response = "".join(json_fragments).strip()
            logger.debug(f"Texto combinado:\n{combined_response}")

            self.response = self.extract_json(combined_response)

        except Exception as e:
            logger.exception(f"Error llamando al LLM (requests): {e}")
            self.response = None

    # ------------------ Extracción JSON común ------------------

    def extract_json(self, text):
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError as e:
                logger.error(f"Error al decodificar JSON: {e}")
        else:
            logger.error("No se encontró JSON válido en la respuesta.")
        return None

