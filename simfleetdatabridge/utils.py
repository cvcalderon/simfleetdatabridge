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
                max_tokens=1000
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
            json_candidate = match.group(0)
            fixed_json = self.fix_unbalanced_braces(json_candidate)
            try:
                return json.loads(fixed_json)
            except json.JSONDecodeError as e:
                logger.error(f"Error al decodificar JSON: {e}")
        else:
            logger.error("No se encontró JSON válido en la respuesta.")
        return None

    def fix_unbalanced_braces(self, text: str) -> str:
        """
        Detecta y corrige desbalance de llaves en JSON tipo texto.
        """
        open_braces = text.count('{')
        close_braces = text.count('}')
        diff = open_braces - close_braces

        if diff > 0:
            logger.warning(f"Faltan {diff} llaves de cierre en la respuesta JSON. Se agregarán automáticamente.")
            text += '}' * diff
        elif diff < 0:
            logger.warning(f"Sobran {-diff} llaves de cierre en la respuesta JSON. Se intentará corregir.")
            # Esto es opcional, normalmente no pasa
            text = text.rstrip('}' * (-diff))

        return text

# ------------------------------------------------------------------------------------------------------------------------
# Others utils

def describe_profile(profile: dict, keys_to_describe: list) -> str:
    """
    Generates a profile description based on the specified main keys in 'keys_to_describe'.
    It uses predefined templates for each key and ignores sub-keys.

    Parameters:
        profile (dict): The complete profile dictionary.
        keys_to_describe (list): List of main keys to describe, e.g.,
            ["demographics", "mobility_preferences", "environment", "transport_options"]

    Returns:
        str: A string that describes the profile.
    """
    description_parts = []  # Accumulate the description parts

    for key, value in profile.items():
        if key in keys_to_describe:
            # Use a predefined template for each main key.
            if key == "demographics" and isinstance(value, dict):
                age = value.get("age", "unknown")
                gender = value.get("gender", "unknown")
                education = value.get("education", "unknown")
                occupation = value.get("occupation", "unknown")
                annual_income = value.get("annual_income", "unknown")
                description_parts.append(
                    f"Hi, I'm a {age}-year-old {gender}. I have a {education} degree and work as an {occupation}. My annual income is {annual_income} $."
                )
            elif key == "mobility_preferences" and isinstance(value, dict):
                eco = value.get("eco-consciousness", "unknown")
                time_sens = value.get("time-sensitivity", "unknown")
                comfort = value.get("comfort-preference", "unknown")
                budget = value.get("budget-sensitivity", "unknown")
                reliability = value.get("reliability-sensitivity", "unknown")
                description_parts.append(
                    f"When it comes to mobility, I consider eco-consciousness to be {eco}, time sensitivity {time_sens}, comfort {comfort}, budget sensitivity {budget}, and reliability {reliability}."
                )
            elif key == "environment" and isinstance(value, dict):
                arrival = value.get("arrival_time_limit", {})
                if isinstance(arrival, dict):
                    a_type = arrival.get("type", "unknown")
                    a_time = arrival.get("time", "unknown")
                    a_purpose = arrival.get("purpose", "unknown")
                    description_parts.append(
                        f"I need to be at my destination by a {a_type} deadline at {a_time} for {a_purpose}."
                    )
                else:
                    description_parts.append(f"Environment details: {value}")
            elif key == "transport_options" and isinstance(value, list):
                options_str = ", ".join(value)
                description_parts.append(
                    f"My available transport options are: {options_str}."
                )
            else:
                # Use a generic format for any other key
                description_parts.append(f"{key}: {value}")

    # Combine all description parts into a single string.
    profile_description = " ".join(description_parts)
    return profile_description

