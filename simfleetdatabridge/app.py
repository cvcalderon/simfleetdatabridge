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
        self.simfleet_backup = None

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
        """Initialize the memory if it is empty."""
        return {agent: {"short_memory": [], "long_memory": {"by_mode": {}, "by_pattern":{}}} for agent in profiles}


    def update_memory_with_simulation(self, sim_metrics):
        """Update the agent’s memory with the data from today’s simulation."""

        try:
            day_context = self.get_day_context()
        except Exception as e:
            logger.error(f"Could not retrieve context from the current day: {e}")
            return

        fecha_info = {
            "day_number": day_context["day"],
            "day_text": day_context["day_name"],
            "mes": day_context["month_name"]
        }

        for category in ("LlmPedestrianAgent", "TaxiCustomerAgent", "BusCustomerAgent"):
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
                    "travel_time_min": round(trip_time / self.scale_ratio, 2),
                    "waiting_time_min": round(waiting_time / self.scale_ratio, 2),
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
        """Save the short_memory_history and long_memory separately."""

        base_path = Path(self.base_dir) / "agents"
        base_path.mkdir(parents=True, exist_ok=True)

        # Save short_memory_history (the entire episodic history).
        memory_path = base_path / "memory.json"
        try:
            with memory_path.open("w") as f:
                json.dump(self.short_memory_history, f, indent=4)
            logger.info("Short memory history saved in memory.json")
        except Exception as e:
            logger.error(f"Error saving short_memory_history: {e}")

        # Save only the long_memory (summaries, patterns, reflections)
        long_memory_path = base_path / "long_memory.json"
        long_memory_data = {
            agent: self.memory[agent].get("long_memory", {})
            for agent in self.memory.keys()
        }

        try:
            with long_memory_path.open("w") as f:
                json.dump(long_memory_data, f, indent=4)
            logger.info("Long memory saved in long_memory.json")
        except Exception as e:
            logger.error(f"Error saving long_memory: {e}")

    def archive_simulation_metrics(self):
        """Move simfleet_metrics.json to the daily history and delete it."""
        metrics_file = Path("simfleet_metrics.json")
        if not metrics_file.exists():
            logger.warning("Metrics file not found for archiving.")
            return

        destination_path = Path(self.base_dir) / "metrics/days" / f"{self.actual_day}_day_simfleet_metrics.json"
        destination_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copy(metrics_file, destination_path)
            metrics_file.unlink()
        except Exception as e:
            logger.error(f"Error moving metrics to {destination_path}: {e}")


    # -------------------------- Patterns ----------------------------

    def generate_weekly_patterns(self, agent_name, similarity_threshold=0.15):
        """
        Generate weekly behavior patterns for a specific agent.
        Group by days, modes of transportation, and time windows.
        Then merge similar patterns within the defined threshold.
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
            logger.info(f"No completed entries to generate patterns in {agent_name}.")
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
        Merge similar patterns within 'long_memory["by_pattern"]' for an agent.
        Patterns are considered similar if they share mode, time window, month,
        and have similar metrics within the threshold.

        similarity_threshold: allowed variation percentage (0.15 = 15%)
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

            # Merge days, averages, and events
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

        # Replace existing patterns with the merged ones
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

            res = arrival_time > limit_time

            logger.warning(f"DEBUG: arrival_time: {arrival_time} > limit_time: {limit_time} = {res}")

            return arrival_time > limit_time
        except Exception as e:
            logger.warning(f"Error comparing arrival_time with limit_time for {agent_name}: {e}")
            return False

    async def setup(self):
        """
        Setup method executed when the agent starts.
        Loads profiles and memory from JSON files.
        """

        #New simulation
        self.load_framework_config(self.config) # Load framework config - actions + llm
        self.load_agent_profiles()
        self.load_memory()
        self.set_time_scale(4.3)
        self.scale_range_time(
            start_time_day=self.environment.get("start_time_day"),
            end_time_day=self.environment.get("end_time_day")
        )

        date_dict = self.generate_date_dictionary("31/03/2025", "25/04/2025")
        self.group_dates_by_week(date_dict, ["Saturday", "Sunday"])

        self.update_total_days()
        self.count_days_per_week()

        self.build_event_index()

        # 1. Initialize memory if necessary.
        if not self.memory:
            self.memory = self.initialize_memory(self.get_agent_names())

    async def run(self):
        """
        Starts the engine
        """

        engine_run = FSMEngineBehaviour()
        self.add_behaviour(engine_run)


class EngineBehaviour(State):

    async def on_start(self):
        """
            Logs the start of the agent behaviour
        """
        logger.debug("Strategy {} started in Engine".format(type(self).__name__))

    # --------------------- Pattern -------------------------

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
                clean_name = match.group(2)  # Part of the name without the number of days and "day"
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


    def get_next_day_plan(self, agent_name):
        """
        Return the next day's plan for a specific agent.
        """
        current_index = self.agent.index

        if current_index + 1 >= self.agent.total_days:
            return None  # Fin de calendario

        next_day_info = self.agent.date_week[current_index + 1]
        next_week = next_day_info[0]

        # CORRECTED: Extract the day number from ("Wednesday", 2)
        try:
            next_day_number = str(next_day_info[1][0][1])  # <- día numérico
            logger.debug(f"Attempting to get plan for {agent_name} - {next_week} day {next_day_number}")
            next_day_plan = self.agent.plan[agent_name][next_week]["days"][next_day_number]
            return next_day_plan
        except KeyError:
            logger.warning(f"No plan registered for {agent_name} on {next_week}, day {next_day_number}.")
            return None

    def save_travel_plan(self, agent_name, plan):

        if not hasattr(self.agent, "plan") or self.agent.plan is None:
            self.agent.plan = {}

        self.agent.plan[agent_name] = {}
        aux_index = self.agent.index  # Auxiliary index that does not modify self.index

        for day_plan in plan["travel_plan"]["days"]:
            if aux_index >= len(self.agent.date_week):
                break  # Prevent overflow

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

            aux_index += 1  # We only advance the auxiliary index.


    def set_agent_action_for_today(self, agent_name):
        if not hasattr(self.agent, "agents_action"):
            self.agent.agents_action = {}

        # Step 1: Get the context of the current day.
        day_context = self.agent.get_day_context()
        week = day_context["week"]
        day = str(day_context["day"])

        # Step 2: Get the plan for the current day.
        try:
            today_plan = self.agent.plan[agent_name][week]["days"][day]
            suggested_transport_mode = today_plan["travel"]["suggested_transport_mode"].lower()
            suggested_departure_time = today_plan["travel"]["suggested_departure_time"]
        except KeyError:
            logger.error(f"No plan found for the agent '{agent_name}' in the day {day} of the week '{week}'")

        # Step 3: Get action configuration for that mode of transportation.
        if suggested_transport_mode not in self.agent.actions:
            logger.error(f"Transport mode '{suggested_transport_mode}' is not defined in self.agent.actions")

        action_data = self.agent.actions[suggested_transport_mode]

        # Step 4: Assign configuration to agents_action.
        self.agent.agents_action[agent_name] = {
            "action_name": suggested_transport_mode,
            "class_path": action_data["class_path"],
            "strategy_path": action_data["strategy_path"],
            "departure_time": suggested_departure_time,
            "line": action_data["line"],
            "speed": action_data["speed"]
        }

    # ---------------------- Memory state --------------------------

    def load_simulation_metrics(self):
        metrics_file = Path('simfleet_metrics.json')
        if not metrics_file.exists():
            logger.error("The file simfleet_metrics.json does not exist.")
            return None

        try:
            with metrics_file.open('r') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON: {e}")
            return None

    def store_llm_decision(self, agent_name, reflection):
        context = reflection.get("decision_context", {})
        suggested_mode = context.get("suggested_transport_mode").lower()
        suggested_departure = context.get("suggested_departure_time")

        # Replace the "reason" field with the LLM’s reflection.
        try:
            last_entry = self.agent.memory[agent_name]["short_memory"][-1]
            last_entry["decision_context"]["reason"] = context.get("reflection", "-")
            logger.debug(f"Reflection added to short_memory of {agent_name}")
        except Exception as e:
            logger.warning(f"Could not add reflection to short_memory of {agent_name}: {e}")

        # Save action if applicable.
        if suggested_mode and suggested_departure:
            action_data = self.agent.actions.get(suggested_mode)
            if action_data:
                self.agent.agents_action[agent_name] = {
                    "action_name": suggested_mode,
                    "class_path": action_data["class_path"],
                    "strategy_path": action_data["strategy_path"],
                    "departure_time": suggested_departure,
                    "line": action_data["line"],
                    "speed": action_data["speed"]
                }
                logger.info(f"Action assigned to {agent_name}: {suggested_mode} to the {suggested_departure}")
            else:
                logger.warning(f"Mode '{suggested_mode}' not recognized for {agent_name}")
        else:
            logger.info(f"No action assigned for {agent_name} (last day of the week or no decision)")


    def store_weekly_summary_or_patterns(self, agent_name, reflection):
        summary = reflection.get("weekly_pattern_summary")
        if summary:
            self.agent.memory[agent_name]["long_memory"].setdefault("weekly_reflections", []).append({
                "week": self.agent.get_current_week_name(),
                "summary": summary
            })
            logger.info(f"Weekly summary saved for {agent_name}")
        else:
            try:
                self.agent.generate_weekly_patterns(agent_name)
                self.agent.merge_similar_patterns(agent_name)
                logger.info(f"Patterns generated for {agent_name}")
            except Exception as e:
                logger.error(f"Error generating patterns for {agent_name}: {e}")

    def get_weekly_reflections_dict(self, agent_name):
        """
        Returns a dictionary with week names as keys
        and the contents of the summaries as values.

        Example:
        {
        "week_1": "Contents of summary 1",
        "week_2": "Contents of summary 2"
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
            logger.warning(f"No memory found for the agent {agent_name}.")
        except Exception as e:
            logger.error(f"Error getting weekly_reflections for {agent_name}: {e}")

        return result

    #--------------------- Transports backup (taxis) -----------------------------

    def ensure_original_backup(self, simfleet_path: Path):
        if getattr(self.agent, "simfleet_backup", None) is not None:
            return  # Already in memory.

        # Search for file 0_day_*.json as the original source.
        for file in os.listdir(simfleet_path):
            if re.match(r"0_day_.*\.json", file):
                zero_day_path = simfleet_path / file
                logger.info(f"[Backup] Loading backup from '{file}' (day 0).")
                with open(zero_day_path, "r") as f:
                    self.agent.simfleet_backup = json.load(f)
                return

        logger.warning("[Backup] File '0_day_*.json' not found. Could not create backup.")

    def restore_taxis_from_backup(self, sim_config):
        backup = getattr(self.agent, "simfleet_backup", None)
        if not backup:
            logger.warning("[TaxiRestore] No backup in memory to restore taxis.")
            return

        original_taxis = [t for t in backup.get("transports", []) if t.get("fleet_type") == "taxi"]
        other_transports = [t for t in sim_config.get("transports", []) if t.get("fleet_type") != "taxi"]
        sim_config["transports"] = original_taxis + other_transports

        logger.info(f"[TaxiRestore] Restored {len(original_taxis)} taxis from backup.")

    def apply_strike_taxi_filter(self, sim_config):
        events_today = self.agent.get_events_for_today()

        # Get original taxis from the backup (not from the previous day's sim_config).
        backup = getattr(self.agent, "simfleet_backup", None)
        if not backup:
            logger.warning("[TaxiFilter] No backup available. No filtering applied.")
            return

        original_taxis = [t for t in backup.get("transports", []) if t.get("fleet_type") == "taxi"]
        other_transports = [t for t in sim_config.get("transports", []) if t.get("fleet_type") != "taxi"]

        if not events_today:
            logger.info("[TaxiFilter] No events: restoring taxis from backup.")
            sim_config["transports"] = original_taxis + other_transports
            return

        taxi_strike = next(
            (e for e in events_today
             if e.get("category") == "transport"
             and e.get("subtype") == "strike"
             and e.get("details", {}).get("transport_type") == "taxi"),
            None
        )

        if not taxi_strike:
            logger.info("[TaxiFilter] No taxi strike. Restoring taxis from backup.")
            sim_config["transports"] = original_taxis + other_transports
            return

        affected_ratio = taxi_strike["details"].get("affected_ratio", 0.0)
        keep_count = max(1, int(len(original_taxis) * (1 - affected_ratio)))
        logger.info(f"[TaxiFilter] Strike active. Active taxis: {keep_count}/{len(original_taxis)}")
        sim_config["transports"] = original_taxis[:keep_count] + other_transports

    async def run(self):
        """
            Abstract method that should be implemented in subclasses. This is where the specific strategy of the
            agent will be executed.
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

                # Attempting to retrieve previous weekly patterns.
                patterns_dict = self.get_weekly_reflections_dict(agent_name)

                # Only add "patterns" if there is something real to analyze.
                if patterns_dict:
                    profile["patterns"] = patterns_dict

                days_in_week = self.agent.get_days_in_week(current_week)
                forced_week = current_week == "week_1"

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

        logger.info("[DecisionMaking] Decision process completed for the current day.")

        if self.agent.agents_action:
            self.set_next_state(PREPARE_OUTPUT)
            return

        return


class EnginePrepareOutputState(EngineBehaviour):
    async def on_start(self):
        await super().on_start()
        self.agent.status = PREPARE_OUTPUT
        logger.debug(f"{self.agent.jid} in Prepare output State")

    async def run(self):
        simfleet_path = Path(self.agent.base_dir) / "config/simfleet"

        # 1. Load configuration from the last day (may be reduced due to previous strike).
        day, name, sim_config = self.load_latest_simfleet_config(simfleet_path)

        # 2. Create backup in memory from 0_day_*.json (only once).
        self.ensure_original_backup(simfleet_path)

        # 3. Apply agents' decisions.
        decisions = self.agent.agents_action
        for customer in sim_config.get("customers", []):
            customer_name = customer.get("name")
            decision = decisions.get(customer_name)

            if not decision:
                logger.warning(f"Warning: No decision for the client {customer_name}.")
                continue

            dep_time = decision.get("departure_time", customer.get("delay"))
            if dep_time:
                customer["delay"] = self.agent.scaled_time_to_real_seconds(str(dep_time))

            customer["class"] = decision.get("class_path", customer.get("class"))
            customer["strategy"] = decision.get("strategy_path", customer.get("strategy"))
            customer["fleet_type"] = decision.get("action_name", customer.get("action_name"))
            customer["speed"] = decision.get("speed", customer.get("speed"))
            customer["line"] = decision.get("line", customer.get("line"))

        # 4. Apply taxi strike if applicable (based on original backup).
        self.apply_strike_taxi_filter(sim_config)

        # 5. General simulation parameterization.
        sim_config["max_time"] = self.agent.get_real_seconds_range()
        sim_config["mobility_metrics"] = "simfleetdatabridge.actions.metrics.control.AgentsMobilityClass"

        # 6. Save the output file for the new day.
        actual_day = self.agent.actual_day + 1
        end_path = simfleet_path / f"{actual_day}_day_{name}"
        if end_path.exists():
            logger.debug(f"The file for the day {day} already exists.")
        self.agent.path = end_path

        with open(end_path, 'w') as f:
            json.dump(sim_config, f, indent=4)

        self.set_next_state(RUN_SIMULATION)

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
        """Orchestrate the memory preparation for all agents."""

        # 1. Initialize memory if necessary
        if not self.agent.memory:
            self.agent.memory = self.agent.initialize_memory(self.agent.get_agent_names())

        # 2. Load metrics.
        metrics = self.load_simulation_metrics()
        if not metrics:
            logger.error("Could not load simfleet_metrics.json. Aborting memory update.")
            return

        # 3. Update memory with data from the day.
        self.agent.update_memory_with_simulation(metrics)

        #self.agent.reset_all_agents_actions()
        self.agent.agents_action = {}

        # 4. Determine if it is the last day of the week.
        is_last_day = self.agent.is_last_day_of_current_week()

        special_events = self.agent.get_events_for_today()

        # 5. Process each agent.
        for agent_name in self.agent.profiles.keys():
            try:
                next_plan_day = self.get_next_day_plan(agent_name)
                memory = self.agent.get_agent_memory_info(agent_name)
                profile = self.agent.get_agent_info(agent_name)

                # 6. Daily or weekly reflection.
                reflection = await llm_agent_reflection(
                    self.agent,
                    profile=profile,
                    memory=memory,
                    next_day_plan=next_plan_day,
                    last_day_week=is_last_day,
                    special_events= special_events
                )

                # 7. Save reflection and decision (if available).
                self.store_llm_decision(agent_name, reflection)

                # 8. If it is the last day, save summary or generate patterns.
                if is_last_day:
                    self.store_weekly_summary_or_patterns(agent_name, reflection)

            except Exception as e:
                logger.error(f"Error processing reflection for {agent_name}: {e}")

        # 9. Persist memory and archive metrics.
        self.agent.persist_memory_to_disk()
        self.agent.archive_simulation_metrics()

        if is_last_day:
            for agent_name in self.agent.profiles.keys():
                # Optional: back up short memory to history (already done, so this can be omitted).
                self.agent.memory[agent_name]["short_memory"] = []
                logger.info(f"Short memory cleared for {agent_name} after weekly consolidation.")

        #if self.agent.has_next_day():

        self.agent.advance()
        # self.agent.actual_day = day + 1
        self.agent.actual_day = self.agent.index

        # 10. Transition
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


