import requests
from loguru import logger
import json
import os


class LlmBase:
    # Definimos los nombres de los archivos usados en el sistema
    PROFILE_FILE = "LlmDecisionMaking/Agents/profiles.json"
    MEMORY_FILE = "LlmDecisionMaking/Agents/memory.json"
    ACTIONS_FILE = "LlmDecisionMaking/Agents/actions.json"
    DECISIONS_FILE = "LlmDecisionMaking/Agents/decisions/1_day_decisions.json"
    LLM_CONFIG = "LlmDecisionMaking/llm_config.json"

    def __init__(self):
        """
        Initializes the LlmMixin with default structures for agent data.
        """
        # Colective parameters
        self.profiles = {}
        self.environment = {}
        self.memory = {}
        self.decisions = {}
        self.actions = {}

        # Individual parameters
        self.persona = {}
        self.personal_environment = {}
        self.personal_memory = {}
        self.personal_decisions = {}

        # Agent connection LLM (same connection)
        self.session = requests.Session()

    @staticmethod
    def _load_json_file(file_path):
        """
        Loads a JSON file and returns its content.
        If the file does not exist or is invalid, logs an error and returns an empty dictionary.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                data = json.load(file)
                logger.info(f"Successfully loaded {file_path}")
                return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            logger.error(f"Error: {file_path} was not found.")
        except json.JSONDecodeError:
            logger.error(f"Error: {file_path} does not have a valid JSON format.")
        except Exception as e:
            logger.exception(f"Unexpected error while loading {file_path}: {e}")
        return {}

    def load_agent_profiles(self):
        """
        Loads agent profiles from the profiles.json file.
        """
        self.profiles = self._load_json_file(self.PROFILE_FILE)

    def get_number_of_agents(self):
        """
        Returns the number of agent profiles loaded.
        """
        return len(self.profiles)

    def get_agent_names(self):
        """
        Returns a list of agent names (keys) from the profiles.
        """
        return list(self.profiles.keys())

    def get_agent_info(self, agent_name, key=None):
        """
        Returns the content of a specific key for a given agent.
        If the key is not provided, returns the full agent profile.
        """
        agent_data = self.profiles.get(agent_name)
        if agent_data is None:
            logger.warning(f"Agent '{agent_name}' not found.")
            return None
        return agent_data if key is None else agent_data.get(key, None)

    ######################## Memory #########################

    def load_memory(self):
        """
        Loads the agent's memory from the memory.json file.
        """
        self.memory = self._load_json_file(self.MEMORY_FILE)

    def get_agent_memory_info(self, agent_name):
        """
        Returns the memory data for a given agent.
        """
        return self.memory.get(agent_name, {})

    def load_json_conf(self, path):

        return self._load_json_file(path)


    ######################## LLM Connection #########################

    def load_llm_connection(self):
        """
        Loads LLM connection data from a specified JSON file.
        """
        return self._load_json_file(self.LLM_CONFIG)

    ######################## Actions #########################

    def load_actions(self):
        """
        Loads available actions from the actions.json file.
        """
        self.actions = self._load_json_file(self.ACTIONS_FILE)

    ######################## Decisions #########################

    def load_decisions(self):
        """
        Loads previous decisions from the decisions.json file.
        """
        self.decisions = self._load_json_file(self.DECISIONS_FILE)


    ######################### Escala Hora Simulacion ##############################

    def seconds_to_scaled_time(self, seconds: int) -> str:
        """
        Converts real seconds to scaled time (HH:MM).

        1 real second = 1 scaled minute
        60 real seconds = 1 scaled hour
        1440 real seconds = 24 scaled hours (1 full scaled day)

        Parameters:
            seconds (int): Number of real seconds to convert.

        Returns:
            str: Scaled time in 'HH:MM' format.
        """
        scaled_minutes = seconds  # Each real second equals 1 scaled minute
        hours = (scaled_minutes // 60) % 24  # Keep the format within 24 hours
        minutes = scaled_minutes % 60
        return f"{hours:02}:{minutes:02}"

    def scaled_time_to_seconds(self, scaled_time: str) -> int:
        """
        Converts a scaled time (HH:MM) to real seconds.

        1 scaled minute = 1 real second
        1 scaled hour = 60 real seconds
        24 scaled hours = 1440 real seconds (1 full scaled day)

        Parameters:
            scaled_time (str): Scaled time in 'HH:MM' format.

        Returns:
            int: Equivalent time in real seconds.
        """
        hours, minutes = map(int, scaled_time.split(":"))
        scaled_minutes = (hours * 60) + minutes  # Convert to total scaled minutes
        real_seconds = scaled_minutes  # 1 scaled minute = 1 real second
        return real_seconds
