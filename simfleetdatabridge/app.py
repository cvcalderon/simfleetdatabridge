import json
import os
import re
import asyncio
import subprocess
import shutil
import functools
import time

from spade.agent import Agent
from spade.behaviour import OneShotBehaviour, State, FSMBehaviour

from simfleetdatabridge.llmbase import LlmBase
from simfleetdatabridge.utils import oneshot_request_llm

from loguru import logger
from datetime import datetime, timedelta
from pathlib import Path

PREPARE_MEMORY = "PREPARE_MEMORY"
DECISION_MAKING = "DECISION_MAKING"
PREPARE_OUTPUT = "PREPARE_OUTPUT"
RUN_SIMULATION = "RUN_SIMULATION"

class EngineAgent(Agent, LlmBase):
    """
    After these tasks are done in the Simulator constructor, the simulation is started when the ``run`` method is called.
    """

    def __init__(self, config, sim_path, jid="engine@localhost", password="secret"):
        super().__init__(jid=jid, password=password)
        LlmBase.__init__(self, sim_path)    # Initialize LlmBase with the simulation path

        self.config = config  # LLM engine config
        self.path = Path(sim_path)  # Simulation Path file
        self.base_dir = Path(sim_path)

        self.agents_action = {}
        self.reflection = False
        self.actual_day = None
        self.agent_used_actions = {}

        self.status = None
        self.stopped = False

        #Metrics
        self.evaluation_metrics = {}


    def is_finished(self):
        """
        Checks if the engine is finished.

        Returns:
            bool: whether the simulation is finished or not.
        """
        return self.stopped

    def initialize_memory(self, profiles):
        """Inicializa la memoria si está vacía."""
        return {agent: {"short_memory": [], "long_memory": {"by_mode": {}}} for agent in profiles}

    def update_memory_with_simulation(self, sim_metrics, umbral_memoria=3):
        """Actualiza la memoria interna del agente con los datos de la simulación y mantiene short_memory dentro del umbral."""

        #logger.warning("DEBUG 1 - Memory: {} ".format(self.memory))

        for category in ("LlmPedestrianAgent", "TaxiCustomerAgent"):
            for agent_data in sim_metrics.get("DetailedMetrics", {}).get(category, []):
                agent_name = agent_data["name"].split("@")[0]

                #if agent_name in self.get_agent_names():
                trip_completion_timestamp = agent_data["trip_completion_timestamp"]
                trip_time = agent_data["trip_time"]
                waiting_time = agent_data["waiting_time"]
                transport_mode = agent_data["transport"]
                cost = agent_data["cost"]
                distance_km = agent_data["distance"] / 1000

                # Evaluar si el viaje fue realmente completado
                trip_completed = trip_completion_timestamp > 0.0 and trip_time > 0.0 and distance_km > 0.0

                if trip_completed:
                    reason = "-"
                    departure_time = self.real_seconds_to_scaled_time(
                        trip_completion_timestamp - trip_time - waiting_time
                    )
                else:
                    # Buscar última acción asignada
                    last_action = self.agents_action.get(agent_name)
                    inferred_transport_mode = last_action["action_name"] if last_action else "unknown"
                    inferred_departure_time = last_action["departure_time"] if last_action else None

                    reason = (
                        f"Trip not completed: agent waited {round(waiting_time, 2)} minutes using mode '{inferred_transport_mode}', "
                        "but was not picked up or did not reach destination. Inferred data was used."
                    )

                    # Usar datos inferidos
                    transport_mode = inferred_transport_mode
                    departure_time = inferred_departure_time

                entry = {
                    "day": self.actual_day,
                    "departure_time": departure_time if trip_completed else inferred_departure_time,
                    "arrival_time": self.real_seconds_to_scaled_time(
                        trip_completion_timestamp) if trip_completed else None,
                    "travel_time_min": round(trip_time, 2),
                    "waiting_time_min": round(waiting_time, 2),
                    "distance_km": distance_km,
                    "transport_mode": transport_mode,
                    "cost": cost,
                    "decision_context": {
                        "reason": reason,
                        "alternative_considered": []
                    },
                }

                # Inicializar memoria si no existe
                #self.memory.setdefault(agent_name, {"short_memory": [], "long_memory": {"by_mode": {}}})

                # Mantener el tamaño de short_memory dentro del umbral
                if len(self.memory[agent_name]["short_memory"]) >= umbral_memoria:
                    self.memory[agent_name]["short_memory"].pop(0)  # Eliminar el más antiguo

                # Agregar la nueva entrada a short_memory
                self.memory[agent_name]["short_memory"].append(entry)

                #logger.warning("DEBUG 2 - Memory: {} ".format(self.memory))

                # Añadir al historial la short memory
                self.short_memory_history.setdefault(agent_name, []).append(entry)

                # Actualizar la memoria larga
                self.update_long_memory(agent_name, entry)

        # Guardar memoria en archivo
        memory_path = os.path.join(self.base_dir, "agents/short_memory.json")
        os.makedirs(os.path.dirname(memory_path), exist_ok=True)

        try:
            with open(memory_path, 'w') as f:
                json.dump(self.short_memory_history, f, indent=4)
        except Exception as e:
            logger.error(f"Error al escribir en {memory_path}: {e}")


    def update_long_memory(self, agent_name, entry):
        """Actualiza long_memory con los datos agregados en short_memory."""

        mode = entry["transport_mode"]

        # Inicializar estructura si no existe
        if agent_name not in self.memory:
            self.memory[agent_name] = {"short_memory": [], "long_memory": {"by_mode": {}}}

        if "long_memory" not in self.memory[agent_name]:
            self.memory[agent_name]["long_memory"] = {"by_mode": {}}

        if mode not in self.memory[agent_name]["long_memory"]["by_mode"]:
            self.memory[agent_name]["long_memory"]["by_mode"][mode] = {
                "total_days": 0,
                "avg_travel_time": 0,
                "avg_waiting_time": 0,
                "avg_cost": 0,
                "reflections": {
                    "summary": "-",
                    "adjustment": "-"
                }
            }

        mode_data = self.memory[agent_name]["long_memory"]["by_mode"][mode]

        # Actualizar métricas
        mode_data["total_days"] += 1
        mode_data["avg_travel_time"] = ((mode_data["avg_travel_time"] * (mode_data["total_days"] - 1)) + entry[
            "travel_time_min"]) / mode_data["total_days"]
        mode_data["avg_waiting_time"] = ((mode_data["avg_waiting_time"] * (mode_data["total_days"] - 1)) + entry[
            "waiting_time_min"]) / mode_data["total_days"]
        mode_data["avg_cost"] = ((mode_data["avg_cost"] * (mode_data["total_days"] - 1)) + entry["cost"]) / mode_data[
            "total_days"]

        #logger.warning("DEBUG 3 - Memory: {} ".format(self.memory))

    async def setup(self):
        """
        Setup method executed when the agent starts.
        Loads profiles and memory from JSON files.
        """

        #New simulation
        self.load_framework_config(self.config) # Load framework config - actions + llm
        self.load_agent_profiles()  # Cargar perfiles
        self.load_memory()  # Cargar memoria
        self.scale_range_time(
            start_time_day=self.environment.get("start_time_day"),
            end_time_day=self.environment.get("end_time_day")
        )


    async def run(self):
        """
        Starts the engine
        """

        engine_run = FSMEngineBehaviour()
        self.add_behaviour(engine_run)

        # Crear y ejecutar el comportamiento de toma de decisiones
        #decision_behaviour = DecisionMakingBehaviour(self.config)
        #self.add_behaviour(decision_behaviour)

        #await decision_behaviour.join()
        #self.stopped = True


class EngineBehaviour(State):

    async def on_start(self):
        """
            Logs the start of the agent behaviour
        """
        logger.debug("Strategy {} started in Engine".format(type(self).__name__))


    def check_options_all_agents(self):
        all_agents_actions = {}

        # Extraemos los perfiles y las opciones de transporte
        profile_data = self.agent.profiles  # Información de los perfiles
        profile_transport_modes = {
            profile_name: set(profile_info.get("environment", {}).get("transport_options", []))
            for profile_name, profile_info in profile_data.items()
        }

        # Obtener todas las acciones posibles
        available_actions = self.agent.actions  # Diccionario de acciones con class_path y strategy_path

        # Iteramos sobre cada agente
        for agent_name in self.agent.get_agent_names():
            memory_agent = self.agent.get_agent_memory_info(agent_name)
            short_memory = memory_agent.get("short_memory", [])

            # Extraer modos de transporte ya usados
            used_actions = {entry["transport_mode"] for entry in short_memory if "transport_mode" in entry}

            # Quiero acumular las acciones usadas por el agente. Porque en otra función la memoria corta tiene un umbral de 3 y no aparece todas las opciones usadas
            #self.used_actions = used_actions

            # **Acumular las acciones previas**
            if agent_name not in self.agent.agent_used_actions:
                self.agent.agent_used_actions[agent_name] = set()

            # Agregar las nuevas acciones usadas
            self.agent.agent_used_actions[agent_name].update(used_actions)

            # Obtener los transportes permitidos según su perfil
            available_transports = profile_transport_modes.get(agent_name, set())

            # **Si el agente ya ha usado todas sus opciones de transporte, omitirlo**
            if self.agent.agent_used_actions[agent_name].issuperset(available_transports):
                logger.info(f"{agent_name} has already used all the transport options. Omitting in this iteration.")
                continue  # No procesa este agente

            logger.warning(f"DEBUG 1 - profile_transport_modes: {profile_transport_modes}")
            logger.warning(f"DEBUG 2 - available_transports: {available_transports}")
            logger.warning(f"DEBUG 3 - used_actions: {used_actions}")
            #logger.warning(f"DEBUG 4 - accumulated_used_actions: {self.agent.agent_used_actions[agent_name]}")

            # Obtener departure_time válido
            departure_time = None

            if memory_agent and short_memory:
                last_departure = short_memory[-1].get("departure_time")

                if last_departure:
                    departure_time = last_departure
                    #logger.warning(f"DEBUG 2 - departure_time from memory: {departure_time}")
                else:
                    logger.warning(f"{agent_name} has invalid (None) departure_time in last memory entry.")
            else:
                logger.warning(f"{agent_name} has no short memory.")

            if not departure_time:
                arrival_time_limit = profile_data.get(agent_name, {}).get("environment", {}).get("arrival_time_limit",
                                                                                                 {}).get("time")

                if arrival_time_limit:
                    try:
                        arrival_time = datetime.strptime(arrival_time_limit, "%I:%M %p")
                        departure_time = (arrival_time - timedelta(minutes=10)).strftime("%I:%M %p")
                        logger.info(f"Estimated fallback departure_time for {agent_name}: {departure_time}")
                    except ValueError:
                        logger.error(f"Incorrect time format for {agent_name}: {arrival_time_limit}")
                        departure_time = arrival_time_limit
                else:
                    departure_time = arrival_time_limit

            # Filtrar acciones válidas (solo transportes aún no usados)
            valid_actions = [
                {
                    "action_name": action_name,
                    "class_path": available_actions[action_name]["class_path"],
                    "strategy_path": available_actions[action_name]["strategy_path"],
                    "departure_time": str(departure_time)
                }
                for action_name in available_transports - used_actions  # Diferencia de conjuntos para excluir usados
                if action_name in available_actions
            ]
            # Metrics
            self._init_agent_metrics(agent_name)
            metrics = self.agent.evaluation_metrics[agent_name]
            metrics["transport_modes_selected"].append(valid_actions[0]["action_name"])

            # Dejar la elección final al LLM
            if valid_actions:
                all_agents_actions[agent_name] = valid_actions[0]  # Si hay varias, se elige la primera

        return all_agents_actions

    def load_latest_simfleet_config(self, directory: str) -> tuple:
        """
        Searches for and loads the SimFleet configuration file with the highest number of days.

        Args:
            directory (str): Path to the directory containing the configuration files.

        Returns:
            tuple: A tuple containing:
                - The number of days (int).
                - The original filename without "X_day_" (str).
                - The content of the latest configuration JSON file (dict).

        Raises:
            FileNotFoundError: If no valid configuration file is found.
            ValueError: If there is an issue loading the JSON file.
        """
        try:
            config_files = [f for f in os.listdir(directory) if f.endswith(".json")]
        except FileNotFoundError:
            logger.error(f"Directory '{directory}' does not exist.")
            raise FileNotFoundError(f"Directory '{directory}' does not exist.")

        # Regular expression to capture the number of days and the rest of the filename
        pattern = re.compile(r"(\d+)_day_(.+\.json)")

        latest_config = None
        latest_clean_name = None
        latest_days = -1

        for file in config_files:
            match = pattern.match(file)
            if match:
                days = int(match.group(1))
                clean_name = match.group(2)  # Parte del nombre sin el número de días y "_day_"
                if days > latest_days:
                    latest_days = days
                    latest_config = file
                    latest_clean_name = clean_name

        if not latest_config:
            logger.error("No valid configuration file found.")
            raise FileNotFoundError("No valid configuration file found.")

        latest_config_path = os.path.join(directory, latest_config)
        logger.info(f"Loading configuration from: {latest_config_path}")

        # Load the JSON file
        try:
            with open(latest_config_path, "r") as f:
                config_data = json.load(f)
            logger.info(f"Configuration '{latest_clean_name}' loaded successfully.")
            return latest_days, latest_clean_name, config_data
        except json.JSONDecodeError:
            logger.error(f"Error loading JSON file: {latest_config_path}")
            raise ValueError(f"Error loading JSON file: {latest_config_path}")

    def generate_travel_prompt(self, agent_id, agent_profile, agent_memory):

        prompt = {
            agent_id: {
                "user_profile": agent_profile,
                "travel_memory": agent_memory,
                "instructions": {
                    "task": "Your role is to analyze the user's travel history and determine the optimal transportation mode for the upcoming day, while also exploring viable alternatives when appropriate. **Only modes included in 'transport_options' should be considered**. Your decision should be informed by past experiences ('memory'), aligned with the user's mobility preferences, and responsive to the current environmental context.",
                    "evaluation_steps": [
                        {
                            "step": 1,
                            "title": "Evaluation of Recent Travel (Short Memory)",
                            "description": "Analyze the most recent day's travel data, including departure and arrival times, travel time, waiting time, distance and cost. If the type is 'strict', any arrival after the limit is considered late. If the type is 'flexible', allow a reasonable margin. Also analyze whether the travel time is consistent and corresponds to the distance ('distance_km')."
                        },
                        {
                            "step": 2,
                            "title": "Assessment of Aggregated Data (Long Memory)",
                            "description": "Review the historical performance of each transportation mode based on average travel time, waiting time, cost, and reflections. Identify which modes have shown consistent performance and which have been problematic."
                        },
                        {
                            "step": 3,
                            "title": "Exploration of Alternative Options",
                            "description": "If a transportation mode has insufficient historical data or has not been used recently, prioritize testing it to gather experience. If the current optimal choice has been consistently used, explore an alternative mode at a reasonable frequency."
                        },
                        {
                            "step": 4,
                            "title": "Decision-Making for the Next Day",
                            "description": "Select the best transportation mode based on available data. If a new alternative is being explored. Any suggested alternative must be compatible with the user's profile, the type of event, and the acceptable level of risk (e.g., avoid unnecessary risks if the event is 'strict')."
                        },
                        {
                            "step": 5,
                            "title": "Output Strict JSON",
                            "description": "Respond ONLY with a valid JSON that matches the required structure. DO NOT add any text, python code, explanation, or markdown."
                        }
                    ],
                    "output_requirements": {
                        "format": "**STRICT JSON ONLY**.",
                        "structure": {
                            "decision_context": {
                                "reason": "Explain the reasoning behind the decision, referencing profile constraints, historical performance, and whether a new mode is being tested.",
                                "transport_alternative_considered": [
                                    "list of alternative transport modes if applicable"]
                            },
                            "reflections": {
                                "summary": "Provide a summary of key reflections from historical data (long_memory), including insights from previous travel experiences.",
                                "adjustment": "Describe any suggested adjustments for future trips, particularly regarding time management and mode selection."
                            },
                            "next_day_decision": {
                                "suggested_departure_time": "HH:MM AM/PM",
                                "suggested_transport_mode": "Only modes included in 'transport_options'"
                            }
                        }
                    }
                }
            }
        }

        return json.dumps(prompt, indent=4)

    #Metrics
    def _init_agent_metrics(self, agent_name):
        if agent_name not in self.agent.evaluation_metrics:
            self.agent.evaluation_metrics[agent_name] = {
                "valid_json_count": 0,
                "total_responses": 0,
                "reasoned_correctly_count": 0,
                "response_times_sec": [],
                "transport_modes_selected": []
            }

    async def decision_making(self, agent_name, profile, past_memory):
        """
        Calls the LLM to determine the best transport mode for the next day.
        """
        max_attempts = 3
        attempt = 0
        decision = None

        # Generar el nuevo prompt con la estructura actualizada
        prompt = self.generate_travel_prompt(agent_name, profile, past_memory)

        #Metrics
        self._init_agent_metrics(agent_name)

        logger.warning(f"DEBUG prompt: {prompt}")

        while attempt < max_attempts:
            attempt += 1
            logger.warning(f"Attempt #{attempt} to get valid decision for {agent_name}")

            #Metrics
            start_time = time.time()

            # Llamada al LLM - Abre y cierra conexión
            decision = await oneshot_request_llm(self.agent, config=self.agent.model_config, prompt=prompt)

            #Metrics
            end_time = time.time()
            response_time = end_time - start_time

            metrics = self.agent.evaluation_metrics[agent_name]
            metrics["total_responses"] += 1
            metrics["response_times_sec"].append(response_time)

            is_structured = self.is_valid_structure(decision)
            if is_structured:
                metrics["valid_json_count"] += 1

                is_reasoned = self.is_valid_decision(decision, profile, self.agent.actions)
                if is_reasoned:
                    metrics["reasoned_correctly_count"] += 1
                    # Guardar el modo de transporte elegido si es válido
                    transport_mode = decision["next_day_decision"]["suggested_transport_mode"].lower()
                    metrics["transport_modes_selected"].append(transport_mode)
                    logger.warning(f"DEBUG Transport mode: {transport_mode}")


            logger.warning(f"DEBUG decisión: {decision}")

            if decision and self.is_valid_structure(decision) and self.is_valid_decision(
                    decision,
                    profile,
                    self.agent.actions
            ):

                break  # Decisión válida
            else:
                decision = None  # Forzamos fallback

        if decision is None:
            # Recuperamos la short_memory como en check_options_all_agents
            memory_agent = self.agent.get_agent_memory_info(agent_name)
            short_memory = memory_agent.get("short_memory", []) if memory_agent else []

            # Valores por defecto
            last_mode = "walk"
            last_time = "06:30 AM"
            day = self.agent.actual_day

            if short_memory:
                last_entry = short_memory[-1]
                last_mode = last_entry.get("transport_mode", last_mode)
                last_time = last_entry.get("departure_time", last_time)
                day = str(last_entry.get("day", day) - 1)

            decision = {
                "decision_context": {
                    "reason": f"LLM response was invalid, empty, or failed parsing. Fallback logic used previous mode: {last_mode} of day {day}.",
                    "transport_alternative_considered": []
                },
                "reflections": {
                    "summary": "-",
                    "adjustment": "-"
                },
                "next_day_decision": {
                    "suggested_departure_time": last_time,
                    "suggested_transport_mode": last_mode
                }
            }

            logger.warning(f"DEBUG Fallback based on short_memory: {decision}")

            #Metrics
            metrics["transport_modes_selected"].append("fallback")

        return decision


    def update_reflection_memory(self, agent_name, llm_response):
        if agent_name not in self.agent.memory:
            raise ValueError(f"Agent {agent_name} not found in memory.")

        agent_data = self.agent.memory[agent_name]
        short_memory = agent_data["short_memory"]
        long_memory = agent_data["long_memory"]

        #logger.warning("DEBUG 4.1 - Reflection: {} ".format(agent_data))
        #logger.warning("DEBUG 4.2 - Reflection: {} ".format(short_memory))
        #logger.warning("DEBUG 4.3 - Reflection: {} ".format(long_memory))

        if not short_memory:
            raise ValueError("No short_memory data available to update.")

        # Get the latest entry in short_memory
        last_entry = short_memory[-1]
        transport_mode = last_entry["transport_mode"]

        # Update decision_context in the latest short_memory entry
        last_entry["decision_context"].update({
            "reason": llm_response["decision_context"]["reason"],
            "alternative_considered": llm_response["decision_context"]["transport_alternative_considered"]
        })

        # Update reflections in the corresponding transport mode in long_memory
        if transport_mode not in long_memory["by_mode"]:
            raise ValueError(f"Transport mode {transport_mode} not found in long_memory.")

#        long_memory["by_mode"][transport_mode]["reflections"] = [{
#            "summary": llm_response["reflections"]["summary"],
#            "adjustment": llm_response["reflections"]["adjustment"]
#        }]

        summary = llm_response["reflections"].get("summary", "").strip()
        adjustment = llm_response["reflections"].get("adjustment", "").strip()

        # Solo actualiza si ambos tienen contenido significativo
        if summary and summary != "-" and adjustment and adjustment != "-":
            long_memory["by_mode"][transport_mode]["reflections"] = [{
                "summary": summary,
                "adjustment": adjustment
            }]
        else:
            logger.warning(f"Reflections not updated for {transport_mode} due to missing or placeholder values.")

        #SOLUCIONA ESTE PROBLEMA PARA GUARDAR LA MEMORIA A LARGO PLAZO

        # Añadir al historial la short memory
        #self.agent.long_memory_history[agent_name].append(long_memory["by_mode"][transport_mode]["reflections"])

    def is_valid_structure(self, decision: dict) -> bool:
        try:
            required_structure = {
                "decision_context": ["reason",
                                     "transport_alternative_considered"],
                "reflections": ["summary", "adjustment"],
                "next_day_decision": ["suggested_departure_time", "suggested_transport_mode"]
            }

            for section, keys in required_structure.items():
                if section not in decision:
                    logger.warning(f"Missing section: '{section}' in decision")
                    return False
                for key in keys:
                    if key not in decision[section]:
                        logger.warning(f"Missing key: '{key}' in section '{section}'")
                        return False

            return True

        except Exception as e:
            logger.error(f"Error checking required keys: {e}")
            return False

    def is_valid_decision(self, decision, profile, available_actions):
        try:
            transport_mode = decision["next_day_decision"]["suggested_transport_mode"].lower()
            departure_time = decision["next_day_decision"]["suggested_departure_time"]

            # Validar transporte
            valid_transports = set(profile.get("environment", {}).get("transport_options", []))
            if transport_mode not in valid_transports or transport_mode not in available_actions:
                logger.warning(f"Invalid transport mode suggested: {transport_mode}")
                return False

            # Validar hora de salida
            departure_minutes = self.agent._convert_to_minutes(departure_time)

            if not (self.agent.start_time <= departure_minutes <= self.agent.end_time):
                logger.warning(
                    f"Departure time {departure_time} ({departure_minutes} min) is outside allowed range "
                    f"({self.agent.start_time}-{self.agent.end_time} min)."
                )
                return False

            return True

        except Exception as e:
            logger.error(f"Error validating LLM decision: {e}")
            return False

    async def run(self):
        """
            Abstract method that should be implemented in subclasses. This is where the specific strategy of the
            vehicle will be executed.
        """
        raise NotImplementedError


################################################################
#                                                              #
#                 FSM LLM Engine Strategy                      #
#                                                              #
################################################################

class EngineDecisionMakingState(EngineBehaviour):
    async def on_start(self):
        await super().on_start()
        self.agent.status = DECISION_MAKING
        logger.debug("{} in Decision making State".format(self.agent.jid))

    async def run(self):
        new_decisions = {}

        self.agent.agents_action = self.check_options_all_agents()
        #logger.warning("DEBUG 1 - Decision: {} ".format(self.agent.agents_action))

        if len(self.agent.agents_action) < len(self.agent.profiles.keys()):
            perfiles_sin_procesar = set(self.agent.profiles.keys()) - set(self.agent.agents_action.keys())
            #logger.warning("DEBUG 3 - Perfiles sin procesar: {} ".format(perfiles_sin_procesar))
        else:
            self.set_next_state(PREPARE_OUTPUT)
            return

        for agent_name in perfiles_sin_procesar:
            profile = self.agent.get_agent_info(agent_name)
            past_memory = self.agent.get_agent_memory_info(agent_name)

            decision = await self.decision_making(agent_name, profile, past_memory)

            new_decisions[agent_name] = decision

            suggested_departure_time = decision["next_day_decision"].get("suggested_departure_time")
            suggested_transport_mode = decision["next_day_decision"].get("suggested_transport_mode").lower()

            agent_actions = self.agent.actions

            action_path = agent_actions.get(suggested_transport_mode, {}).get("class_path")
            strategy_path = agent_actions.get(suggested_transport_mode, {}).get("strategy_path")

            self.agent.agents_action[agent_name] = {
                "action_name": suggested_transport_mode,
                "class_path": action_path,
                "strategy_path": strategy_path,
                "departure_time": suggested_departure_time
            }

            #logger.warning("DEBUG 4 - Decision: {} ".format(self.agent.agents_action))

            # Reflexión
            self.update_reflection_memory(agent_name, decision)

        #logger.warning("DEBUG 4.5 - Decision: {} ".format(self.agent.memory))

        memory_path = os.path.join(self.agent.base_dir, "agents/long_memory.json")
        with open(memory_path, 'w') as f:
            json.dump(self.agent.long_memory_history, f, indent=4)

        dest_file = os.path.join(
            self.agent.base_dir, "agents/decisions", f"{self.agent.actual_day}_day_decisions.json"
        )
        Path(dest_file).parent.mkdir(parents=True, exist_ok=True)

        if os.path.exists(dest_file):
            logger.debug(f"El archivo para el día {self.agent.actual_day} ya existe.")

        with open(dest_file, "w") as f:
            json.dump(new_decisions, f, indent=4)

        logger.info("[DecisionMakingBehaviour] Decision process completed.")

        memory_path = Path(self.agent.base_dir) / "agents/memory.json"
        memory_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with memory_path.open('w') as f:
                json.dump(self.agent.memory, f, indent=4)
        except Exception as e:
            logger.error(f"Error al escribir en {memory_path}: {e}")
            return

        if self.agent.actual_day == self.agent.environment.get("days"):
            self.agent.stopped = True

            #Metrics
            with open("llm_evaluation_metrics.json", "w") as f:
                json.dump(self.agent.evaluation_metrics, f, indent=4)

        if self.agent.agents_action is not None:
            self.set_next_state(PREPARE_OUTPUT)

class EnginePrepareOutputState(EngineBehaviour):
    async def on_start(self):
        await super().on_start()
        self.agent.status = PREPARE_OUTPUT
        logger.debug("{} in Prepare output State".format(self.agent.jid))

    async def run(self):
        #logger.info("{} arrived at its destination".format(self.agent.jid))

        simfleet_path = os.path.join(self.agent.base_dir, "config/simfleet")
        simfleet_path = Path(simfleet_path)

        day, name, sim_config = self.load_latest_simfleet_config(simfleet_path)
        decisions = self.agent.agents_action

        #logger.warning("DEBUG 2: {} in Prepare output State".format(decisions))

        for customer in sim_config.get("customers", []):
            customer_name = customer.get("name")
            if customer_name in decisions:
                decision = decisions[customer_name]
                # Actualizar delay usando depature_time (conversión a segundos)
                dep_time = decision.get("departure_time")
                if dep_time:
                    customer["delay"] = self.agent.scaled_time_to_real_seconds(str(dep_time))
                else:
                    logger.debug(f"Advertencia: No se encontró 'departure_time' para {customer_name}.")
                # Actualizar class y strategy
                #logger.warning("DEBUG 2.2: {} ".format(decision.get("class_path", customer.get("class"))))
                customer["class"] = decision.get("class_path", customer.get("class"))
                customer["strategy"] = decision.get("strategy_path", customer.get("strategy"))
                customer["delay"] = self.agent.scaled_time_to_real_seconds(decision.get("departure_time", customer.get("delay")))
            else:
                logger.debug(f"Advertencia: No hay decisión para el cliente {customer_name}.")

        sim_config["max_time"] = self.agent.get_real_seconds_range()
        sim_config["mobility_metrics"] = "simfleetdatabridge.actions.metrics.control.AgentsMobilityClass"

        self.agent.actual_day = day + 1

        end_path = os.path.join(simfleet_path, str(self.agent.actual_day) + "_day_" + name)
        end_path = Path(end_path)
        # Verificar si ya existe un archivo para ese día en la carpeta days
        #dest_file = f"LlmDecisionMaking/Config/days/{self.agent.next_day+1}_day_config_simulation.json"
        #dest_path = os.path.join(simfleet_path, end_path)
        if os.path.exists(end_path):
            logger.debug(f"El archivo para el día {day} ya existe.")

        self.agent.path = end_path

        with open(end_path, 'w') as f:
            json.dump(sim_config, f, indent=4)

        #self.agent.agents_action = None

        # (Opcional) Si se desea mover en vez de copiar, se puede borrar el original:
        #os.remove('LlmDecisionMaking/Config/config_simulation.json')
        #self.agent.stopped = True
        self.set_next_state(RUN_SIMULATION)
        return

class EngineRunSimulationState(State):
    async def on_start(self):
        await super().on_start()
        self.agent.status = RUN_SIMULATION
        self.retries = 0
        logger.debug(f"{self.agent.jid} in Run Simulation State")

    def run_simfleet_sync(self, path):
        try:
            result = subprocess.run(
                ["simfleet", "--config", str(path), "-r"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )
            return result.returncode, result.stdout.decode(), result.stderr.decode()
        except subprocess.CalledProcessError as e:
            return e.returncode, e.stdout.decode() if e.stdout else "", e.stderr.decode() if e.stderr else ""

    async def run_simulation_async(self, path):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, functools.partial(self.run_simfleet_sync, path))

    async def run(self):
        while self.retries < 3:
            logger.info(f"Attempt {self.retries + 1} of 3: Running Simfleet...")

            try:
                return_code, stdout, stderr = await self.run_simulation_async(self.agent.path)

                logger.info(stdout)
                if return_code == 0:
                    logger.info("Simfleet simulation finished successfully.")
                    self.set_next_state(PREPARE_MEMORY)
                    return
                else:
                    logger.warning(f"Simfleet failed with exit code {return_code}. Retrying...")
                    logger.error(stderr)
                    self.retries += 1

            except Exception as e:
                logger.error(f"Exception during Simfleet execution: {e}")
                self.retries += 1

        logger.error(f"{self.agent.jid} reached maximum retry attempts. Finishing...")
        self.agent.stopped = True


class EnginePrepareMemoryState(EngineBehaviour):
    async def on_start(self):
        await super().on_start()
        self.agent.status = PREPARE_MEMORY
        logger.debug("{} in Prepare memory State".format(self.agent.jid))

    async def run(self):
        """Prepara la memoria del agente y actualiza los datos de la simulación."""

        # Inicializar memoria si está vacía
        if not self.agent.memory:
            self.agent.memory = self.agent.initialize_memory(self.agent.get_agent_names())

        # Verificar existencia del archivo de métricas antes de abrirlo
        metrics_file = Path('simfleet_metrics.json')
        if not metrics_file.exists():
            logger.error("El archivo simfleet_metrics.json no existe. No se actualizará la memoria.")
            return

        try:
            with metrics_file.open('r') as archivo:
                metrics = json.load(archivo)
        except json.JSONDecodeError as e:
            logger.error(f"Error al cargar JSON desde {metrics_file}: {e}")
            return

        # Actualizar memoria con los datos de simulación (sin pasar memory como parámetro)
        self.agent.update_memory_with_simulation(metrics)

        # Guardar la memoria actualizada
        memory_path = Path(self.agent.base_dir) / "agents/memory.json"
        memory_path.parent.mkdir(parents=True, exist_ok=True)  # Asegura que la carpeta exista

        try:
            with memory_path.open('w') as f:
                json.dump(self.agent.memory, f, indent=4)
        except Exception as e:
            logger.error(f"Error al escribir en {memory_path}: {e}")
            return

        # Copiar métricas al directorio de días
        destination_path = Path(
            self.agent.base_dir) / "metrics/days" / f"{self.agent.actual_day}_day_simfleet_metrics.json"
        destination_path.parent.mkdir(parents=True, exist_ok=True)  # Asegura que la carpeta exista

        try:
            shutil.copy(metrics_file, destination_path)
            metrics_file.unlink()  # Elimina el archivo original
        except Exception as e:
            logger.error(f"Error al mover {metrics_file} a {destination_path}: {e}")
            return

        # Avanzar al siguiente día en la simulación
        #self.agent.actual_day += 1

        self.set_next_state(DECISION_MAKING)
        return



class FSMEngineBehaviour(FSMBehaviour):
    def setup(self):
        # Create states
        self.add_state(DECISION_MAKING,  EngineDecisionMakingState(), initial=True)
        self.add_state(PREPARE_OUTPUT, EnginePrepareOutputState())
        self.add_state(RUN_SIMULATION, EngineRunSimulationState())
        self.add_state(PREPARE_MEMORY, EnginePrepareMemoryState())

        # Create transitions
        self.add_transition(
            DECISION_MAKING, PREPARE_OUTPUT
        )
        self.add_transition(
            PREPARE_OUTPUT, RUN_SIMULATION
        )
        self.add_transition(
            RUN_SIMULATION, PREPARE_MEMORY
        )
        self.add_transition(
            PREPARE_MEMORY, DECISION_MAKING
        )


