import json
from spade.behaviour import OneShotBehaviour
from loguru import logger
from simfleetdatabridge.utils import oneshot_request_llm

async def llm_agent_plan(agent, profile=None, prompt=None, forced_week=True):
    instance = LlmPlanningAgent(profile, prompt, forced_week)
    agent.add_behaviour(instance)
    await instance.join()
    return instance.response

class LlmPlanningAgent(OneShotBehaviour):
    def __init__(self, agent_profile, user_prompt, forced_week):
        super().__init__()
        self.steps = user_prompt  # Expected to be a list of steps (if provided)
        self.forced_week = forced_week
        self.agent_profile = agent_profile
        self.response = None
        self.days = 3  # Example: itinerary for 3 days (e.g., Monday - Wednesday)

    def generate_plan_prompt(self):
        # Define the additional step separately.
        additional_step = {
            "step": len(self.steps) + 1 if self.steps and isinstance(self.steps, list) else 1,
            "title": "Output Strict JSON",
            "description": (
                "Respond ONLY with a valid JSON that matches the required structure. "
                "DO NOT add any extra text, code, explanations, or markdown."
            )
        }

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
                        "**ONLY consider the transport modes listed in 'transport_options**."
                    )
                },
                {
                    "step": 3,
                    "title": "Design the Itinerary",
                    "description": (
                        f"Develop a detailed travel itinerary for the next {self.days} days that ensures the user meets "
                        "their required arrival times and preferences, logically organizing the route and chosen transportation methods."
                    )
                },
                {
                    "step": 4,
                    "title": "Verify Format and Structure",
                    "description": (
                        "Ensure that the generated plan complies with the required strictly JSON format, "
                        "including a 'travel_plan' field that contains a 'days' array with the itinerary details and a 'reason' field."
                    )
                }
            ]
            # Update the additional step number based on the default steps.
            additional_step["step"] = len(self.steps) + 1

        # Append the additional step to the evaluation steps.
        evaluation_steps = self.steps + [additional_step]

        # Create a default days plan structure based on self.days.
        days_plan = [
            {"day": f"Day {i+1}", "transport_mode": "", "departure_time": "HH:MM AM/PM"}
            for i in range(self.days)
        ]

        # Define the task instruction with explicit constraints.
        task_text = (
            f"Generate a personalized travel plan based on the user profile for the next {self.days} days. "
            "Analyze the demographics, mobility preferences, and environmental conditions to recommend an optimal itinerary and transportation option for each day. "
            "For each day, assign a recommended transport mode chosen exclusively from the 'transport_options' provided in the user profile, and suggest a precise departure time that ensures the user meets any required arrival deadlines. "
            "ONLY modes included in 'transport_options' should be considered. "
            "Prioritize efficient, sustainable, and on-time solutions."
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
        logger.warning("Text alert.")
        prompt = self.generate_plan_prompt()
        # Call the LLM to get the decision using the constructed prompt.
        decision = await oneshot_request_llm(self.agent, config=self.agent.model_config, prompt=prompt)
        self.response = decision



