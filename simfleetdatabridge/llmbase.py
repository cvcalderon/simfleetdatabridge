import requests
from loguru import logger
import json
from pathlib import Path
from datetime import datetime, timedelta

class LlmBase:
    """
    Base class for agents that interact with an LLM.
    Provides methods to load agent profiles, memory, and decisions.
    """

    def __init__(self, sim_path):
        """
        Initializes LlmBase with the simulation base path.
        """
        self.sim_path = Path(sim_path)  # Ensure sim_path is a Path object

        # Data structures
        self.profiles = {}
        self.memory = {}
        self.decisions = {}
        self.environment = {}
        self.plan = {}

        self.date_week = {}
        self.index = 0
        self.total_days = 0

        self.summary_week = {}

        #History
        self.short_memory_history = {}  # No umbral
        self.long_memory_history = {}  # No umbral

        # LLM configuration
        self.model_config = {}
        self.actions = {}

        self.start_time = None
        self.end_time = None
        self.scale_ratio = 0

        # Session for LLM connection
        self.session = requests.Session()

    def _load_json_file(self, file_path):
        """
        Loads a JSON file and returns its content.
        If the file is missing or has an invalid format, returns an empty dictionary.
        """
        file_path = Path(file_path)  # Ensure file_path is a Path object
        try:
            with file_path.open("r", encoding="utf-8") as file:
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
        """
        config_data = self._load_json_file(config_path)
        if not config_data:
            logger.error("Failed to load framework configuration.")
            return

        # Store configuration in class variables
        self.model_config = config_data.get("model_config", {})
        self.actions = config_data.get("actions", {})
        self.environment = config_data.get("enviroment", {})

        logger.info("Framework configuration successfully loaded.")
        logger.info(f"Model Configuration: {self.model_config}")
        logger.info(f"Actions Configuration: {self.actions}")
        logger.info(f"Environment Configuration: {self.environment}")

    ########################## Profiles ###########################

    def load_agent_profiles(self):
        """Loads agent profiles from the respective JSON file."""
        profile_file = self.sim_path / "agents/profiles.json"
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
        memory_file = self.sim_path / "agents/memory.json"
        self.memory = self._load_json_file(memory_file)

    def get_agent_memory_info(self, agent_name):
        """Returns memory information for a specific agent."""
        return self.memory.get(agent_name, {})

    ######################### Simulation Time Scale ##############################

    def set_time_scale(self, real_seconds_per_sim_minute: float):
        """
        Defines how many real seconds correspond to 1 simulated minute.
        """
        self.scale_ratio = real_seconds_per_sim_minute

    def scale_range_time(self, start_time_day: str, end_time_day: str):
        """
        Define the time range of the simulation.
        """
        self.start_time = self._convert_to_minutes(start_time_day)
        self.end_time = self._convert_to_minutes(end_time_day)

        if self.start_time >= self.end_time:
            raise ValueError("The start time must be earlier than the end time.")

    def _convert_to_minutes(self, time_str: str) -> int:
        """
        Convierte 'HH:MM AM/PM' a minutos desde la medianoche.
        """
        time_obj = datetime.strptime(time_str, "%I:%M %p")
        return time_obj.hour * 60 + time_obj.minute

    def scaled_time_to_real_seconds(self, scaled_time: str) -> float:
        """
        Convert a simulated time to real seconds since the start of the simulated day.
        """
        scaled_minutes = self._convert_to_minutes(scaled_time)

        if scaled_minutes < self.start_time or scaled_minutes > self.end_time:
            logger.warning(f"{scaled_time} is out of the defined range ({self.start_time}-{self.end_time} min).")
            return 0

        return (scaled_minutes - self.start_time) * self.scale_ratio

    def real_seconds_to_scaled_time(self, real_seconds: float) -> str:
        """
        Convert real seconds to simulated time (within the defined range).
        """
        scaled_minutes = round(real_seconds / self.scale_ratio)
        new_scaled_time = self.start_time + scaled_minutes

        hours = (new_scaled_time // 60) % 24
        minutes = new_scaled_time % 60

        return datetime.strptime(f"{hours}:{minutes}", "%H:%M").strftime("%I:%M %p")

    def get_real_seconds_range(self) -> float:
        """
        Calculate how many real seconds the entire defined simulation range lasts.
        """
        total_scaled_minutes = self.end_time - self.start_time
        return total_scaled_minutes * self.scale_ratio

############################### Dates #######################################

    # Date generator

    def generate_date_dictionary(self, start_date, end_date):
        """
        Generates a dictionary with the dates between start_date and end_date (inclusive).
        Each entry is in the format:
        {index: [(day_name, day), (month_name, month), year]}
        It is assumed that dates are provided in the format dd/mm/yyyy.
        """
        try:
            start_date_dt = datetime.strptime(start_date, "%d/%m/%Y")
            end_date_dt = datetime.strptime(end_date, "%d/%m/%Y")
        except ValueError:
            logger.error("Error", "Invalid date format. Please use dd/mm/yyyy")
            return None

        # Dictionaries to convert numbers to names in English
        days_of_week = {
            0: 'Monday', 1: 'Tuesday', 2: 'Wednesday', 3: 'Thursday',
            4: 'Friday', 5: 'Saturday', 6: 'Sunday'
        }
        months = {
            1: 'January', 2: 'February', 3: 'March', 4: 'April',
            5: 'May', 6: 'June', 7: 'July', 8: 'August',
            9: 'September', 10: 'October', 11: 'November', 12: 'December'
        }

        date_dict = {}
        current_date = start_date_dt
        index = 1

        while current_date <= end_date_dt:
            day_name = days_of_week[current_date.weekday()]
            day_number = current_date.day
            month_name = months[current_date.month]
            month_number = current_date.month
            year = current_date.year

            # Store the information in the requested format
            date_dict[index] = [(day_name, day_number), (month_name, month_number), year]

            index += 1
            current_date += timedelta(days=1)

        return date_dict
        #self.date_dict = date_dict

    def group_dates_by_week(self, date_dict, excluded_days=None):
        """
        Groups the days in the 'date_dict' into natural weeks based on the first day.
        Optionally removes specified days from each week.

        Parameters:
        - date_dict: Dictionary with date information.
        - excluded_days: List of day names (e.g. ["Saturday", "Sunday"]) to exclude. If None, includes all.

        Returns:
        - Dictionary with keys 'week_1', 'week_2', ... and lists of remaining days.
        """
        weeks = {}
        week_num = 1
        current_week = []

        sorted_keys = sorted(date_dict.keys())
        total_days = len(sorted_keys)

        if not sorted_keys:
            return weeks  # handle empty input

        # Get the name of the first day
        first_day_name = date_dict[sorted_keys[0]][0][0]

        days_to_sunday = {
            "Monday": 6, "Tuesday": 5, "Wednesday": 4, "Thursday": 3,
            "Friday": 2, "Saturday": 1, "Sunday": 0,
        }

        days_in_first_week = days_to_sunday[first_day_name] + 1
        idx = 0

        while idx < total_days:
            slice_size = days_in_first_week if week_num == 1 else 7
            week_slice_keys = sorted_keys[idx: idx + slice_size]

            # Filter days if excluded_days is provided
            filtered_week = []
            for key in week_slice_keys:
                day_info = date_dict[key]
                day_name = day_info[0][0]
                if excluded_days is None or day_name not in excluded_days:
                    filtered_week.append(day_info)

            # Only include non-empty weeks
            if filtered_week:
                weeks[f"week_{week_num}"] = filtered_week

            idx += slice_size
            week_num += 1

        #return weeks
        #self.date_week = weeks
        self.date_week = self._flatten_weeks(weeks)

    def _flatten_weeks(self, weeks_dict):
        """
        Convert the dictionary into a list of tuples (week_name, day_info).
        """
        flat = []
        for week_name, days in weeks_dict.items():
            for day in days:
                flat.append((week_name, day))
        return flat

    def update_total_days(self):
        """
        Update the attribute total_days based on the current list of dates.
        """
        self.total_days = len(self.date_week)

    def has_next_day(self):
        return self.index < self.total_days

    def get_current_day(self):
        if not self.has_next_day():
            return None
        return self.date_week[self.index][1]

    def get_current_week_name(self):
        if not self.has_next_day():
            return None
        return self.date_week[self.index][0]

    def get_day_context(self):
        """
        Return a simple dictionary useful for an LLM.
        """
        week, [(day_name, day), (month_name, month), year] = self.date_week[self.index]
        return {
            "week": week,
            "day_name": day_name,
            "day": day,
            "month_name": month_name,
            "month": month,
            "year": year
        }

    def count_days_per_week(self):
        """
        Iterates over the days using an auxiliary index and counts how many days are in each week.
        Returns a dictionary in the format {week name: number of days}.
        """
        weeks = {}
        idx = 0

        while idx < self.total_days:
            week = self.date_week[idx][0]
            if week not in weeks:
                weeks[week] = 0
            weeks[week] += 1
            idx += 1

        self.summary_week = weeks
        #return weeks

    def get_days_in_week(self, week_name):
        """
        Returns the number of days for a given week name from the weeks dictionary.
        If the week is not found, returns 0.
        """

        return self.summary_week.get(week_name, 0)

    def is_week_finished(self):
        """
        Return True if the next day is in another week (or it's the end).
        """
        if self.index + 1 >= self.total_days:
            return True  # última iteración
        current_week = self.date_week[self.index][0]
        next_week = self.date_week[self.index + 1][0]
        return current_week != next_week

    def advance(self):
        if self.has_next_day():
            self.index += 1


    def is_first_day_of_current_week(self):
        """
        Return True if the current index points to the first day of its week.
        """
        if self.index == 0:
            return True

        current_week = self.date_week[self.index][0]
        previous_week = self.date_week[self.index - 1][0]
        return current_week != previous_week

    def is_last_day_of_current_week(self):
        """
        Return True if the current index points to the last day of its week.
        """
        if self.index >= self.total_days - 1:
            return True  # Último día total

        current_week = self.date_week[self.index][0]
        next_week = self.date_week[self.index + 1][0]
        return current_week != next_week


############################### Disrupt events #######################################

    def build_event_index(self):
        """
        Build the event_by_date index from self.environment["special_events"].
        """
        index = {}
        for event in self.environment.get("special_events", []):
            for date in event["dates"]:
                if date not in index:
                    index[date] = []
                index[date].append(event["id"])
        self.environment["event_by_date"] = index

    def get_events_for_today(self):
        if not hasattr(self, "environment") or not isinstance(self.environment, dict):
            return None

        day = self.get_current_day()
        if not day:
            return None

        day_str = f"{day[2]:04d}-{day[1][1]:02d}-{day[0][1]:02d}"



        event_ids = self.environment.get("event_by_date", {}).get(day_str, [])

        logger.warning(f"DEBUG: day = '{day}', day_str = {day_str}, event_ids = {event_ids}")

        if not event_ids:
            return None

        all_events = self.environment.get("special_events", [])
        if not isinstance(all_events, list):
            return None

        id_to_event = {e["id"]: e for e in all_events if "id" in e}
        return [id_to_event[eid] for eid in event_ids if eid in id_to_event] or None

