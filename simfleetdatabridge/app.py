import json
import os
import re

from spade.agent import Agent
from spade.behaviour import OneShotBehaviour, State, FSMBehaviour

from simfleetdatabridge.llmbase import LlmBase
from simfleetdatabridge.utils import oneshot_request_llm

from loguru import logger

PREPARE_MEMORY = "PREPARE_MEMORY"
DECISION_MAKING = "DECISION_MAKING"
PREPARE_OUTPUT = "PREPARE_OUTPUT"

class EngineAgent(Agent, LlmBase):
    """
    After these tasks are done in the Simulator constructor, the simulation is started when the ``run`` method is called.
    """

    def __init__(self, config, sim_path, jid="engine@localhost", password="secret"):
        super().__init__(jid=jid, password=password)
        LlmBase.__init__(self, sim_path)    # Initialize LlmBase with the simulation path

        self.config = config  # LLM engine config
        self.path = sim_path  # Simulation Path file

        self.agents_action = None
        self.next_day = None
        self.actual_day = None

        self.status = None
        self.stopped = False

    def is_finished(self):
        """
        Checks if the engine is finished.

        Returns:
            bool: whether the simulation is finished or not.
        """
        return self.stopped

    async def setup(self):
        """
        Setup method executed when the agent starts.
        Loads profiles and memory from JSON files.
        """

        #New simulation
        self.load_framework_config(self.config) # Load framework config - actions + llm
        self.load_agent_profiles()  # Cargar perfiles
        self.load_memory()  # Cargar memoria


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

#Test llamada LLM
# class DecisionMakingBehaviour(OneShotBehaviour):
#     """
#     One-time behaviour that makes transport decisions for each agent using an LLM.
#     """
#
#     def __init__(self, config):
#         super().__init__()
#         self.llm_conection = config  # `EngineAgent`
#
#     async def run(self):
#         logger.info("[DecisionMakingBehaviour] Starting decision process.")
#
#         new_decisions = {}
#
#         for agent_name in self.agent.get_agent_names():
#             profile = self.agent.get_agent_info(agent_name)
#             past_memory = self.agent.get_agent_memory_info(agent_name)
#
#             # Obtener la mejor opción de transporte para el siguiente día
#             decision = await self.make_decision(agent_name, profile, past_memory)
#
#             if decision:
#                 new_decisions[agent_name] = decision["decision"]
#
#         with open("decisions.json", "w") as f:
#             json.dump(new_decisions, f, indent=4)
#
#         logger.info("[DecisionMakingBehaviour] Decision process completed.")
#
#     async def make_decision(self, agent_name, profile, past_memory):
#         """
#         Calls the LLM to determine the best transport mode for the next day.
#         """
#         prompt = f"""
#         You are a Pedestrian with the following profile: {json.dumps(profile, indent=2)}.
#         Based on the following JSON of historical travel data and the profile, analyze and determine the best transportation option for the next day.
#
#         **Instructions:**
#         1. Evaluate the travel options.
#         2. Determine the departure time and the mode of transport.
#         3. Justify the decision based on travel time and cost.
#         4. **Return ONLY the response in JSON format, without any additional explanation.**
#
#         ### **Input Data (JSON):**
#         {json.dumps({"travel_history": past_memory}, indent=2)}
#
#         **Expected Output Format (JSON):**
#         {{
#           "decision": {{
#             "suggested_departure_time": "XX:XX",
#             "suggested_transport_mode": "XXX",
#             "estimated_cost": X.XX,
#             "estimated_travel_time_min": XX,
#             "reasoning": "XXX"
#           }}
#         }}
#         """
#
#         # Llamada al LLM
#         decision = await oneshot_request_llm(self.agent, config=self.llm_conection, prompt=prompt)
#
#         if decision:
#             logger.info(f"[DecisionMakingBehaviour] {agent_name} chooses {decision}")
#             return decision
#         else:
#             logger.warning(f"[DecisionMakingBehaviour] Invalid decision for {agent_name}. Using fallback option.")
#             return {
#                 "decision": {
#                     "suggested_departure_time": "06:30",
#                     "suggested_transport_mode": "walk",
#                     "estimated_cost": 0,
#                     "estimated_travel_time_min": 100,
#                     "reasoning": "Fallback due to invalid response."
#                 }
#             }



class EngineBehaviour(State):

    async def on_start(self):
        """
            Logs the start of the vehicle's strategy behavior.
        """
        logger.debug("Strategy {} started in vehicle".format(type(self).__name__))

    def process_events(self, events, day, class_type=None):
        """
        Procesa el archivo events_simulation.json para extraer, para cada agente de tipo TaxiCustomerAgent,
        la hora de salida (initial_event), la hora de llegada (trip_completion) y el tiempo de viaje.

        - Para **taxi**, **bus** y **sharing** se utiliza el evento "travel_to_destination" para calcular
          el tiempo de viaje: travel_time = trip_completion - travel_to_destination.
        - Para **walk** se calcula como: travel_time = trip_completion - initial_event.

        Se calcula el día del viaje usando:
            día = (timestamp_initial // 1440) + 1

        La información resultante se guarda en memory_file (memory.json).
        """
        # Clave: nombre del agente. Valor: diccionario con "initial" y "travel_destination" (si existe)
        pending_trips = {}

        for event in events:
            # Procesamos solo los eventos de agentes clientes
            if event["class_type"] != "TaxiCustomerAgent" and event["class_type"] != "PedestrianAgent":           #SOLUCIONAR PROBLEMA DE CLASS AL PROCESAR LOS EVENTS
                continue

            full_name = event["name"]
            # Se asume que el nombre es del tipo "nombre@localhost"
            agent_name = full_name.split("@")[0]
            event_type = event["event_type"]
            timestamp = event["timestamp"]

            if event_type == "initial_event":
                # Se inicia un nuevo viaje: se guarda el timestamp de salida
                pending_trips[agent_name] = {
                    "initial": timestamp,
                    "travel_destination": None  # Se completará si llega el evento "travel_to_destination"
                }
            elif event_type == "travel_to_destination":
                # Se registra el evento de viaje (aplicable para taxi, bus o sharing)
                if agent_name in pending_trips:
                    pending_trips[agent_name]["travel_destination"] = timestamp
            elif event_type == "trip_completion":
                # Al completarse el viaje, se espera que exista un viaje pendiente para el agente
                if agent_name in pending_trips:
                    initial_timestamp = pending_trips[agent_name]["initial"]
                    travel_dest_timestamp = pending_trips[agent_name]["travel_destination"]
                    arrival_timestamp = timestamp

                    # Extraer los detalles del viaje
                    details = event.get("details", {})
                    # Se asume que el detalle "transport" indica el modo de transporte
                    transport_mode = details.get("transport", "walk")
                    cost = details.get("cost", 0)

                    # Cálculo del tiempo de viaje en minutos
                    if transport_mode.lower() == "walk":
                        # Para walk se utiliza initial_event y trip_completion
                        travel_time = arrival_timestamp - initial_timestamp
                    else:
                        # Para taxi, bus y sharing se utiliza travel_to_destination, si está disponible
                        if travel_dest_timestamp is not None:
                            travel_time = arrival_timestamp - travel_dest_timestamp
                        else:
                            # Si no se encontró travel_to_destination, se utiliza el tiempo total del viaje
                            travel_time = arrival_timestamp - initial_timestamp
                    travel_time_min = int(round(travel_time))

                    # Conversión a formato "HH:MM" usando la función ya definida
                    departure_time_str = self.agent.seconds_to_scaled_time(int(initial_timestamp))
                    arrival_time_str = self.agent.seconds_to_scaled_time(int(arrival_timestamp))

                    # Registro del viaje para el agente
                    record = {
                        "day": day,
                        "departure_time": departure_time_str,
                        "arrival_time": arrival_time_str,
                        "travel_time_min": travel_time_min,
                        "transport_mode": transport_mode,
                        "cost": cost
                    }

                    if agent_name not in self.agent.memory:
                        self.agent.memory[agent_name] = []
                    self.agent.memory[agent_name].append(record)
                    # Se elimina el viaje pendiente (se asume que cada viaje está completo al procesar trip_completion)
                    del pending_trips[agent_name]

        with open(self.agent.MEMORY_FILE, 'w') as f:
            json.dump(self.agent.memory, f, indent=4)

    # def check_options_all_agents(self):
    #     all_agents_actions = {}
    #
    #     # Iteramos sobre cada agente en el diccionario self.agents
    #     for agent_name in self.agent.get_agent_names():
    #         # Obtener la memoria del agente, que asumimos es una lista de registros
    #         memory_agent = self.agent.get_agent_memory_info(agent_name)
    #
    #         # Seleccionar el departure_time del primer registro disponible (si existe)
    #         if memory_agent and isinstance(memory_agent, list) and len(memory_agent) > 0:
    #             departure_time = memory_agent[0].get("departure_time")
    #         else:
    #             departure_time = None
    #
    #         # Extraer los modos de transporte ya usados en la memoria
    #         used_actions = {entry.get("transport_mode") for entry in memory_agent if "transport_mode" in entry}
    #
    #         selected_action = None
    #         # Iterar sobre las acciones definidas en el JSON nuevo (dentro de la clave "actions")
    #         for action_name, action_info in self.agent.actions["actions"].items():
    #             if action_name not in used_actions:
    #                 selected_action = {
    #                     "action_name": action_name,
    #                     "class_path": action_info["class_path"],
    #                     "strategy_path": action_info["strategy_path"],
    #                     "depature_time": departure_time  # Se respeta el nombre "depature_time" solicitado
    #                 }
    #                 break
    #
    #         all_agents_actions[agent_name] = selected_action
    #
    #     return all_agents_actions

    def check_options_all_agents(self):
        all_agents_actions = {}

        # Extraemos los perfiles y las opciones de transporte
        profile_data = self.agent.profiles  # Información de los perfiles
        profile_transport_modes = {
            profile_name: set(profile_info.get("environment", {}).get("transport_options", []))
            for profile_name, profile_info in profile_data.items()
        }

        # Obtener todas las acciones posibles
        available_actions = self.agent.actions["actions"]

        # Iteramos sobre cada agente
        for agent_name in self.agent.get_agent_names():
            memory_agent = self.agent.get_agent_memory_info(agent_name)

            # Extraer modos de transporte ya usados
            used_actions = {entry["transport_mode"] for entry in memory_agent if
                            "transport_mode" in entry and entry["transport_mode"] is not None}

            # Obtener los transportes permitidos según su perfil
            available_transports = profile_transport_modes.get(agent_name, set())

            # **Si el agente ya ha usado todas sus opciones de transporte, omitirlo**
            if used_actions == available_transports:
                logger.info(
                    f"{agent_name} has already used all the transport options. Omitting in this iteration.")
                continue  # No procesa este agente

            # Determinar departure_time
            if memory_agent:
                # Usar el último departure_time si existe
                departure_time = memory_agent[-1]["departure_time"]
            else:
                # Si no hay memoria, obtener arrival_time_limit del perfil y restar 10 minutos
                arrival_time_limit = profile_data.get(agent_name, {}).get("environment", {}).get("arrival_time_limit",
                                                                                                 {}).get("time")
                if arrival_time_limit:
                    try:
                        arrival_time = datetime.strptime(arrival_time_limit, "%I:%M %p")
                        departure_time = (arrival_time - timedelta(minutes=10)).strftime("%I:%M %p")
                    except ValueError:
                        logger.error(f"Incorrect time format for {agent_name}: {arrival_time_limit}")
                        departure_time = None
                else:
                    departure_time = None

            # Filtrar acciones válidas (solo transportes aún no usados)
            valid_actions = [
                {
                    "action_name": action_name,
                    "class_path": available_actions[action_name]["class_path"],
                    "strategy_path": available_actions[action_name]["strategy_path"],
                    "departure_time": str(departure_time)
                }
                for action_name in available_transports
                if action_name in available_actions and action_name not in used_actions
            ]

            # Dejar la elección final al LLM
            if valid_actions:
                all_agents_actions[agent_name] = valid_actions

        # Logging mejorado
        #logger.debug("Available actions for LLM:\n%s", json.dumps(all_agents_actions, indent=4))

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


    async def make_decision(self, agent_name, profile, past_memory):
        """
        Calls the LLM to determine the best transport mode for the next day.
        """
        # prompt = f"""
        # You are a Pedestrian with the following profile: {json.dumps(profile, indent=2)}.
        # Based on the following JSON of historical travel data and the profile, analyze and determine the best transportation option for the next day.
        #
        # **Instructions:**
        # 1. Evaluate the travel options.
        # 2. Determine the departure time and the mode of transport.
        # 3. Justify the decision based on travel time and cost.
        # 4. **Return ONLY the response in JSON format, without any additional explanation.**
        #
        # ### **Input Data (JSON):**
        # {json.dumps({"travel_history": past_memory}, indent=2)}
        #
        # **Expected Output Format (JSON):**
        # {{
        #   "decision": {{
        #     "suggested_departure_time": "XX:XX",
        #     "suggested_transport_mode": "XXX",
        #     "estimated_cost": X.XX,
        #     "estimated_travel_time_min": XX,
        #     "reasoning": "XXX"
        #   }}
        # }}
        # """




        prompt = f"""
        You are a Pedestrian with the following profile: {json.dumps(profile, indent=2)}.
        Based on the following JSON of historical travel data and the profile above, analyze and determine the best transportation option for the next day.

        **Instructions:**  
        1. **Evaluate all available travel options** using the profile and historical data. Identify any relevant **historical patterns or trends** (e.g., which transport mode has been quickest or most reliable on previous days, or how departure time affected travel time).  
        2. **Weigh the pedestrian’s personal factors**: comfort, time sensitivity, and budget sensitivity. Use the profile’s preference values to balance these factors in the decision (e.g., a high comfort preference means comfort is important, but also consider time if time sensitivity is high, etc.). Ensure no single factor completely overrides the others unless the situation makes it necessary.  
        3. **Incorporate flexibility**: if an option that was best historically might not be available or ideal due to unexpected circumstances (traffic, weather, a flat bike tire, etc.), be ready to adapt and choose the next best alternative. Don’t rely rigidly on past choices if conditions change.  
        4. **Use realistic decision-making heuristics**: simulate human-like thinking. For example, apply **loss aversion** by being cautious about options that previously caused delays or high costs (avoiding a repeat of a bad experience). Also apply **familiarity bias** by considering if the pedestrian might prefer an option they’ve used and felt comfortable with before, as long as it meets their needs.  
        5. **Determine the optimal departure time and transport mode** for the next day, aiming to arrive by **(`{profile['environment']['arrival_time_threshold']}`)** (the specified arrival time threshold) or earlier. Ensure this choice fits the observed patterns and the pedestrian’s preferences.  
        6. **Justify the decision** with a brief reasoning, referencing expected travel time, cost, and how the choice satisfies the comfort/time/budget preferences and any relevant historical trend (e.g., “chosen mode has been consistently quick in the past and fits the budget”).  
        7. **Return ONLY the response in JSON format**, following the structure below, and do not include any additional explanation or text outside the JSON.

        ### **Input Data (JSON):**
        {json.dumps({"travel_history": past_memory}, indent=2)}

        **Expected Output Format (JSON):**
        {{
          "decision": {{
            "suggested_departure_time": "XX:XX",
            "suggested_transport_mode": "XXX",
            "estimated_cost": X.XX,
            "estimated_travel_time_min": XX,
            "reasoning": "XXX"
          }}
        }}
        """
        

        # prompt = f"""
        # You are an intelligent mobility assistant evaluating the best transportation option for a pedestrian based on historical travel data and their personal preferences.
        #
        # ### **Pedestrian Profile:**
        # {json.dumps(profile, indent=2)}
        #
        # ### **Task Description:**
        # Using the pedestrian’s profile and the historical travel data provided, determine the optimal **transportation mode** and **departure time** for the next day based on:
        #
        # - **Time Sensitivity:** Ensuring arrival **before or at** the given threshold (`{profile['environment']['arrival_time_threshold']}`).
        # - **Budget Sensitivity:** Minimizing cost while considering monthly budget constraints (`{profile['demographics']['month_transport_money']}`).
        # - **Comfort & Preferences:** Prioritizing the pedestrian's preference for comfort and convenience.
        # - **Eco-consciousness:** Factoring in the user's sustainability preferences.
        #
        # ### **Instructions:**
        # 1. **Analyze the historical travel data.**
        # 2. **Select the best transport mode and departure time** for the next day.
        # 3. **Justify your decision** based on time, cost, and the pedestrian's preferences.
        # 4. **Return ONLY the response in JSON format, without any additional explanation.**
        #
        # ### **Historical Travel Data (JSON):**
        # {json.dumps({"travel_history": past_memory}, indent=2)}
        #
        # ### **Expected JSON Output Format:**
        # {{
        #   "decision": {{
        #     "suggested_departure_time": "XX:XX",
        #     "suggested_transport_mode": "XXX",
        #     "estimated_cost": X.XX,
        #     "estimated_travel_time_min": XX,
        #     "reasoning": "XXX"
        #   }}
        # }}
        # """

        # prompt = f"""
        # You are an intelligent mobility assistant evaluating the best transportation option for a pedestrian based on historical travel data and their personal preferences.
        #
        # ### **Decision-Making Criteria:**
        # 1. **Prioritize Comfort:** If comfort preference is above 85, avoid personal-bike or walk unless necessary.
        # 2. **Balance Time and Cost:** If budget sensitivity is below 40, allow paid options if they save more than 5 minutes.
        # 3. **Consider Physical Effort:** Avoid options with high effort if the pedestrian values comfort highly.
        # 4. **Optimize Departure Time:** Choose the latest possible time while still meeting the arrival threshold.
        # 5. **Evaluate All Available Transport Options:** Ensure all modes in the pedestrian’s profile are analyzed.
        # 6. **Incorporate Eco-Consciousness:** If eco-consciousness is above 60, prioritize sustainable transport over fossil fuel options when the difference in time and cost is minimal.
        # 7. 4. **Return ONLY the response in JSON format, without any additional explanation.**
        #
        # ### **Pedestrian Profile:**
        # {json.dumps(profile, indent=2)}
        #
        # ### **Historical Travel Data:**
        # {json.dumps({"travel_history": past_memory}, indent=2)}
        #
        # ### **Expected JSON Output Format:**
        # {{
        #   "decision": {{
        #     "suggested_departure_time": "XX:XX",
        #     "suggested_transport_mode": "XXX",
        #     "estimated_cost": X.XX,
        #     "estimated_travel_time_min": XX,
        #     "reasoning": "XXX"
        #   }}
        # }}
        # """


        #Version 1
        #Explicación con "Estructura paso a paso"
        #Incorporación de "Learning from Past Data" --> Mejorar con memoria a corto plazo
        # prompt = f"""
        # You are an intelligent mobility assistant evaluating the best transportation option for a pedestrian based on historical travel data and their personal preferences.
        # Your decision-making process is based on behavioral mobility science and structured reasoning.
        #
        # ## **Decision-Making Process:**
        # Follow this structured reasoning before selecting the optimal choice:
        #
        # ### **Step 1: Assess Comfort Sensitivity**
        # - If comfort preference is above 85, assign a penalty score to physically demanding options (e.g., personal-bike, walking) unless no reasonable alternative exists.
        #
        # ### **Step 2: Evaluate Time Sensitivity & Budget Constraints**
        # - If time sensitivity is high (>60), prioritize faster transport options while considering budget constraints.
        # - If budget sensitivity is below 40, allow premium options if they reduce travel time by at least 5 minutes.
        #
        # ### **Step 3: Leverage Historical Behavior Trends**
        # - Identify recurring choices in similar past conditions and prioritize them if no significant inefficiencies exist.
        # - Detect patterns of inefficiency in travel duration and adjust recommendations accordingly.
        #
        # ### **Step 4: Integrate Eco-Consciousness**
        # - If eco-consciousness is above 60, prioritize sustainable transport over fossil fuel-based options when the time and cost differences are within 10%.
        #
        # ### **Step 5: Optimize Departure Time**
        # - Recommend the latest feasible departure time while ensuring the pedestrian arrives before the threshold.
        #
        # ### **Step 6: Rank Transport Options & Select the Optimal Choice**
        # - Assign a weighted score to each mode based on:
        #   - **Comfort Score** (if comfort preference >85, apply penalties to discomforting options)
        #   - **Speed Score** (time saved compared to alternatives)
        #   - **Cost Score** (impact on budget)
        #   - **Eco Score** (if applicable)
        # - Select the transport mode with the highest overall score.
        #
        # ### **Step 7: Generate JSON Output**
        # - **Return ONLY the response in JSON format, without any additional explanation.**
        #
        # ## **Pedestrian Profile:**
        # {json.dumps(profile, indent=2)}
        #
        # ## **Historical Travel Data:**
        # {json.dumps({"travel_history": past_memory}, indent=2)}
        #
        # ## **Expected JSON Output Format:**
        # {{
        #   "decision": {{
        #     "suggested_departure_time": "HH:MM",
        #     "suggested_transport_mode": "XXX",
        #     "estimated_cost": X.XX,
        #     "estimated_travel_time_min": XX,
        #     "reasoning": "Concise explanation of the decision based on the provided criteria."
        #   }}
        # }}
        # """

        #Version 2
        # prompt = f"""
        # You are an intelligent mobility assistant evaluating the best transportation option for a pedestrian based on historical travel data and their personal preferences.
        #
        # ## **Decision-Making Process:**
        #
        # ### **Step 1: Assess Comfort Sensitivity**
        # - If comfort preference is above **85**, apply a **-30% penalty** to physically demanding options unless no reasonable alternative exists.
        #
        # ### **Step 2: Evaluate Time Sensitivity & Budget Constraints**
        # - If time sensitivity is **greater than 60**, prioritize faster transport options while considering budget constraints.
        # - If a premium option saves **at least 5 minutes**, it is **only selected if its cost increase is less than 15%** of the monthly budget.
        #
        # ### **Step 3: Leverage Historical Behavior Trends**
        # - If a transport mode was selected in **at least 70% of similar past trips**, it receives a **+10% score boost**, unless it was inefficient in **15% or more** of cases.
        #
        # ### **Step 4: Integrate Eco-Consciousness**
        # - If eco-consciousness is above **60**, prioritize sustainable transport if cost and time differences are within **10%**.
        #
        # ### **Step 5: Optimize Departure Time**
        # - Identify the **fastest historical transport mode** and determine its **minimum travel time**.
        # - Compute the **earliest feasible departure time** to ensure arrival **before {profile['environment']['arrival_time_threshold']}**.
        # - If **time sensitivity > 60**, add a **safety margin of 10% of travel time**.
        # - If **historical delays exist**, adjust departure time by **2-5 minutes earlier** to prevent lateness.
        # - If **comfort preference > 85**, ensure departure minimizes wait time at the destination.
        # - Suggested departure time must be no later than **arrival_time_threshold - adjusted_travel_time**.
        #
        # ### **Step 6: Rank Transport Options & Select the Optimal Choice**
        # Each mode is scored based on:
        # - **Speed Score (35%)** → Based on saved time vs. slowest option.
        # - **Cost Score (25%)** → Based on affordability relative to budget.
        # - **Comfort Score (25%)** → Adjusted by preferences.
        # - **Eco Score (15%)** → If applicable.
        #
        # ### **Step 7: Generate JSON Output**
        # - **Return ONLY the response in JSON format, without any additional explanation.**
        #
        # ## **Pedestrian Profile:**
        # {json.dumps(profile, indent=2)}
        #
        # ## **Historical Travel Data:**
        # {json.dumps({"travel_history": past_memory}, indent=2)}
        #
        # ## **Expected JSON Output Format:**
        # {{
        #   "decision": {{
        #     "suggested_departure_time": "HH:MM",
        #     "suggested_transport_mode": "XXX",
        #     "estimated_cost": X.XX,
        #     "estimated_travel_time_min": XX,
        #     "confidence_score": X.XX,
        #     "reasoning": {{
        #       "time_analysis": "Explanation...",
        #       "budget_analysis": "Explanation...",
        #       "comfort_analysis": "Explanation...",
        #       "historical_analysis": "Explanation..."
        #     }}
        #   }}
        # }}
        # """

        logger.warning("DEBUG: {}".format(prompt))

        # Llamada al LLM
        decision = await oneshot_request_llm(self.agent, config=self.agent.llm_config, prompt=prompt)

        if decision:
            logger.info(f"[DecisionMakingBehaviour] {agent_name} chooses {decision}")
            return decision
        else:
            logger.warning(f"[DecisionMakingBehaviour] Invalid decision for {agent_name}. Using fallback option.")
            return {
                "decision": {
                    "suggested_departure_time": "06:30",
                    "suggested_transport_mode": "walk",
                    "estimated_cost": 0,
                    "estimated_travel_time_min": 100,
                    "reasoning": "Fallback due to invalid response."
                }
            }

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

        # Mejora -> 1) Probar opciones de manera estatica o 2) Probar opciones dichas por el LLM
        # Encontrar perfiles sin procesar

        logger.warning("DEBUG 1: {} ".format(len(self.agent.agents_action)))

        if len(self.agent.agents_action) < len(self.agent.profiles.keys()):
            logger.warning("DEBUG 3.1: {} ".format(set(self.agent.profiles.keys())))
            logger.warning("DEBUG 3.2: {} ".format(set(self.agent.agents_action.keys())))
            perfiles_sin_procesar = set(self.agent.profiles.keys()) - set(self.agent.agents_action.keys())
            logger.warning("DEBUG 3: {} ".format(perfiles_sin_procesar))

            #perfiles_sin_procesar = self.agent.profiles.keys()
            #logger.warning("DEBUG 2: {} ".format(perfiles_sin_procesar))

        else:
            self.set_next_state(PREPARE_OUTPUT)
            return

        for agent_name in perfiles_sin_procesar:

            # if self.agent.agents_action[agent_name] is None:

            profile = self.agent.get_agent_info(agent_name)
            past_memory = self.agent.get_agent_memory_info(agent_name)

            # Obtener la mejor opción de transporte para el siguiente día
            decision = await self.make_decision(agent_name, profile, past_memory)

            if decision:
                new_decisions[agent_name] = decision["decision"]

                # Extraer la información sugerida
                suggested_departure_time = decision["decision"].get("suggested_departure_time")
                suggested_transport_mode = decision["decision"].get("suggested_transport_mode")

                # Obtener el agente correspondiente
                # agent = self.agents.get(agent_name)
                # if agent and hasattr(agent, "actions") and "actions" in agent.actions:
                agent_actions = self.agent.actions["actions"]
                # Extraer el strategy_path correspondiente al modo sugerido

                if suggested_transport_mode in agent_actions:
                    action_path = agent_actions[suggested_transport_mode].get("class_path")
                    strategy_path = agent_actions[suggested_transport_mode].get("strategy_path")
                else:
                    action_path = None
                    strategy_path = None
                # else:
                #    action_path = None
                #    strategy_path = None

                # decisions_result[agent_name] = {
                self.agent.agents_action[agent_name] = {
                    "action_name": suggested_transport_mode,
                    "class_path": action_path,
                    "strategy_path": strategy_path,
                    "depature_time": suggested_departure_time
                }


        # Verificar si ya existe un archivo para ese día en la carpeta days
        dest_file = f"LlmDecisionMaking/Agents/decisions/{self.agent.next_day+1}_day_decisions.json"
        if os.path.exists(dest_file):
            logger.debug(f"El archivo para el día {self.agent.next_day} ya existe.")

        with open(dest_file, "w") as f:
            json.dump(new_decisions, f, indent=4)

        logger.info("[DecisionMakingBehaviour] Decision process completed.")

        if self.agent.agents_action != None:
            #self.agent.stopped = True
            self.set_next_state(PREPARE_OUTPUT)
            return

class EnginePrepareOutputState(EngineBehaviour):
    async def on_start(self):
        await super().on_start()
        self.agent.status = PREPARE_OUTPUT
        logger.debug("{} in Prepare output State".format(self.agent.jid))

    async def run(self):
        #logger.info("{} arrived at its destination".format(self.agent.jid))

        simfleet_path = os.path.join(self.agent.path, "config/simfleet")

        day, name, sim_config = self.load_latest_simfleet_config(simfleet_path)
        decisions = self.agent.agents_action

        logger.warning("DEBUG 2: {} in Prepare output State".format(decisions))

        for customer in sim_config.get("customers", []):
            customer_name = customer.get("name")
            if customer_name in decisions:
                decision = decisions[customer_name]
                # Actualizar delay usando depature_time (conversión a segundos)
                dep_time = decision.get("depature_time")
                if dep_time:
                    customer["delay"] = self.agent.scaled_time_to_seconds(str(dep_time))
                else:
                    logger.debug(f"Advertencia: No se encontró 'depature_time' para {customer_name}.")
                # Actualizar class y strategy
                customer["class"] = decision.get("class_path", customer.get("class"))
                customer["strategy"] = decision.get("strategy_path", customer.get("strategy"))
            else:
                logger.debug(f"Advertencia: No hay decisión para el cliente {customer_name}.")

        self.agent.actual_day = day + 1

        end_path = os.path.join(simfleet_path, (day+1)+"_day_"+name)
        # Verificar si ya existe un archivo para ese día en la carpeta days
        #dest_file = f"LlmDecisionMaking/Config/days/{self.agent.next_day+1}_day_config_simulation.json"
        #dest_path = os.path.join(simfleet_path, end_path)
        if os.path.exists(end_path):
            logger.debug(f"El archivo para el día {day} ya existe.")

        with open(dest_file, 'w') as f:
            json.dump(end_path, f, indent=4)

        # (Opcional) Si se desea mover en vez de copiar, se puede borrar el original:
        #os.remove('LlmDecisionMaking/Config/config_simulation.json')

        #self.agent.stopped = True

class EnginePrepareMemoryState(EngineBehaviour):
    async def on_start(self):
        await super().on_start()
        self.agent.status = PREPARE_MEMORY
        logger.debug("{} in Prepare memory State".format(self.agent.jid))

    async def run(self):

        memory = self.agent.memory

        # Calcula el día máximo en una sola línea
        max_day = max((trip.get('day', 0) for trips in memory.values() for trip in trips), default=0)

        # Planifica el siguiente día
        self.agent.next_day = max_day + 1

        # Verificar si ya existe un archivo para ese día en la carpeta days
        dest_file = f"LlmDecisionMaking/LogsForDays/days/{self.agent.next_day}_day_events_simulation.json"
        if os.path.exists(dest_file):
            logger.debug(f"El archivo para el día {self.agent.next_day} ya existe.")


        #events = self.agent.load_json_conf('LlmDecisionMaking/LogsForDays/events_simulation.json')

        #logger.warning("DEBUG 1: {} in Decision making State".format(events))

        with open('LlmDecisionMaking/LogsForDays/events_simulation.json', 'r') as archivo:
            events = json.load(archivo)

        #logger.warning("DEBUG 2: {} in Decision making State".format(events))

        if events:

            # Validar que 'events' sea una lista de diccionarios con las claves requeridas
            required_keys = {"name", "timestamp", "event_type", "class_type", "details"}
            if not isinstance(events, list) or not all(
                    isinstance(e, dict) and required_keys.issubset(e.keys()) for e in events):
                raise ValueError("La estructura de events_simulations.json no es la esperada.")

            # Paso 3: Guardar el contenido validado en un nuevo archivo en la carpeta days
            with open(dest_file, 'w') as f:
                json.dump(events, f, indent=4)

            # (Opcional) Si se desea mover en vez de copiar, se puede borrar el original:
            os.remove('LlmDecisionMaking/LogsForDays/events_simulation.json')

            self.process_events(events=events, day=self.agent.next_day)

        #if max_day < len(self.agent.actions):
        #self.agent.agents_action = self.check_options_all_agents()

        self.set_next_state(DECISION_MAKING)
        return


class EngineDecisionMakingState_old(EngineBehaviour):
    async def on_start(self):
        await super().on_start()
        self.agent.status = DECISION_MAKING
        logger.debug("{} in Decision making State".format(self.agent.jid))

    async def run(self):


        new_decisions = {}
        #decisions_result = {}

        #if self.agent.agents_action != None:
        #    #self.agent.stopped = True
        #    self.set_next_state(PREPARE_OUTPUT)
        #    return

        #if len(self.agent.agents_action) != len(self.agent.get_agent_names):

        # Encontrar perfiles sin procesar

        logger.warning("DEBUG 1: {} ".format(len(self.agent.agents_action)))

        if len(self.agent.agents_action) < len(self.agent.profiles.keys()):
            logger.warning("DEBUG 3.1: {} ".format(set(self.agent.profiles.keys())))
            logger.warning("DEBUG 3.2: {} ".format(set(self.agent.agents_action.keys())))
            perfiles_sin_procesar = set(self.agent.profiles.keys()) - set(self.agent.agents_action.keys())
            logger.warning("DEBUG 3: {} ".format(perfiles_sin_procesar))

            #perfiles_sin_procesar = self.agent.profiles.keys()
            #logger.warning("DEBUG 2: {} ".format(perfiles_sin_procesar))

        else:
            self.set_next_state(PREPARE_OUTPUT)
            return

        for agent_name in perfiles_sin_procesar:

            # if self.agent.agents_action[agent_name] is None:

            profile = self.agent.get_agent_info(agent_name)
            past_memory = self.agent.get_agent_memory_info(agent_name)

            # Obtener la mejor opción de transporte para el siguiente día
            decision = await self.make_decision(agent_name, profile, past_memory)

            if decision:
                new_decisions[agent_name] = decision["decision"]

                # Extraer la información sugerida
                suggested_departure_time = decision["decision"].get("suggested_departure_time")
                suggested_transport_mode = decision["decision"].get("suggested_transport_mode")

                # Obtener el agente correspondiente
                # agent = self.agents.get(agent_name)
                # if agent and hasattr(agent, "actions") and "actions" in agent.actions:
                agent_actions = self.agent.actions["actions"]
                # Extraer el strategy_path correspondiente al modo sugerido

                if suggested_transport_mode in agent_actions:
                    action_path = agent_actions[suggested_transport_mode].get("class_path")
                    strategy_path = agent_actions[suggested_transport_mode].get("strategy_path")
                else:
                    action_path = None
                    strategy_path = None
                # else:
                #    action_path = None
                #    strategy_path = None

                # decisions_result[agent_name] = {
                self.agent.agents_action[agent_name] = {
                    "action_name": suggested_transport_mode,
                    "class_path": action_path,
                    "strategy_path": strategy_path,
                    "depature_time": suggested_departure_time
                }


        # for agent_name in self.agent.get_agent_names():
        #
        #     #if self.agent.agents_action[agent_name] is None:
        #
        #     profile = self.agent.get_agent_info(agent_name)
        #     past_memory = self.agent.get_agent_memory_info(agent_name)
        #
        #     # Obtener la mejor opción de transporte para el siguiente día
        #     decision = await self.make_decision(agent_name, profile, past_memory)
        #
        #     if decision:
        #         new_decisions[agent_name] = decision["decision"]
        #
        #         # Extraer la información sugerida
        #         suggested_departure_time = decision["decision"].get("suggested_departure_time")
        #         suggested_transport_mode = decision["decision"].get("suggested_transport_mode")
        #
        #         # Obtener el agente correspondiente
        #         #agent = self.agents.get(agent_name)
        #         #if agent and hasattr(agent, "actions") and "actions" in agent.actions:
        #         agent_actions = self.agent.actions["actions"]
        #         # Extraer el strategy_path correspondiente al modo sugerido
        #
        #         if suggested_transport_mode in agent_actions:
        #             action_path = agent_actions[suggested_transport_mode].get("class_path")
        #             strategy_path = agent_actions[suggested_transport_mode].get("strategy_path")
        #         else:
        #             action_path = None
        #             strategy_path = None
        #         #else:
        #         #    action_path = None
        #         #    strategy_path = None
        #
        #         decisions_result[agent_name] = {
        #             "action_name": suggested_transport_mode,
        #             "class_path": action_path,
        #             "strategy_path": strategy_path,
        #             "depature_time": suggested_departure_time
        #         }

        #self.agent.agents_action = decisions_result

        # Verificar si ya existe un archivo para ese día en la carpeta days
        dest_file = f"LlmDecisionMaking/Agents/decisions/{self.agent.next_day+1}_day_decisions.json"
        if os.path.exists(dest_file):
            logger.debug(f"El archivo para el día {self.agent.next_day} ya existe.")

        with open(dest_file, "w") as f:
            json.dump(new_decisions, f, indent=4)

        logger.info("[DecisionMakingBehaviour] Decision process completed.")

        if self.agent.agents_action != None:
            #self.agent.stopped = True
            self.set_next_state(PREPARE_OUTPUT)
            return



class FSMEngineBehaviour(FSMBehaviour):
    def setup(self):
        # Create states
        self.add_state(PREPARE_MEMORY, EnginePrepareMemoryState(), initial=True)
        self.add_state(DECISION_MAKING, EngineDecisionMakingState())
        self.add_state(PREPARE_OUTPUT, EnginePrepareOutputState())

        # Create transitions
        self.add_transition(
            PREPARE_MEMORY, DECISION_MAKING
        )  # waiting for messages
        self.add_transition(
            DECISION_MAKING, PREPARE_OUTPUT
        )


