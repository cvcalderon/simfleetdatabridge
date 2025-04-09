import json
import time
import random
from datetime import datetime, timedelta
from spade.behaviour import OneShotBehaviour
from loguru import logger
from simfleetdatabridge.utils import oneshot_request_llm, describe_profile


async def llm_agent_plan(agent, profile=None, prompt=None, forced_week=False, profile_description=False, days=5):
    instance = LlmPlanningAgent(profile, prompt, forced_week, profile_description, days)
    agent.add_behaviour(instance)
    await instance.join()
    return instance.response


class LlmPlanningAgent(OneShotBehaviour):
    def __init__(self, profile, prompt, forced_week, profile_description, days):
        super().__init__()
        self.steps = prompt  # A list of steps is expected (if provided)
        self.forced_week = forced_week
        self.agent_profile = profile
        self.profile_description = profile_description
        self.profile_described = None
        self.response = None
        self.days = days  # Number of days for the itinerary

    def generate_plan_prompt(self):
        # If no valid steps are provided, use the default steps.
        if not self.steps or not isinstance(self.steps, list):
            self.steps = [
                {
                    "step": 1,
                    "title": "Profile Analysis",
                    "description": (
                        "Examine the demographic data, mobility preferences, and environmental conditions "
                        "to identify the user's needs, restrictions, and priorities."
                    )
                },
                {
                    "step": 2,
                    "title": "Evaluate Transportation Options",
                    "description": (
                        "Review the available transport options provided in the 'transport_options' field "
                        "of the user profile, and determine which options are feasible and best meet the identified preferences and restrictions. "
                        "**ONLY consider the transport modes listed in 'transport_options'**."
                    )
                },
                {
                    "step": 3,
                    "title": "Design the Itinerary",
                    "description": (
                        f"Develop a detailed travel itinerary for the next {self.days} days that ensures the user meets "
                        "their required arrival times and preferences, logically organizing the route and chosen transportation methods."
                    )
                }
            ]

        # If forced_week is True, insert an exploratory step.
        if self.forced_week:
            arrival_type = self.agent_profile.get("environment", {}) \
                .get("arrival_time_limit", {}) \
                .get("type", "unspecified")
            arrival = self.agent_profile.get("environment", {}) \
                .get("arrival_time_limit", {}) \
                .get("time", "unspecified")
            exploratory_step = {
                "step": None,  # Numbering will be reassigned later
                "title": "Exploratory Transportation Analysis",
                "description": (
                    "You MUST examine EACH transport mode listed in 'transport_options' SEPARATELY. "
                    f"For each option, evaluate how well it fits the user's needs: {arrival_type} arrival by '{arrival}', eco-consciousness, comfort, reliability, budget and time. "
                    "DO NOT assume a single best mode without comparing all options. Consider pros, cons, possible delays, creative uses, or combination strategies. "
                    f"Show clearly why each mode is or isn't suitable for each of the {self.days} days."
                )
            }
            # Insert the exploratory step after the mobility patterns analysis or, if not available, after 'Evaluate Transportation Options'
            insert_after_title = "Analyze Mobility Patterns" if self.agent_profile.get("patterns") else "Evaluate Transportation Options"
            index = next((i for i, step in enumerate(self.steps) if step["title"] == insert_after_title), None)
            if index is not None:
                self.steps.insert(index + 1, exploratory_step)

        # If the profile contains "patterns", insert a step to analyze them.
        if self.agent_profile.get("patterns"):
            pattern_analysis_step = {
                "step": None,  # Numbering will be reassigned later
                "title": "Analyze Mobility Patterns",
                "description": (
                    "Analyze the mobility patterns provided in the 'patterns' field of the user profile. "
                    "Use these patterns to further refine the itinerary recommendations and optimize transportation choices."
                )
            }
            index = next((i for i, step in enumerate(self.steps) if step["title"] == "Evaluate Transportation Options"), None)
            if index is not None:
                self.steps.insert(index + 1, pattern_analysis_step)

        # Reassign the numbering of the steps.
        for idx, step in enumerate(self.steps, start=1):
            step["step"] = idx

        # Additional step to ensure output in strict JSON format.
        additional_step = {
            "step": len(self.steps) + 1,
            "title": "Output Strict JSON",
            "description": (
                "Respond ONLY with a valid JSON that matches the required structure. "
                "DO NOT add any extra text, code, explanations, or markdown."
            )
        }

        evaluation_steps = self.steps + [additional_step]

        # Create the structure for the itinerary days.
        days_plan = [
            {"day": f"Day {i + 1}", "suggested_transport_mode": "", "suggested_departure_time": "HH:MM AM/PM"}
            for i in range(self.days)
        ]

        task_text = (
            f"Generate a personalized travel plan for the next {self.days} days, ensuring efficient transportation choices according to the user's profile."
        )

        # Determine the profile to send: if profile_description is enabled, use the descriptive version.
        if self.profile_description and self.profile_described:
            profile_input = {
                "profile": self.profile_described,
                "transport_options": self.agent_profile.get("environment", {}).get("transport_options", [])
            }
            if self.agent_profile.get("patterns"):
                profile_input["patterns"] = self.agent_profile["patterns"]
        else:
            profile_input = self.agent_profile

        prompt = {
            "user_profile": profile_input,
            "instructions": {
                "task": task_text,
                "evaluation_steps": evaluation_steps,
                "output_requirements": {
                    "format": "**STRICT JSON ONLY**.",
                    "structure": {
                        "travel_plan": {
                            "days": days_plan,
                            "reason": "Explain briefly the logic behind the selected itinerary for the given days."
                        }
                    }
                }
            }
        }
        return json.dumps(prompt, indent=4)

    def is_valid_plan_structure(self, decision: dict, days: int) -> bool:
        """
        Validates that the response contains the 'travel_plan' section with the expected structure.

        Requirements:
          - 'travel_plan' must exist and be a dictionary.
          - 'travel_plan' must contain the key 'days', which should be a non-empty list with exactly {days} elements.
          - 'travel_plan' must contain the key 'reason'.

        Returns:
            bool: True if the structure is valid; False otherwise.
        """
        try:
            if not isinstance(decision, dict):
                logger.warning("The decision is not a dictionary.")
                return False

            if "travel_plan" not in decision:
                logger.warning("The 'travel_plan' section is missing in the decision.")
                return False

            travel_plan = decision["travel_plan"]
            if not isinstance(travel_plan, dict):
                logger.warning("'travel_plan' must be a dictionary.")
                return False

            if "days" not in travel_plan or "reason" not in travel_plan:
                logger.warning("Either 'days' or 'reason' is missing in the 'travel_plan' section.")
                return False

            days_list = travel_plan["days"]
            if not isinstance(days_list, list) or len(days_list) == 0:
                logger.warning("The 'days' key must be a non-empty list.")
                return False

            if len(days_list) != days:
                logger.warning(
                    f"The number of planned days ({len(days_list)}) does not match the expected value ({days}).")
                return False

            return True

        except Exception as e:
            logger.error(f"Error checking the structure: {e}")
            return False


    def is_valid_plan_decision(self, decision: dict, profile: dict, available_actions: list, days: int) -> bool:
        """
        Validates that the travel plan content (within 'travel_plan') meets the logical constraints.

        It verifies that:
          - The 'travel_plan' section exists and contains a 'days' list with exactly {days} days.
          - Each day of the itinerary includes the keys 'suggested_departure_time' and 'suggested_transport_mode'.
          - Each day has a suggested transport mode that is among the allowed options
            (defined in the profile and in available_actions).
          - Each day has a departure time that is within the allowed range.

        Returns:
            bool: True if the plan's content is valid; False otherwise.
        """
        try:
            travel_plan = decision.get("travel_plan")
            if not travel_plan:
                logger.warning("The 'travel_plan' section was not found in the decision.")
                return False

            days_list = travel_plan.get("days")
            if not days_list or not isinstance(days_list, list):
                logger.warning("The 'days' key must be a list with at least one day.")
                return False

            if len(days_list) != days:
                logger.warning(
                    f"The number of days in the plan ({len(days_list)}) does not match the expected value ({days}).")
                return False

            # Get the valid transport options from the profile.
            valid_transports = set(profile.get("environment", {}).get("transport_options", []))

            # Validate each day of the itinerary.
            required_day_keys = ["suggested_departure_time", "suggested_transport_mode"]
            for i, day in enumerate(days_list, start=1):
                # Verify that the required keys exist.
                if not all(key in day for key in required_day_keys):
                    logger.warning(f"Day {i} does not contain the required fields: {required_day_keys}.")
                    return False

                transport_mode = day["suggested_transport_mode"].lower()
                departure_time = day["suggested_departure_time"]

                # Validate the transport mode.
                if transport_mode not in valid_transports or transport_mode not in available_actions:
                    logger.warning(f"Invalid transport mode on day {i}: {transport_mode}")
                    return False

                # Validate the departure time.
                departure_minutes = self.agent._convert_to_minutes(departure_time)
                if not (self.agent.start_time <= departure_minutes <= self.agent.end_time):
                    logger.warning(
                        f"The departure time on day {i} ({departure_time} - {departure_minutes} min) "
                        f"is out of the allowed range ({self.agent.start_time}-{self.agent.end_time} min)."
                    )
                    return False

            return True

        except Exception as e:
            logger.error(f"Error validating the decision: {e}")
            return False

    def generate_random_plan(self) -> dict:
        """
        Generates a fallback travel plan with random default values for each day.

        It uses the 'time' value from 'arrival_time_limit' in 'environment' to generate
        a range of possible departure times. The window spans 2 hours before the arrival time,
        with departure times spaced every 20 minutes.

        Returns:
            dict: A travel plan structured as a JSON object.
        """

        # Retrieve valid transport options; fallback to ["walk"] if none are provided.
        valid_transports = self.agent_profile.get("environment", {}).get("transport_options", [])
        if not valid_transports:
            valid_transports = ["walk"]

        # Retrieve arrival time from the profile; default to "07:00 PM" if not available.
        arrival_time_str = self.agent_profile.get("environment", {}) \
            .get("arrival_time_limit", {}) \
            .get("time", "07:00 AM")
        try:
            arrival_time = datetime.strptime(arrival_time_str, "%I:%M %p")
        except Exception as e:
            logger.warning(f"Error parsing arrival time '{arrival_time_str}', defaulting to 07:00 PM: {e}")
            arrival_time = datetime.strptime("07:00 AM", "%I:%M %p")

        # Define the start of the departure window: 2 hours before the arrival time.
        start_time = arrival_time - timedelta(hours=2)

        # Generate possible departure times within the 2-hour window in 20-minute intervals.
        possible_times = []
        current_time = start_time
        while current_time <= arrival_time:
            possible_times.append(current_time.strftime("%I:%M %p"))
            current_time += timedelta(minutes=20)

        # Generate the itinerary for the given number of days.
        days_plan = []
        for _ in range(self.days):
            mode = random.choice(valid_transports)
            departure_time = random.choice(possible_times)
            days_plan.append({
                "suggested_departure_time": departure_time,
                "suggested_transport_mode": mode
            })

        plan = {
            "travel_plan": {
                "days": days_plan,
                "reason": f"LLM response was invalid or failed parsing. Fallback plan used random default values for {self.days} days."
            }
        }
        return plan


    async def generate_plan(self) -> dict:
        """
        Generates a personalized travel plan by calling the LLM and performing the necessary validations.

        Up to 3 attempts are made to obtain a valid plan, validating:
          - The structure of 'travel_plan' (includes 'days' with exactly self.days elements and 'reason').
          - The content of each day (the keys 'suggested_departure_time' and 'suggested_transport_mode', valid transportation mode and time within range).

        If no valid plan is obtained after the attempts, a fallback plan with default values is used.
        """
        max_attempts = 3
        attempt = 0
        plan = None

        logger.warning(f"DEBUG: Agent_profile: ({self.agent_profile}) Days:({self.days}).")

        prompt = self.generate_plan_prompt()
        logger.warning(f"DEBUG prompt: {prompt}")

        while attempt < max_attempts:
            attempt += 1
            logger.warning(f"Attempt #{attempt} to get valid plan for {self.agent.name}")

            #start_time = time.time()
            # Call to the LLM (connection is opened and closed in each attempt)
            plan = await oneshot_request_llm(self.agent, config=self.agent.model_config, prompt=prompt)
            #end_time = time.time()

            # Validate the structure of the plan (includes correct number of days)
            if self.is_valid_plan_structure(plan, self.days):
                # Validate the content and logic of the plan
                if self.is_valid_plan_decision(plan, self.agent_profile, self.agent.actions, self.days):
                    first_day_mode = plan["travel_plan"]["days"][0]["suggested_transport_mode"].lower()
                    logger.warning(f"DEBUG Valid plan. First day transport mode: {first_day_mode}")

            logger.warning(f"DEBUG plan: {plan}")

            if plan and self.is_valid_plan_structure(plan, self.days) and self.is_valid_plan_decision(plan, self.agent_profile, self.agent.actions, self.days):
                break  # A valid plan has been obtained.
            else:
                plan = None  # Force the fallback for this attempt.

        # Fallback: if no valid plan is obtained after the attempts.
        if plan is None:
            plan = self.generate_random_plan()
            logger.warning(f"DEBUG Fallback plan: {plan}")

        return plan

    async def run(self):
        # If required, generate a detailed profile description.
        if self.profile_description:
            self.profile_described = describe_profile(
                self.agent_profile,
                ["demographics", "mobility_preferences", "environment"]
            )
        # Generate the validated plan.
        self.response = await self.generate_plan()
