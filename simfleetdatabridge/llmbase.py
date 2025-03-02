import requests
from loguru import logger
import json
import os


class LlmBase:
    """
    Base class for agents that interact with an LLM.
    Provides methods to load agent profiles, memory, and decisions.
    """

    def __init__(self, sim_path):
        """
        Initializes LlmBase with the simulation base path.
        """
        self.sim_path = sim_path  # Base simulation directory

        # Data structures
        self.profiles = {}
        self.memory = {}
        self.decisions = {}

        # LLM configuration
        self.model_config = {}
        self.actions = {}

        # Session for LLM connection #TEST
        self.session = requests.Session()

    def _load_json_file(self, file_path):
        """
        Loads a JSON file and returns its content.
        If the file is missing or has an invalid format, returns an empty dictionary.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                data = json.load(file)
                logger.info(f"Successfully loaded file: {file_path}")
                return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            logger.error(f"Error: File not found: {file_path}.")
        except json.JSONDecodeError:
            logger.error(f"Error: Invalid JSON format in {file_path}.")
        except Exception as e:
            logger.exception(f"Unexpected error while loading {file_path}: {e}")
        return {}

########################## Config #############################

    def load_framework_config(self, config_path: str):
        """
        Loads the framework configuration from a JSON file and stores it in class variables.

        :param config_path: Path to the framework configuration JSON file.
        """
        config_data = self._load_json_file(config_path)
        if not config_data:
            logger.error("Failed to load framework configuration.")
            return

        # Store configuration in class variables
        self.model_config = config_data.get("model_config", {})
        self.actions_config = config_data.get("actions", {})

        logger.info("Framework configuration successfully loaded.")
        logger.info(f"Model Configuration: {self.model_config}")
        logger.info(f"Actions Configuration: {self.actions_config}")

########################## Profiles ###########################

    def load_agent_profiles(self):
        """Loads agent profiles from the respective JSON file."""
        profile_file = os.path.join(self.sim_path, "agents/profiles.json")
        self.profiles = self._load_json_file(profile_file)

    def get_number_of_agents(self):
        """Returns the number of agents loaded in profiles."""
        return len(self.profiles)

    def get_agent_names(self):
        """Returns a list of agent names."""
        return list(self.profiles.keys())

    def get_agent_info(self, agent_name, key=None):
        """Returns the information of a specific agent."""
        agent_data = self.profiles.get(agent_name)
        if agent_data is None:
            logger.warning(f"Agent '{agent_name}' not found.")
            return None
        return agent_data if key is None else agent_data.get(key, None)

    ######################## Memory #########################

    def load_memory(self):
        """Loads agent memory from the respective JSON file."""
        memory_file = os.path.join(self.sim_path, "agents/memory.json")
        self.memory = self._load_json_file(memory_file)

    def get_agent_memory_info(self, agent_name):
        """Returns memory information for a specific agent."""
        return self.memory.get(agent_name, {})

    def load_json_conf(self, path):

        return self._load_json_file(path)


    ######################## LLM Connection #########################

    def load_llm_connection(self):
        """
        Loads LLM connection data from a specified JSON file.
        """
        return self._load_json_file(self.LLM_CONFIG)


    ######################## Decisions #########################

    def load_decisions(self):
        """
        Loads previous decisions from the decisions.json file.
        """
        self.decisions = self._load_json_file(self.DECISIONS_FILE)


    ######################### Escala Hora Simulacion ##############################

    def seconds_to_scaled_time(self, seconds: int) -> str:
        """
        Converts real seconds to scaled time (HH:MM AM/PM).

        1 real second = 1 scaled minute
        60 real seconds = 1 scaled hour
        1440 real seconds = 24 scaled hours (1 full scaled day)

        Parameters:
            seconds (int): Number of real seconds to convert. Must be non-negative.

        Returns:
            str: Scaled time in 'HH:MM AM/PM' format.
        """
        if seconds < 0:
            raise ValueError("Seconds cannot be negative.")

        scaled_minutes = seconds  # Each real second equals 1 scaled minute
        hours_24 = (scaled_minutes // 60) % 24  # Keep the format within 24 hours
        minutes = scaled_minutes % 60

        # Convert 24-hour format to 12-hour format with AM/PM
        period = "AM" if hours_24 < 12 else "PM"
        hours_12 = hours_24 % 12
        if hours_12 == 0:
            hours_12 = 12  # Convert 00:xx to 12:xx AM

        return f"{hours_12:02}:{minutes:02} {period}"


    def scaled_time_to_seconds(self, scaled_time: str) -> int:
        """
        Converts a scaled time (HH:MM AM/PM) to real seconds.

        1 scaled minute = 1 real second
        1 scaled hour = 60 real seconds
        24 scaled hours = 1440 real seconds (1 full scaled day)

        Parameters:
            scaled_time (str): Scaled time in 'HH:MM AM/PM' format.

        Returns:
            int: Equivalent time in real seconds.
        """
        try:
            # Convert to 24-hour format using datetime
            time_obj = datetime.strptime(scaled_time, "%I:%M %p")
            hours, minutes = time_obj.hour, time_obj.minute

            return (hours * 60) + minutes  # Convert to total scaled minutes
        except ValueError:
            raise ValueError("Invalid input format. Expected 'HH:MM AM/PM'.")
