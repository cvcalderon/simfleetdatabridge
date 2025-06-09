from spade.behaviour import OneShotBehaviour
from loguru import logger
import json
import re
import requests
import openai
from datetime import datetime, timedelta

from typing import List, Dict

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
                    f"Hi, I'm a {age}-year-old {gender}. I have a {education} degree and my occupation is an {occupation}. My annual income is {annual_income} $."
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

def describe_short_memory(short_memory, environment):
    descriptions = []

    # Extract arrival limit data
    limit_time_str = environment["arrival_time_limit"]["time"]
    limit_time = datetime.strptime(limit_time_str, "%I:%M %p")
    purpose = environment["arrival_time_limit"].get("purpose", "the destination")
    limit_type = environment["arrival_time_limit"].get("type", "strict")

    for entry in short_memory:
        # Date formatting
        day = entry["fecha"]["day_text"]
        month = entry["fecha"]["mes"]
        day_number = entry["fecha"]["day_number"]
        date_str = f"{day}, {month} {day_number}"

        # Basic transport info
        departure = entry["departure_time"]
        arrival = entry["arrival_time"]
        travel_time = entry["travel_time_min"]
        wait_time = entry["waiting_time_min"]
        distance = entry["distance_km"]
        mode = entry["transport_mode"].replace("-", " ")
        cost = entry["cost"]

        # Decision info
        was_late = entry["decision_context"]["was_late"]
        completed = entry["decision_context"]["completed"]
        reason = entry["decision_context"].get("reason", "-")

        if not completed or arrival is None:
            fail_reason = f"Reason: {reason}." if reason and reason != "-" else "No reason provided."
            description = (
                f"On {date_str}, the trip using {mode} starting at {departure} was not completed. "
                f"{fail_reason} No arrival time available. The agent did not reach their destination for {purpose} "
                f"(which was scheduled before {limit_time_str})."
            )
        else:
            # Completed trip
            arrival_dt = datetime.strptime(arrival, "%I:%M %p")
            time_diff = int((arrival_dt - limit_time).total_seconds() / 60)
            punctuality = ""

            if limit_type == "strict" or limit_type == "flexible":
                if time_diff > 0:
                    punctuality = f"Arrival was {time_diff} minutes late for {purpose} (limit: {limit_time_str})."
                elif time_diff < 0:
                    punctuality = f"Arrival was {abs(time_diff)} minutes early for {purpose} (limit: {limit_time_str})."
                else:
                    punctuality = f"Arrival was exactly on time for {purpose} (limit: {limit_time_str})."

            status = "There was a delay." if was_late else "No delay."
            completion = "Trip completed."

            description = (
                f"On {date_str}, departure was at {departure} and arrival at {arrival}. "
                f"Mode of transport: {mode}. Duration: {travel_time} minutes (waiting time: {wait_time} min), "
                f"distance: {distance} km. Cost: ${cost:.2f}. {completion} {punctuality}" #{status} {completion} {punctuality}"
            )

        descriptions.append(description.strip())

    return descriptions


def describe_plan(day_data):
    travel = day_data.get("travel", {})
    date = day_data.get("date_context", {})

    # Acceso seguro a los valores necesarios
    transport_mode = travel.get("suggested_transport_mode", "unspecified transport")
    departure_time = travel.get("suggested_departure_time", "unspecified time")

    day_name = date.get("day_name", "Unknown day")
    month_name = date.get("month_name", "Unknown month")
    day_number = date.get("day", "Unknown date")

    # Construcción del mensaje
    description = (
        f"The trip is scheduled for {day_name}, {month_name} {day_number}. "
        f"The mode of transport will be {transport_mode}, "
        f"with a departure time at {departure_time}."
    )

    return description


def generate_pattern_descriptions(merged_patterns: dict) -> dict:
    """
    Generates optimized natural language descriptions for each merged mobility pattern.

    Args:
        merged_patterns (dict): Dictionary of merged patterns, as stored in long_memory["by_pattern"]

    Returns:
        dict: {1: "Description of pattern 1", 2: "Description of pattern 2", ...}
    """
    descriptions = {}

    for i, (pattern_id, pattern) in enumerate(merged_patterns.items(), start=1):
        detection = pattern.get("detection", {})
        behavior = pattern.get("behavior", {})
        context = pattern.get("external_context", {})

        # Extract detection data
        days = detection.get("day_names", [])
        months = detection.get("months", [])
        time_window = detection.get("time_window", {})
        start_time = time_window.get("start", "")
        end_time = time_window.get("end", "")
        frequency = detection.get("frequency", 0)

        # Extract behavior data
        modes = behavior.get("modes_used", [])
        travel_time = behavior.get("avg_travel_time_min", 0)
        wait_time = behavior.get("avg_waiting_time_min", 0)
        cost = behavior.get("avg_cost", 0)
        distance = behavior.get("avg_distance_km", 0)

        # Extract context
        delays = context.get("delays_occurred_days", 0)
        missed = context.get("missed_destination_days", 0)

        # Formatting helpers
        days_str = ", ".join(days)
        months_str = ", ".join(months)
        modes_str = ", ".join(modes)

        # Build narrative
        desc = (
            f"A frequent mobility pattern was observed during the month(s) of {months_str} "
            f"on the following weekdays: {days_str}. All trips occurred within a consistent time window "
            f"from {start_time} to {end_time}, with a total of {frequency} recorded instances.\n\n"
            f"The user consistently used {modes_str} as their transport mode. Each trip averaged "
            f"{travel_time} minutes of travel time, {wait_time} minutes of waiting, and covered approximately "
            f"{distance} kilometers. These trips had an average cost of {cost}.\n\n"
        )

        if delays > 0 or missed > 0:
            desc += (
                f"There were {delays} day(s) with delays and {missed} day(s) where the destination was missed. "
            )
        else:
            desc += "There were no delays or missed trips recorded. "

        #desc += "No common external situations were reported, and no reflections or adjustments were noted."

        descriptions[i] = desc.strip()

    return descriptions


def describe_events(events: List[Dict]) -> List[str]:
    descriptions = []

    for event in events:
        name = event.get("name", "Unnamed event")
        category = event.get("category", "unknown")
        subtype = event.get("subtype", "")
        details = event.get("details", {})

        description = f"{name} ({category}/{subtype})."

        if category == "transport":
            if subtype == "strike":
                ratio = details.get("affected_ratio", 0)
                transport_type = details.get("transport_type", "transport")
                percent = int(ratio * 100)
                description += f" About {percent}% of the {transport_type} service is expected to be disrupted."
            elif subtype == "maintenance":
                line = details.get("line", "unknown line")
                reduction = int(details.get("reduction_in_service", 0) * 100)
                description += f" The {line} will operate at {100 - reduction}% capacity due to maintenance."
        elif category == "weather":
            subtype = event.get("subtype", "weather event").lower()

            # Base description
            description += f" A {subtype} is expected."

            # Add details if available
            if "precipitation_mm" in details:
                rain = details["precipitation_mm"]
                description += f" Estimated precipitation: {rain} mm."
            if "snow_cm" in details:
                snow = details["snow_cm"]
                description += f" Snow accumulation may reach {snow} cm."
            if "wind_speed_kmph" in details:
                wind = details["wind_speed_kmph"]
                description += f" Winds could reach up to {wind} km/h."
            if "temperature_c" in details:
                temp = details["temperature_c"]
                description += f" Expected temperature: {temp}°C."
            if "visibility_km" in details:
                vis = details["visibility_km"]
                description += f" Visibility may drop to {vis} km."

        descriptions.append(description)

    return descriptions