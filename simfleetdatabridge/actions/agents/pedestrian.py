from spade.behaviour import State
from loguru import logger

from simfleet.utils.helpers import PathRequestException, AlreadyInDestination
from simfleet.common.lib.customers.models.pedestrian import PedestrianAgent

class LlmPedestrianAgent(PedestrianAgent):
    def __init__(self, agentjid, password):
        super().__init__(agentjid, password)
        self.distance = 0
        self.cost = 0

    def transport_cost(self, distancia_metros):
        # Convertir la distancia de metros a kilómetros
        distancia_km = distancia_metros / 1000.0
        # Calcular el precio consumo - (km * consumo_litros_por_100km) / 100 * precio diesel por litro
        precio = ((distancia_km * 4.5) / 100) * 1.25
        self.cost = precio

    def set_distance(self, distance):
        self.distance = distance

    def get_distance(self):
        return self.distance

class PedestrianStrategyBehaviour(State):
    """
    This class defines the vehicle's behavior strategy. It is designed to be extended to implement
    custom strategies for vehicle operations.

    Key Methods:
        - on_start(): Logs the initialization of the strategy.
        - planned_trip(): Defines how the vehicle should move to its destination.
    """

    async def on_start(self):
        """
            Logs the start of the vehicle's strategy behavior.
        """
        logger.debug("Strategy {} started in vehicle".format(type(self).__name__))

    async def planned_trip(self, dest=None):
        """
        Initiates the process for the vehicle to travel to the specified destination. The vehicle moves along the
        path, updating its position until it reaches its destination.

        Args:
            dest (list): The coordinates of the vehicle's destination.
        """
        logger.info(
            "Agent[{}]: The agent on route to destination ({})".format(self.agent.name, dest)
        )
        try:
            logger.debug("Agent[{}]: The agent move_to destination ({})".format(self.agent.name, dest))

            path, distance, duration = await self.agent.request_path(
                self.get("current_pos"), dest
            )
            self.agent.distance = distance

            await self.agent.move_to(dest)
        except AlreadyInDestination:
            logger.debug(
                "Agent[{}]: The agent is already in the destination' ({}) position. . .".format(
                    self.agent.name, dest
                )
            )

    async def run(self):
        """
            Abstract method that should be implemented in subclasses. This is where the specific strategy of the
            vehicle will be executed.
        """
        raise NotImplementedError