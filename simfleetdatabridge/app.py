import json
import os
import re
import asyncio
import subprocess
import shutil
import functools
import time
import hashlib
from collections import defaultdict

from spade.agent import Agent
from spade.behaviour import OneShotBehaviour, State, FSMBehaviour

from simfleetdatabridge.llmbase import LlmBase
from simfleetdatabridge.utils import oneshot_request_llm
from simfleetdatabridge.planning import llm_agent_plan
from simfleetdatabridge.reflection import llm_agent_reflection

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
        self.actual_day = 0
        self.actual_week = None
        self.agent_used_actions = {}
        self.date_dict = {}
        self.agents_action = {}

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
        return {agent: {"short_memory": [], "long_memory": {"by_mode": {}, "by_pattern":{}}} for agent in profiles}


    def update_memory_with_simulation(self, sim_metrics):
        """Actualiza la memoria del agente con los datos de la simulación del día."""

        try:
            day_context = self.get_day_context()
        except Exception as e:
            logger.error(f"No se pudo obtener contexto del día actual: {e}")
            return

        fecha_info = {
            "day_number": day_context["day"],
            "day_text": day_context["day_name"],
            "mes": day_context["month_name"]
        }

        for category in ("LlmPedestrianAgent", "TaxiCustomerAgent"):
            for agent_data in sim_metrics.get("DetailedMetrics", {}).get(category, []):
                agent_name = agent_data["name"].split("@")[0]

                if agent_name not in self.get_agent_names():
                    continue

                trip_completion_timestamp = agent_data["trip_completion_timestamp"]
                trip_time = agent_data["trip_time"]
                waiting_time = agent_data["waiting_time"]
                transport_mode = agent_data["transport"]
                cost = agent_data["cost"]
                distance_km = agent_data["distance"] / 1000

                trip_completed = (
                        trip_completion_timestamp > 0.0 and
                        trip_time > 0.0 and
                        distance_km > 0.0
                )

                if trip_completed:
                    departure_time = self.real_seconds_to_scaled_time(
                        trip_completion_timestamp - trip_time - waiting_time
                    )
                    arrival_time = self.real_seconds_to_scaled_time(trip_completion_timestamp)
                    reason = "-"
                else:
                    last_action = self.agents_action.get(agent_name)
                    transport_mode = last_action["action_name"] if last_action else "unknown"
                    departure_time = last_action["departure_time"] if last_action else None
                    arrival_time = None
                    reason = (
                        f"Trip not completed: waited {round(waiting_time, 2)} min using '{transport_mode}'."
                    )

                was_late = self.is_delayed_arrival(agent_name, arrival_time)

                entry = {
                    "fecha": fecha_info,
                    "departure_time": departure_time,
                    "arrival_time": arrival_time,
                    "travel_time_min": round(trip_time, 2),
                    "waiting_time_min": round(waiting_time, 2),
                    "distance_km": distance_km,
                    "transport_mode": transport_mode,
                    "cost": cost,
                    "decision_context": {
                        "reason": reason,
                        "was_late": was_late,
                        "completed": trip_completed
                    }
                }

                self.memory.setdefault(agent_name, {"short_memory": [], "long_memory": {"by_pattern": {}}})
                self.short_memory_history.setdefault(agent_name, [])

                self.memory[agent_name]["short_memory"].append(entry)
                self.short_memory_history[agent_name].append(entry)


    def persist_memory_to_disk(self):
        """Guarda la short_memory_history y long_memory por separado."""

        base_path = Path(self.base_dir) / "agents"
        base_path.mkdir(parents=True, exist_ok=True)

        # Guardar short_memory_history (toda la historia episódica)
        memory_path = base_path / "memory.json"
        try:
            with memory_path.open("w") as f:
                json.dump(self.short_memory_history, f, indent=4)
            logger.info("Short memory history guardada en memory.json")
        except Exception as e:
            logger.error(f"Error al guardar short_memory_history: {e}")

        # Guardar solo la long_memory (resúmenes, patrones, reflexiones)
        long_memory_path = base_path / "long_memory.json"
        long_memory_data = {
            agent: self.memory[agent].get("long_memory", {})
            for agent in self.memory.keys()
        }

        try:
            with long_memory_path.open("w") as f:
                json.dump(long_memory_data, f, indent=4)
            logger.info("Long memory guardada en long_memory.json")
        except Exception as e:
            logger.error(f"Error al guardar long_memory: {e}")

    def archive_simulation_metrics(self):
        """Mueve simfleet_metrics.json al historial diario y lo elimina."""
        metrics_file = Path("simfleet_metrics.json")
        if not metrics_file.exists():
            logger.warning("No se encontró el archivo de métricas para archivar.")
            return

        destination_path = Path(self.base_dir) / "metrics/days" / f"{self.actual_day}_day_simfleet_metrics.json"
        destination_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copy(metrics_file, destination_path)
            metrics_file.unlink()
        except Exception as e:
            logger.error(f"Error al mover métricas a {destination_path}: {e}")

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

    # -------------------------- Patterns ----------------------------

    def generate_weekly_patterns(self, agent_name, similarity_threshold=0.15):
        """
        Genera patrones semanales de comportamiento para un agente específico.
        Agrupa por días, modos de transporte y ventanas de tiempo.
        Luego unifica patrones similares dentro del umbral definido.
        """

        current_week = self.get_current_week_name()
        current_week_days = [
            day_info for week, day_info in self.date_week if week == current_week
        ]
        valid_day_numbers = [day_info[0][1] for day_info in current_week_days]

        memory_entries = self.short_memory_history.get(agent_name, [])
        week_entries = [
            entry for entry in memory_entries
            if entry["fecha"]["day_number"] in valid_day_numbers and entry["decision_context"]["completed"]
        ]

        if not week_entries:
            logger.info(f"No hay entradas completadas para generar patrones en {agent_name}.")
            return

        pattern_groups = defaultdict(list)

        for entry in week_entries:
            hour = int(entry["departure_time"].split(":")[0])
            time_window = self.get_time_window(hour)

            key = (
                tuple([entry["fecha"]["day_text"]]),
                entry["fecha"]["mes"],
                time_window,
                entry["transport_mode"]
            )

            pattern_groups[key].append(entry)

        by_pattern = {}

        for key, entries in pattern_groups.items():
            day_names, month, time_window, mode = key
            pattern_id = self.hash_pattern_key((agent_name, key))

            total_travel = sum(e["travel_time_min"] for e in entries)
            total_wait = sum(e["waiting_time_min"] for e in entries)
            total_cost = sum(e["cost"] for e in entries)
            total_distance = sum(e["distance_km"] for e in entries)

            delays_occurred = sum(e["decision_context"]["was_late"] for e in entries)
            missed_destinations = sum(1 for e in entries if not e["decision_context"]["completed"])

            by_pattern[pattern_id] = {
                "pattern_id": pattern_id,
                "detection": {
                    "day_names": list(day_names),
                    "months": [month],
                    "time_window": {
                        "start": time_window[0],
                        "end": time_window[1]
                    },
                    "frequency": len(entries)
                },
                "behavior": {
                    "modes_used": [mode],
                    "avg_travel_time_min": round(total_travel / len(entries), 2),
                    "avg_waiting_time_min": round(total_wait / len(entries), 2),
                    "avg_cost": round(total_cost / len(entries), 2),
                    "avg_distance_km": round(total_distance / len(entries), 2)
                },
                "external_context": {
                    "common_situations": [],
                    "delays_occurred_days": delays_occurred,
                    "missed_destination_days": missed_destinations
                },
                "reflections": {
                    "summary": "-",
                    "adjustment": "-"
                }
            }

        self.memory[agent_name]["long_memory"]["by_pattern"] = by_pattern
        self.merge_similar_patterns(agent_name, similarity_threshold)

    def merge_similar_patterns(self, agent_name, similarity_threshold=0.15):
        """
        Unifica patrones similares dentro de 'long_memory["by_pattern"]' para un agente.
        Los patrones se consideran similares si comparten modo, ventana de tiempo, mes,
        y tienen métricas similares dentro del umbral.

        similarity_threshold: porcentaje de variación permitido (0.15 = 15%)
        """
        patterns = self.memory[agent_name]["long_memory"].get("by_pattern", {})
        merged = {}
        keys_seen = []

        def is_similar(p1, p2):
            if (
                    p1["detection"]["months"] != p2["detection"]["months"] or
                    p1["detection"]["time_window"] != p2["detection"]["time_window"] or
                    p1["behavior"]["modes_used"] != p2["behavior"]["modes_used"]
            ):
                return False

            def close(v1, v2):
                return abs(v1 - v2) / max(v1, v2, 0.001) <= similarity_threshold

            return all([
                close(p1["behavior"]["avg_travel_time_min"], p2["behavior"]["avg_travel_time_min"]),
                close(p1["behavior"]["avg_waiting_time_min"], p2["behavior"]["avg_waiting_time_min"]),
                close(p1["behavior"]["avg_cost"], p2["behavior"]["avg_cost"]),
                close(p1["behavior"]["avg_distance_km"], p2["behavior"]["avg_distance_km"]),
            ])

        for pid1, p1 in patterns.items():
            if pid1 in keys_seen:
                continue

            group = [p1]
            keys_seen.append(pid1)

            for pid2, p2 in patterns.items():
                if pid2 != pid1 and pid2 not in keys_seen and is_similar(p1, p2):
                    group.append(p2)
                    keys_seen.append(pid2)

            if len(group) == 1:
                merged[p1["pattern_id"]] = p1
                continue

            # Unir días, promedios y eventos
            merged_id = self.hash_pattern_key(
                (agent_name, group[0]["detection"]["time_window"], group[0]["behavior"]["modes_used"]))
            day_names = sorted(set(d for g in group for d in g["detection"]["day_names"]))
            frequency = sum(g["detection"]["frequency"] for g in group)

            merged_pattern = {
                "pattern_id": merged_id,
                "detection": {
                    "day_names": day_names,
                    "months": group[0]["detection"]["months"],
                    "time_window": group[0]["detection"]["time_window"],
                    "frequency": frequency
                },
                "behavior": {
                    "modes_used": group[0]["behavior"]["modes_used"],
                    "avg_travel_time_min": round(sum(
                        g["behavior"]["avg_travel_time_min"] * g["detection"]["frequency"] for g in group) / frequency,
                                                 2),
                    "avg_waiting_time_min": round(sum(
                        g["behavior"]["avg_waiting_time_min"] * g["detection"]["frequency"] for g in group) / frequency,
                                                  2),
                    "avg_cost": round(
                        sum(g["behavior"]["avg_cost"] * g["detection"]["frequency"] for g in group) / frequency, 2),
                    "avg_distance_km": round(
                        sum(g["behavior"]["avg_distance_km"] * g["detection"]["frequency"] for g in group) / frequency,
                        2)
                },
                "external_context": {
                    "common_situations": [],
                    "delays_occurred_days": sum(g["external_context"]["delays_occurred_days"] for g in group),
                    "missed_destination_days": sum(g["external_context"]["missed_destination_days"] for g in group)
                },
                "reflections": {
                    "summary": "-",
                    "adjustment": "-"
                }
            }

            merged[merged_id] = merged_pattern

        # Reemplazar patrones existentes con los fusionados
        self.memory[agent_name]["long_memory"]["by_pattern"] = merged

    # -------------------------- Patterns (Aux) ----------------------------
    def get_time_window(self, hour):
        if 6 <= hour < 9:
            return ("06:00 AM", "09:00 AM")
        elif 9 <= hour < 12:
            return ("09:00 AM", "12:00 PM")
        elif 12 <= hour < 17:
            return ("12:00 PM", "05:00 PM")
        elif 17 <= hour < 21:
            return ("05:00 PM", "09:00 PM")
        else:
            return ("09:00 PM", "06:00 AM")

    def hash_pattern_key(self, key):
        raw = "_".join(map(str, key))
        return hashlib.md5(raw.encode()).hexdigest()[:8]

    def is_delayed_arrival(self, agent_name, arrival_time_str):
        if not arrival_time_str:
            return False

        profile = self.get_agent_info(agent_name, "user_profile")
        if not profile:
            return False

        limit_time_str = profile.get("environment", {}).get("arrival_time_limit", {}).get("time", None)
        if not limit_time_str:
            return False

        try:
            fmt = "%I:%M %p"
            arrival_time = datetime.strptime(arrival_time_str, fmt)
            limit_time = datetime.strptime(limit_time_str, fmt)
            return arrival_time > limit_time
        except Exception as e:
            logger.warning(f"Error comparando arrival_time con limit_time para {agent_name}: {e}")
            return False

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

        date_dict = self.generate_date_dictionary("31/03/2025", "25/04/2025")
        self.group_dates_by_week(date_dict, ["Saturday", "Sunday"])

        self.update_total_days()
        self.count_days_per_week()

        # 1. Inicializar memoria si es necesario
        if not self.memory:
            self.memory = self.initialize_memory(self.get_agent_names())

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

    # --------------------- Pattern -------------------------


    def is_delayed_arrival(self, agent_name, arrival_time_str):
        """
        Compara la hora de llegada con el límite definido en el perfil del agente.
        Retorna True si el agente llegó tarde.
        """
        if not arrival_time_str:
            return False  # No llegó, pero eso se analiza por separado como "missed_destination"

        profile = self.get_agent_info(agent_name, "user_profile")
        if not profile:
            return False

        limit_time_str = profile.get("environment", {}).get("arrival_time_limit", {}).get("time", None)
        if not limit_time_str:
            return False

        try:
            fmt = "%I:%M %p"
            arrival_time = datetime.strptime(arrival_time_str, fmt)
            limit_time = datetime.strptime(limit_time_str, fmt)
            return arrival_time > limit_time
        except Exception as e:
            logger.warning(f"Error comparando arrival_time con limit_time para {agent_name}: {e}")
            return False



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


    def new_generate_travel_prompt(self, agent_id, agent_profile, agent_memory, task, steps):

        prompt = {
            agent_id: {
                "user_profile": agent_profile,
                "travel_memory": agent_memory,
                "instructions": {
                    "task": task,
                    "evaluation_steps": [
                        steps,
                        {
                            "step": len(steps+1),
                            "title": "Output Strict JSON",
                            "description": "Respond ONLY with a valid JSON that matches the required structure. DO NOT add any text, python code, explanation, or markdown."
                        }
                    ],
                    "output_requirements": {
                        "format": "**STRICT JSON ONLY**.",
                        "structure": {
                            "reflections": {
                                "summary": "Provide a summary of key reflections from historical data (long_memory), including insights from previous travel experiences.",
                                "adjustment": "Describe any suggested adjustments for future trips, particularly regarding time management and mode selection."
                            },
                            "next_day_decision": {
                                "suggested_departure_time": "HH:MM AM/PM",
                                "suggested_transport_mode": "Only modes included in 'transport_options'",
                                "reason": "Explain the reasoning behind the decision, referencing profile constraints, historical performance, and whether a new mode is being tested."
                            }
                        }
                    }
                }
            }
        }

        return json.dumps(prompt, indent=4)



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
                            "reflections": {
                                "summary": "Provide a summary of key reflections from historical data (long_memory), including insights from previous travel experiences.",
                                "adjustment": "Describe any suggested adjustments for future trips, particularly regarding time management and mode selection."
                            },
                            "next_day_decision": {
                                "suggested_departure_time": "HH:MM AM/PM",
                                "suggested_transport_mode": "Only modes included in 'transport_options'",
                                "reason": "Explain the reasoning behind the decision, referencing profile constraints, historical performance, and whether a new mode is being tested."
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
                "reflections": {
                    "summary": "-",
                    "adjustment": "-"
                },
                "next_day_decision": {
                    "suggested_departure_time": last_time,
                    "suggested_transport_mode": last_mode,
                    "reason": f"LLM response was invalid, empty, or failed parsing. Fallback logic used previous mode: {last_mode} of day {day}."
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
            "reason": llm_response["next_day_decision"]["reason"]
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
                "reflections": ["summary", "adjustment"],
                "next_day_decision": ["suggested_departure_time", "suggested_transport_mode", "reason"]
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
            transport_mode = decision["travel_plan"]["suggested_transport_mode"].lower()
            departure_time = decision["travel_plan"]["suggested_departure_time"]

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

    def get_next_day_plan(self, agent_name):
        """
        Devuelve el plan del día siguiente para un agente específico.
        """
        current_index = self.agent.index

        if current_index + 1 >= self.agent.total_days:
            return None  # Fin de calendario

        next_day_info = self.agent.date_week[current_index + 1]
        next_week = next_day_info[0]

        # CORREGIDO: Extraer el número de día de ("Wednesday", 2)
        try:
            next_day_number = str(next_day_info[1][0][1])  # <- día numérico
            logger.debug(f"Intentando obtener plan para {agent_name} - {next_week} día {next_day_number}")
            next_day_plan = self.agent.plan[agent_name][next_week]["days"][next_day_number]
            return next_day_plan
        except KeyError:
            logger.warning(f"No hay plan registrado para {agent_name} en {next_week}, día {next_day_number}.")
            return None

    def save_travel_plan(self, agent_name, plan):

        if not hasattr(self.agent, "plan") or self.agent.plan is None:
            self.agent.plan = {}

        self.agent.plan[agent_name] = {}
        aux_index = self.agent.index  # Índice auxiliar que no altera self.index

        for day_plan in plan["travel_plan"]["days"]:
            if aux_index >= len(self.agent.date_week):
                break  # Evitar desbordamiento

            week, [(day_name, day), (month_name, month), year] = self.agent.date_week[aux_index]

            if week not in self.agent.plan[agent_name]:
                self.agent.plan[agent_name][week] = {
                    "reason": plan["travel_plan"]["reason"],
                    "days": {}
                }

            self.agent.plan[agent_name][week]["days"][str(day)] = {
                "travel": day_plan,
                "date_context": {
                    "week": week,
                    "day": day,
                    "day_name": day_name,
                    "month": month,
                    "month_name": month_name,
                    "year": year
                }
            }

            aux_index += 1  # Avanzamos solo el índice auxiliar


    def set_agent_action_for_today(self, agent_name):
        if not hasattr(self.agent, "agents_action"):
            self.agent.agents_action = {}

        # Paso 1: obtener el contexto del día actual
        day_context = self.agent.get_day_context()
        week = day_context["week"]
        day = str(day_context["day"])  # la clave en el plan es string

        # Paso 2: obtener el plan para el día actual
        try:
            today_plan = self.agent.plan[agent_name][week]["days"][day]
            suggested_transport_mode = today_plan["travel"]["suggested_transport_mode"]
            suggested_departure_time = today_plan["travel"]["suggested_departure_time"]
        except KeyError:
            logger.error(f"No se encontró plan para el agente '{agent_name}' en el día {day} de la semana '{week}'")

        # Paso 3: obtener configuración de acción para ese modo de transporte
        if suggested_transport_mode not in self.agent.actions:
            logger.error(f"Modo de transporte '{suggested_transport_mode}' no está definido en self.agent.actions")

        action_data = self.agent.actions[suggested_transport_mode]

        # Paso 4: asignar configuración a agents_action
        self.agent.agents_action[agent_name] = {
            "action_name": suggested_transport_mode,
            "class_path": action_data["class_path"],
            "strategy_path": action_data["strategy_path"],
            "departure_time": suggested_departure_time
        }

    def reset_all_agents_actions(self):
        """
        Elimina todas las acciones configuradas previamente para los agentes.
        """
        self.agent.agents_action = {}

    # ---------------------- Memory state --------------------------

    def load_simulation_metrics(self):
        metrics_file = Path('simfleet_metrics.json')
        if not metrics_file.exists():
            logger.error("El archivo simfleet_metrics.json no existe.")
            return None

        try:
            with metrics_file.open('r') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Error al parsear JSON: {e}")
            return None

    def store_llm_decision(self, agent_name, reflection):
        context = reflection.get("decision_context", {})
        suggested_mode = context.get("suggested_transport_mode")
        suggested_departure = context.get("suggested_departure_time")

        # Reemplazar el campo "reason" por la reflexión del LLM
        try:
            last_entry = self.agent.memory[agent_name]["short_memory"][-1]
            last_entry["decision_context"]["reason"] = context.get("reflection", "-")
            logger.debug(f"Reflexión añadida a short_memory de {agent_name}")
        except Exception as e:
            logger.warning(f"No se pudo añadir reflexión a short_memory de {agent_name}: {e}")

        # Guardar acción si corresponde
        if suggested_mode and suggested_departure:
            action_data = self.agent.actions.get(suggested_mode)
            if action_data:
                self.agent.agents_action[agent_name] = {
                    "action_name": suggested_mode,
                    "class_path": action_data["class_path"],
                    "strategy_path": action_data["strategy_path"],
                    "departure_time": suggested_departure
                }
                logger.info(f"Acción asignada a {agent_name}: {suggested_mode} a las {suggested_departure}")
            else:
                logger.warning(f"Modo '{suggested_mode}' no reconocido para {agent_name}")
        else:
            logger.info(f"No se asignó acción para {agent_name} (último día de la semana o sin decisión)")


    def store_weekly_summary_or_patterns(self, agent_name, reflection):
        summary = reflection.get("weekly_pattern_summary")
        if summary:
            self.agent.memory[agent_name]["long_memory"].setdefault("weekly_reflections", []).append({
                "week": self.agent.get_current_week_name(),
                "summary": summary
            })
            logger.info(f"Resumen semanal guardado para {agent_name}")
        else:
            try:
                self.agent.generate_weekly_patterns(agent_name)
                self.agent.merge_similar_patterns(agent_name)
                logger.info(f"Patrones generados para {agent_name}")
            except Exception as e:
                logger.error(f"Error al generar patrones para {agent_name}: {e}")

    def get_weekly_reflections_dict(self, agent_name):
        """
        Devuelve un diccionario con los nombres de semana como claves
        y el contenido de los resúmenes como valores.

        Ejemplo:
        {
            "week_1": "Contenido del summary 1",
            "week_2": "Contenido del summary 2"
        }
        """
        result = {}

        try:
            weekly_reflections = self.agent.memory[agent_name]["long_memory"].get("weekly_reflections", [])
            for entry in weekly_reflections:
                week = entry.get("week")
                summary = entry.get("summary")
                if week and summary:
                    result[week] = summary
        except KeyError:
            logger.warning(f"No se encontró memoria para el agente {agent_name}.")
        except Exception as e:
            logger.error(f"Error al obtener weekly_reflections para {agent_name}: {e}")

        return result

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

        if not self.agent.has_next_day():
            logger.success("[DecisionMaking] Simulation finished successfully.")
            self.agent.stopped = True

        current_week = self.agent.get_current_week_name()
        current_day = self.agent.get_current_day()
        self.agent.actual_week = current_week
        #self.agent.actual_day = current_day

        decision_file = os.path.join(
            self.agent.base_dir, "agents/decisions", f"{current_week}_decisions.json"
        )

        # Check if it's the beginning of the week
        is_first_day_of_week = self.agent.is_first_day_of_current_week()

        if is_first_day_of_week or not os.path.exists(decision_file):
            logger.info(f"[DecisionMaking] Beginning of the week detected: {current_week}")
            logger.info(f"[DecisionMaking] Generating plans for all agents...")

            week_decisions = {}

            for agent_name in self.agent.profiles.keys():
                profile = self.agent.get_agent_info(agent_name)
                past_memory = self.agent.get_agent_memory_info(agent_name)

                # Intentamos obtener patrones semanales previos
                patterns_dict = self.get_weekly_reflections_dict(agent_name)

                # Solo añadimos "patterns" si hay algo real que analizar
                if patterns_dict:
                    profile["patterns"] = patterns_dict

                days_in_week = self.agent.get_days_in_week(current_week)
                forced_week = current_week == "week_1"

                #logger.warning(f"DEBUG: Days in week:({days_in_week}). Current week: ({current_week}). Week: ({self.agent.summary_week})")

                plan = await llm_agent_plan(
                    self.agent,
                    profile=profile,
                    forced_week=forced_week,
                    profile_description=True,
                    days=days_in_week
                )

                self.save_travel_plan(agent_name, plan)
                self.set_agent_action_for_today(agent_name)
                week_decisions[agent_name] = plan

            Path(decision_file).parent.mkdir(parents=True, exist_ok=True)
            with open(decision_file, "w") as f:
                json.dump(week_decisions, f, indent=4)

            logger.info(f"[DecisionMaking] Weekly plans saved at: {decision_file}")

        else:
            logger.info(f"[DecisionMaking] Mid-week day: {current_week}")
            logger.info(f"[DecisionMaking] Updating daily actions for agents...")

            #for agent_name in self.agent.profiles.keys():
            #    self.set_agent_action_for_today(agent_name)

        logger.info("[DecisionMaking] Decision process completed for the current day.")

        if self.agent.agents_action:
            self.set_next_state(PREPARE_OUTPUT)
            return

        return


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

        actual_day = self.agent.actual_day + 1

        end_path = os.path.join(simfleet_path, str(actual_day) + "_day_" + name)
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
        logger.debug(f"{self.agent.jid} in Prepare memory State")

    async def run(self):
        """Orquesta la preparación de la memoria de todos los agentes."""

        # 1. Inicializar memoria si es necesario
        if not self.agent.memory:
            self.agent.memory = self.agent.initialize_memory(self.agent.get_agent_names())

        # 2. Cargar métricas
        metrics = self.load_simulation_metrics()
        if not metrics:
            logger.error("No se pudo cargar simfleet_metrics.json. Abortando actualización de memoria.")
            return

        # 3. Actualizar memoria con datos del día
        self.agent.update_memory_with_simulation(metrics)

        #self.agent.reset_all_agents_actions()
        self.agent.agents_action = {}

        # 4. Determinar si es el último día de la semana
        is_last_day = self.agent.is_last_day_of_current_week()

        # 5. Procesar cada agente
        for agent_name in self.agent.profiles.keys():
            try:
                next_plan_day = self.get_next_day_plan(agent_name)
                memory = self.agent.get_agent_memory_info(agent_name)
                profile = self.agent.get_agent_info(agent_name)

                # 6. Reflexión diaria o semanal
                reflection = await llm_agent_reflection(
                    self.agent,
                    profile=profile,
                    memory=memory,
                    next_day_plan=next_plan_day,
                    last_day_week=is_last_day
                )

                # 7. Guardar reflexión y decisión (si existe)
                self.store_llm_decision(agent_name, reflection)

                # 8. Si es el último día, guardar resumen o generar patrones
                if is_last_day:
                    self.store_weekly_summary_or_patterns(agent_name, reflection)

            except Exception as e:
                logger.error(f"Error procesando reflexión para {agent_name}: {e}")

        # 9. Persistir memoria y archivar métricas
        self.agent.persist_memory_to_disk()
        self.agent.archive_simulation_metrics()

        if is_last_day:
            for agent_name in self.agent.profiles.keys():
                # Opcional: respaldar short memory en el historial (ya se hace, así que esto puede omitirse)
                self.agent.memory[agent_name]["short_memory"] = []
                logger.info(f"Short memory limpiada para {agent_name} después de consolidación semanal.")

        #if self.agent.has_next_day():

        self.agent.advance()
        # self.agent.actual_day = day + 1
        self.agent.actual_day = self.agent.index

        # 10. Transición
        self.set_next_state(DECISION_MAKING)
        return
        #else:
        #    logger.success("[DecisionMaking] Simulation finished successfully.")
        #    self.agent.stopped = True



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


