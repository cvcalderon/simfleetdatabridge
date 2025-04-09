import json
from spade.behaviour import OneShotBehaviour
from loguru import logger
from simfleetdatabridge.utils import (
    oneshot_request_llm,
    describe_short_memory,
    describe_plan,
    describe_profile
)

async def llm_agent_reflection(agent, profile=None, prompt=None, memory=None, next_day_plan=None, last_day_week=False):
    instance = LlmReflectionAgent(profile, prompt, memory, next_day_plan, last_day_week)
    agent.add_behaviour(instance)
    await instance.join()
    return instance.response

class LlmReflectionAgent(OneShotBehaviour):
    def __init__(self, agent_profile, user_prompt, memory, next_day_plan, last_day_week):
        super().__init__()
        self.steps = user_prompt  # Lista de pasos (puede venir vacía)
        self.memory = memory
        self.memory_description = True
        self.short_memory_described = None
        self.profile_described = None
        self.profile_description = True
        self.next_day_plan = next_day_plan
        self.agent_profile = agent_profile
        self.last_day_week = last_day_week
        self.response = None

    def generate_reflection_prompt(self, last_day=False):
        # Descripción del perfil
        profile_description = describe_profile(
            self.agent_profile,
            ["demographics", "mobility_preferences", "environment"]
        ) if self.profile_description else ""

        profile_input = {
            "profile": profile_description,
            "transport_options": self.agent_profile.get("environment", {}).get("transport_options", [])
        } if self.profile_description else {}

        # Descripción de memoria
        memory_summary = self.short_memory_described if self.memory_description else ""

        # Descripción del plan (solo si hay plan)
        plan_description = describe_plan(self.next_day_plan) if self.next_day_plan else ""

        # Paso adicional obligatorio
        additional_step = {
            "step": len(self.steps) + 1,
            "title": "Output Strict JSON",
            "description": (
                "Respond ONLY with a valid JSON that matches the required structure. "
                "DO NOT add any text, python code, explanation, or markdown."
            )
        }

        # Task y steps adaptados si es el último día de la semana
        if last_day:
            task = "Reflect on the last travel day of the week. Since there is no upcoming plan, no decision is needed."
            evaluation_steps = [step for step in self.steps if "Evaluate Upcoming Plan" not in step["title"]]
            output_structure = {
                "decision_context": {
                    "reflection": "",
                    "suggested_departure_time": None,
                    "suggested_transport_mode": None,
                    "decision_reason": "No decision needed. This was the last day of the week."
                }
            }
        else:
            task = "Reflect on the last travel day, evaluate the upcoming plan, and make a data-informed decision based on the user's context and constraints."
            evaluation_steps = self.steps + [additional_step]
            output_structure = {
                "decision_context": {
                    "reflection": "",
                    "suggested_departure_time": "HH:MM AM/PM",
                    "suggested_transport_mode": "Only modes included in 'transport_options'",
                    "decision_reason": "Explain the reasoning behind the decision, referencing profile constraints, historical performance, and whether a new mode is being tested."
                }
            }

        prompt = {
            "user_profile": profile_input,
            "memory": memory_summary,
            "next_day_plan": plan_description if not last_day else None,
            "instructions": {
                "task": task,
                "evaluation_steps": evaluation_steps,
                "output_requirements": {
                    "format": "**STRICT JSON ONLY**.",
                    "structure": output_structure
                }
            }
        }

        return json.dumps(prompt, indent=4)

    async def generate_reflection(self, last_day=False) -> dict:
        """
        Generates a reflection, with retries and validation.
        """
        max_attempts = 3
        attempt = 0
        reflection = None

        prompt = self.generate_reflection_prompt(last_day=last_day)
        logger.warning(f"Reflection prompt:\n{prompt}")

        while attempt < max_attempts:
            attempt += 1
            logger.warning(f"Attempt #{attempt} to get valid reflection for {self.agent.name}")
            result = await oneshot_request_llm(self.agent, config=self.agent.model_config, prompt=prompt)

            if self.is_valid_reflection_structure(result):
                reflection = result
                break
            else:
                logger.warning("Invalid reflection structure. Retrying...")

        if reflection is None:
            reflection = self.generate_fallback_reflection(last_day=last_day)

        return reflection

    def is_valid_reflection_structure(self, response: dict) -> bool:
        try:
            if not isinstance(response, dict):
                return False
            context = response.get("decision_context")
            if not isinstance(context, dict):
                return False
            required_keys = ["reflection", "suggested_departure_time", "suggested_transport_mode", "decision_reason"]
            return all(key in context for key in required_keys)
        except Exception as e:
            logger.error(f"Error validating reflection structure: {e}")
            return False

    def generate_fallback_reflection(self, last_day=False) -> dict:
        transport_mode = self.next_day_plan.get("travel", {}).get("transport_mode", "unknown") if self.next_day_plan else None
        departure_time = self.next_day_plan.get("travel", {}).get("departure_time", "08:00 AM") if self.next_day_plan else None

        return {
            "decision_context": {
                "reflection": "Unable to generate a detailed reflection at this time.",
                "suggested_departure_time": None if last_day else departure_time,
                "suggested_transport_mode": None if last_day else transport_mode,
                "decision_reason": (
                    "Fallback response. " +
                    ("This was the last day of the week." if last_day else f"The original plan was to use {transport_mode} at {departure_time}.")
                )
            }
        }

    async def generate_weekly_pattern_summary(self) -> str:
        """
        Uses the LLM to generate a weekly pattern summary in JSON format.
        """

        memory_entries = self.memory.get("short_memory", [])
        environment = self.agent_profile.get("environment", {})
        memory_text = "\n".join(describe_short_memory(memory_entries, environment))

        prompt = (
            "You are a mobility assistant. Analyze the user's weekly travel experiences listed below and "
            "summarize the overall mobility pattern.\n\n"
            "Requirements:\n"
            "- Your output MUST be a valid JSON.\n"
            "- Do NOT include any explanation or markdown.\n"
            "- **Only return the JSON**.\n"
            "- The JSON should have a single key: 'weekly_pattern_summary', with a short paragraph (max 150 words).\n\n"
            f"Weekly memory:\n{memory_text}\n\n"
            "Output:"
        )

        result = await oneshot_request_llm(self.agent, config=self.agent.model_config, prompt=prompt)

        if isinstance(result, dict) and "weekly_pattern_summary" in result:
            return result["weekly_pattern_summary"]
        else:
            logger.warning("The LLM did not return a valid weekly_pattern_summary. Using fallback.")
            return None


    async def run(self):
        environment = self.agent_profile.get("environment", {})
        short_memory = self.memory.get("short_memory", [])

        if self.memory_description:
            self.short_memory_described = describe_short_memory(short_memory=short_memory, environment=environment)

        if not self.steps or not isinstance(self.steps, list):
            self.steps = [
                {
                    "step": 1,
                    "title": "Analyze Last Travel Day",
                    "description": "Review the last recorded travel experience from the user's memory. Consider the mode of transport, departure and arrival time, travel duration, and whether the user arrived late or on time."
                },
                {
                    "step": 2,
                    "title": "Reflect on Its Effectiveness",
                    "description": "Based on the previous day's experience, evaluate how effective the decision was. Was the user late? Was the choice of transport aligned with the user's preferences and constraints?"
                },
                {
                    "step": 3,
                    "title": "Evaluate Upcoming Plan",
                    "description": "Analyze the travel plan scheduled for the next day. Consider if it should be adjusted or maintained based on the user's historical data and priorities."
                },
                {
                    "step": 4,
                    "title": "Account for External Factors (if any)",
                    "description": "Consider possible external factors that may influence the user's mobility (e.g., weather, public holidays, strikes, price fluctuations, new mobility policies). If no data is provided, proceed with the available information."
                },
                {
                    "step": 5,
                    "title": "Make and Justify a Decision",
                    "description": "Propose the most suitable mode of transport and departure time for the next day. **ONLY consider the transport modes listed in 'transport_options'**. Justify your decision based on the user profile, recent experience, and the current plan. If changing the plan, explain clearly why."
                }
            ]

        if self.last_day_week:
            reflection = await self.generate_reflection(last_day=True)
            summary = await self.generate_weekly_pattern_summary()
            self.response = {
                "decision_context": reflection["decision_context"],
                "weekly_pattern_summary": summary
            }
        else:
            self.response = await self.generate_reflection()



