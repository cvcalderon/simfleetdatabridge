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
        # If no valid steps are provided, set default evaluation steps.
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
                # ,
                # {
                #     "step": 4,
                #     "title": "Verify Format and Structure",
                #     "description": (
                #         "Ensure that the generated plan complies with the required strictly JSON format, "
                #         "including a 'travel_plan' field that contains a 'days' array with the itinerary details and a 'reason' field."
                #     )
                # }
            ]

        # If forced_week is True, insert an exploratory step.
        if self.forced_week:
            arrival_type = self.agent_profile.get("environment", {}) \
                .get("arrival_time_limit", {}) \
                .get("type", "unspecified")
            exploratory_step = {
                "step": None,  # Will be re-assigned
                "title": "Exploratory Transportation Analysis",
                "description": (
                    "**Conduct an exploratory analysis of all available transport options as listed in 'transport_options'.** "
                    "Evaluate how each option fits with the user's arrival requirement, which is defined as "
                    f"'{arrival_type}'. Consider alternative departure times, and creative approaches to optimize the itinerary. "
                    "Examine potential benefits and drawbacks of each mode in an open-minded, investigative tone."
                )
            }
            # Insert the exploratory step after the Evaluate Transportation Options step.
            self.steps.insert(2, exploratory_step)

        # Re-assign step numbers for all evaluation steps.
        for idx, step in enumerate(self.steps, start=1):
            step["step"] = idx

        # Define the additional step that enforces strict JSON output.
        additional_step = {
            "step": len(self.steps) + 1,
            "title": "Output Strict JSON",
            "description": (
                "Respond ONLY with a valid JSON that matches the required structure. "
                "DO NOT add any extra text, code, explanations, or markdown."
            )
        }

        # Append the additional step.
        evaluation_steps = self.steps + [additional_step]

        # If the agent profile contains a non-empty "patterns" key, insert pattern analysis instructions
        if self.agent_profile.get("patterns"):
            pattern_step = (
                "Additionally, analyze and incorporate the mobility patterns provided in the 'patterns' field "
                "of the user profile. Use these patterns to further refine the itinerary recommendations and "
                "optimize the transportation choices."
            )
            # Insert the pattern instructions into the antepenultimate step (third-to-last step)
            if len(evaluation_steps) >= 3:
                evaluation_steps[-3]["description"] += " " + pattern_step

        # Create a default days plan structure based on self.days.
        days_plan = [
            {"day": f"Day {i + 1}", "transport_mode": "", "departure_time": "HH:MM AM/PM"}
            for i in range(self.days)
        ]

        # Define a concise task instruction.
        task_text = (
            f"Generate a personalized travel plan for the next {self.days} days, ensuring efficient transportation choices according to the user's profile."
        )

        prompt = {
            "user_profile": self.agent_profile,
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

        if self.profile_description:
            self.profile_described = describe_profile(self.agent_profile, ["demographics", "mobility_preferences", "environment", "transport_options"])

        prompt = self.generate_plan_prompt()
        # Call the LLM to get the decision using the constructed prompt.
        decision = await oneshot_request_llm(self.agent, config=self.agent.model_config, prompt=prompt)
        self.response = decision



