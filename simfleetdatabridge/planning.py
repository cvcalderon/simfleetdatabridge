import json
from spade.behaviour import OneShotBehaviour
from loguru import logger
from simfleetdatabridge.utils import oneshot_request_llm, describe_profile


async def llm_agent_plan(agent, profile=None, prompt=None, forced_week=False, profile_description=False):
    instance = LlmPlanningAgent(profile, prompt, forced_week, profile_description)
    agent.add_behaviour(instance)
    await instance.join()
    return instance.response


class LlmPlanningAgent(OneShotBehaviour):
    def __init__(self, agent_profile, user_prompt, forced_week, profile_description):
        super().__init__()
        self.steps = user_prompt  # Expected to be a list of steps (if provided)
        self.forced_week = forced_week
        self.agent_profile = agent_profile
        self.profile_description = profile_description
        self.profile_described = None
        self.response = None
        self.days = 3  # Example: itinerary for 3 days (e.g., Monday - Wednesday)

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
                "step": None,  # Se reasignará la numeración posteriormente
                "title": "Exploratory Transportation Analysis",
                "description": (
                    "You MUST examine EACH transport mode listed in 'transport_options' SEPARATELY. "
                    f"For each option, evaluate how well it fits the user's needs: {arrival_type} arrival by '{arrival}', eco-consciousness, comfort, reliability, budget and time. "
                    "DO NOT assume a single best mode without comparing all options. Consider pros, cons, possible delays, creative uses, or combination strategies. "
                    f"Show clearly why each mode is or isn't suitable for each of the {self.days} days."
                )
            }
            # Insert exploratory step AFTER pattern analysis if patterns exist, otherwise after Evaluate Transportation Options
            insert_after_title = "Analyze Mobility Patterns" if self.agent_profile.get(
                "patterns") else "Evaluate Transportation Options"
            index = next((i for i, step in enumerate(self.steps) if step["title"] == insert_after_title), None)
            if index is not None:
                self.steps.insert(index + 1, exploratory_step)

        # If the profile contains "patterns", insert a dedicated step to analyze them.
        if self.agent_profile.get("patterns"):
            pattern_analysis_step = {
                "step": None,  # Will be reassigned later
                "title": "Analyze Mobility Patterns",
                "description": (
                    "Analyze the mobility patterns provided in the 'patterns' field of the user profile. "
                    "Use these patterns to further refine the itinerary recommendations and optimize transportation choices."
                )
            }
            # Insert it right after "Evaluate Transportation Options" or after the exploratory step if it exists.
            # Insert immediately after "Evaluate Transportation Options", even before the exploratory step if it exists.
            index = next((i for i, step in enumerate(self.steps) if step["title"] == "Evaluate Transportation Options"),
                         None)
            if index is not None:
                self.steps.insert(index + 1, pattern_analysis_step)

        # Reassign step numbers sequentially.
        for idx, step in enumerate(self.steps, start=1):
            step["step"] = idx

        # Define an additional step to ensure strict JSON output.
        additional_step = {
            "step": len(self.steps) + 1,
            "title": "Output Strict JSON",
            "description": (
                "Respond ONLY with a valid JSON that matches the required structure. "
                "DO NOT add any extra text, code, explanations, or markdown."
            )
        }

        # Build the final list of evaluation_steps.
        evaluation_steps = self.steps + [additional_step]

        # Create the structure for the itinerary days.
        days_plan = [
            {"day": f"Day {i + 1}", "transport_mode": "", "departure_time": "HH:MM AM/PM"}
            for i in range(self.days)
        ]

        # Concise instruction for the task.
        task_text = (
            f"Generate a personalized travel plan for the next {self.days} days, ensuring efficient transportation choices according to the user's profile."
        )

        # Define the profile to send: if profile_description is enabled, use the descriptive profile.
        if self.profile_description and self.profile_described:
            profile_input = {
                "profile": self.profile_described,
                "transport_options": self.agent_profile.get("transport_options", [])
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

    async def run(self):
        # Generate a descriptive profile if the flag is set.
        if self.profile_description:
            self.profile_described = describe_profile(
                self.agent_profile,
                ["demographics", "mobility_preferences", "environment", "transport_options"]
            )
        prompt = self.generate_plan_prompt()
        # Call the LLM to get the decision using the constructed prompt.
        decision = await oneshot_request_llm(self.agent, config=self.agent.model_config, prompt=prompt)
        self.response = decision


