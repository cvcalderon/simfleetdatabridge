import asyncio
from loguru import logger

from simfleet.utils.helpers import PathRequestException, AlreadyInDestination

from simfleet.utils.status import CUSTOMER_WAITING, CUSTOMER_MOVING_TO_DEST, CUSTOMER_IN_DEST
from simfleetdatabridge.actions.agents.pedestrian import PedestrianStrategyBehaviour
from simfleet.utils.abstractstrategies import FSMSimfleetBehaviour

################################################################
#                                                              #
#                 OneShot Pedestrian Strategy                  #
#                                                              #
################################################################

class OneShotPedestrianWaitingState(PedestrianStrategyBehaviour):
    async def on_start(self):
        await super().on_start()
        self.agent.status = CUSTOMER_WAITING
        logger.debug("{} in Pedestrian Waiting State".format(self.agent.jid))

    async def run(self):
        if self.agent.status != None and self.agent.status == CUSTOMER_WAITING:

            if self.agent.pedestrian_dest == None:
                self.agent.pedestrian_dest = self.agent.customer_dest
                #self.agent.set("speed_in_kmh", 300)

            try:
                logger.debug(
                    "Pedestrian {} continue the trip".format(
                        self.agent.name
                    )
                )
                await self.planned_trip(self.agent.pedestrian_dest)

                # New statistics
                # Event 1: Travel to destination
                self.agent.events_store.emit(
                    event_type="travel_to_destination",
                    details={}
                )

                self.set_next_state(CUSTOMER_MOVING_TO_DEST)
                return
            except PathRequestException:
                logger.error(
                    "Transport {} could not get a path to customer. Cancelling...".format(
                        self.agent.name
                    )
                )
                self.set_next_state(CUSTOMER_WAITING)
                return


class OneShotPedestrianMovingState(PedestrianStrategyBehaviour):
    async def on_start(self):
        await super().on_start()
        self.agent.status = CUSTOMER_MOVING_TO_DEST
        logger.debug("{} in Vehicle Moving State".format(self.agent.jid))

    async def run(self):
        try:

            if not self.agent.is_in_destination():
                await asyncio.sleep(1)
                self.set_next_state(CUSTOMER_MOVING_TO_DEST)
            else:
                # New statistics
                # Event 2: Trip completion
                self.agent.events_store.emit(
                    event_type="trip_completion",
                    details={"cost": 0, "transport": "walk", "distance": self.agent.get_distance()}
                )
                self.set_next_state(CUSTOMER_IN_DEST)

        except AlreadyInDestination:
            logger.warning(
                "Vehicle {} has arrived to destination: {}.".format(
                    self.agent.agent_id, self.agent.is_in_destination()
                )
            )

            # New statistics
            # Event 2: Trip completion
            self.agent.events_store.emit(
                event_type="trip_completion",
                details={"cost": 0, "transport": "walk", "distance": self.agent.get_distance()}
            )

            self.agent.status = CUSTOMER_IN_DEST
            self.set_next_state(CUSTOMER_IN_DEST)
            return
        except PathRequestException:
            logger.error(
                "Transport {} could not get a path to customer. Cancelling...".format(
                    self.agent.name
                )
            )
            self.agent.status = CUSTOMER_IN_DEST
            self.set_next_state(CUSTOMER_IN_DEST)
            return


class OneShotPedestrianInDestState(PedestrianStrategyBehaviour):
    async def on_start(self):
        await super().on_start()
        self.agent.status = CUSTOMER_IN_DEST
        logger.debug("{} in Vehicle Moving State".format(self.agent.jid))

    async def run(self):
        logger.info("{} arrived at its destination".format(self.agent.jid))


class FSMOneShotPedestrianBehaviour(FSMSimfleetBehaviour):
    def setup(self):
        # Create states
        self.add_state(CUSTOMER_WAITING, OneShotPedestrianWaitingState(), initial=True)
        self.add_state(CUSTOMER_MOVING_TO_DEST, OneShotPedestrianMovingState())
        self.add_state(CUSTOMER_IN_DEST, OneShotPedestrianInDestState())

        # Create transitions
        self.add_transition(
            CUSTOMER_WAITING, CUSTOMER_WAITING
        )  # waiting for messages
        self.add_transition(
            CUSTOMER_WAITING, CUSTOMER_MOVING_TO_DEST
        )  # accepted by customer

        self.add_transition(
            CUSTOMER_MOVING_TO_DEST, CUSTOMER_MOVING_TO_DEST
        )  # transport refused
        self.add_transition(
            CUSTOMER_MOVING_TO_DEST, CUSTOMER_WAITING
        )  # transport refused
        self.add_transition(
            CUSTOMER_MOVING_TO_DEST, CUSTOMER_IN_DEST
        )  # going to pick up customer



################################################################
#                                                              #
#            OneShot Bike Pedestrian Strategy                  #
#                                                              #
################################################################

class OneShotPedestrianBikeWaitingState(PedestrianStrategyBehaviour):
    async def on_start(self):
        await super().on_start()
        self.agent.status = CUSTOMER_WAITING
        logger.debug("{} in Pedestrian Waiting State".format(self.agent.jid))

    async def run(self):
        if self.agent.status != None and self.agent.status == CUSTOMER_WAITING:

            if self.agent.pedestrian_dest == None:
                self.agent.pedestrian_dest = self.agent.customer_dest
                #self.agent.set("speed_in_kmh", 900)

            try:
                logger.debug(
                    "Pedestrian {} continue the trip".format(
                        self.agent.name
                    )
                )
                await self.planned_trip(self.agent.pedestrian_dest)

                # New statistics
                # Event 1: Travel to destination
                self.agent.events_store.emit(
                    event_type="travel_to_destination",
                    details={}
                )

                self.set_next_state(CUSTOMER_MOVING_TO_DEST)
                return
            except PathRequestException:
                logger.error(
                    "Transport {} could not get a path to customer. Cancelling...".format(
                        self.agent.name
                    )
                )
                self.set_next_state(CUSTOMER_WAITING)
                return


class OneShotPedestrianBikeMovingState(PedestrianStrategyBehaviour):
    async def on_start(self):
        await super().on_start()
        self.agent.status = CUSTOMER_MOVING_TO_DEST
        logger.debug("{} in Vehicle Moving State".format(self.agent.jid))

    async def run(self):
        try:

            if not self.agent.is_in_destination():
                await asyncio.sleep(1)
                self.set_next_state(CUSTOMER_MOVING_TO_DEST)
            else:
                # New statistics
                # Event 2: Trip completion
                self.agent.events_store.emit(
                    event_type="trip_completion",
                    details={"cost": 0, "transport": "personal-bike", "distance": self.agent.get_distance()}
                )
                self.set_next_state(CUSTOMER_IN_DEST)

        except AlreadyInDestination:
            logger.warning(
                "Vehicle {} has arrived to destination: {}.".format(
                    self.agent.agent_id, self.agent.is_in_destination()
                )
            )

            # New statistics
            # Event 2: Trip completion
            self.agent.events_store.emit(
                event_type="trip_completion",
                details={"cost": 0, "transport": "personal-bike", "distance": self.agent.get_distance()}
            )

            self.agent.status = CUSTOMER_IN_DEST
            self.set_next_state(CUSTOMER_IN_DEST)
            return
        except PathRequestException:
            logger.error(
                "Transport {} could not get a path to customer. Cancelling...".format(
                    self.agent.name
                )
            )
            self.agent.status = CUSTOMER_IN_DEST
            self.set_next_state(CUSTOMER_IN_DEST)
            return


class OneShotPedestrianBikeInDestState(PedestrianStrategyBehaviour):
    async def on_start(self):
        await super().on_start()
        self.agent.status = CUSTOMER_IN_DEST
        logger.debug("{} in Vehicle Moving State".format(self.agent.jid))

    async def run(self):
        logger.info("{} arrived at its destination".format(self.agent.jid))


class FSMOneShotPedestrianBikeBehaviour(FSMSimfleetBehaviour):
    def setup(self):
        # Create states
        self.add_state(CUSTOMER_WAITING, OneShotPedestrianBikeWaitingState(), initial=True)
        self.add_state(CUSTOMER_MOVING_TO_DEST, OneShotPedestrianBikeMovingState())
        self.add_state(CUSTOMER_IN_DEST, OneShotPedestrianBikeInDestState())

        # Create transitions
        self.add_transition(
            CUSTOMER_WAITING, CUSTOMER_WAITING
        )  # waiting for messages
        self.add_transition(
            CUSTOMER_WAITING, CUSTOMER_MOVING_TO_DEST
        )  # accepted by customer

        self.add_transition(
            CUSTOMER_MOVING_TO_DEST, CUSTOMER_MOVING_TO_DEST
        )  # transport refused
        self.add_transition(
            CUSTOMER_MOVING_TO_DEST, CUSTOMER_WAITING
        )  # transport refused
        self.add_transition(
            CUSTOMER_MOVING_TO_DEST, CUSTOMER_IN_DEST
        )  # going to pick up customer



################################################################
#                                                              #
#            OneShot Car Pedestrian Strategy                  #
#                                                              #
################################################################

class OneShotPedestrianCarWaitingState(PedestrianStrategyBehaviour):
    async def on_start(self):
        await super().on_start()
        self.agent.status = CUSTOMER_WAITING
        logger.debug("{} in Pedestrian Waiting State".format(self.agent.jid))

    async def run(self):
        if self.agent.status != None and self.agent.status == CUSTOMER_WAITING:

            if self.agent.pedestrian_dest == None:
                self.agent.pedestrian_dest = self.agent.customer_dest
                #self.agent.set("speed_in_kmh", 2000)

            try:
                logger.debug(
                    "Pedestrian {} continue the trip".format(
                        self.agent.name
                    )
                )
                await self.planned_trip(self.agent.pedestrian_dest)

                # New statistics
                # Event 1: Travel to destination
                self.agent.events_store.emit(
                    event_type="travel_to_destination",
                    details={}
                )

                self.set_next_state(CUSTOMER_MOVING_TO_DEST)
                return
            except PathRequestException:
                logger.error(
                    "Transport {} could not get a path to customer. Cancelling...".format(
                        self.agent.name
                    )
                )
                self.set_next_state(CUSTOMER_WAITING)
                return


class OneShotPedestrianCarMovingState(PedestrianStrategyBehaviour):
    async def on_start(self):
        await super().on_start()
        self.agent.status = CUSTOMER_MOVING_TO_DEST
        logger.debug("{} in Vehicle Moving State".format(self.agent.jid))

    async def run(self):
        try:

            if not self.agent.is_in_destination():
                await asyncio.sleep(1)
                self.set_next_state(CUSTOMER_MOVING_TO_DEST)
            else:

                self.agent.transport_cost(self.agent.get_distance())

                # New statistics
                # Event 2: Trip completion
                self.agent.events_store.emit(
                    event_type="trip_completion",
                    details={"cost": self.agent.cost, "transport": "personal-car", "distance": self.agent.get_distance()}
                )
                self.set_next_state(CUSTOMER_IN_DEST)

        except AlreadyInDestination:
            logger.warning(
                "Vehicle {} has arrived to destination: {}.".format(
                    self.agent.agent_id, self.agent.is_in_destination()
                )
            )

            # New statistics
            # Event 2: Trip completion
            self.agent.events_store.emit(
                event_type="trip_completion",
                details={"cost": self.agent.cost, "transport": "personal-car", "distance": self.agent.get_distance()}
            )

            self.agent.status = CUSTOMER_IN_DEST
            self.set_next_state(CUSTOMER_IN_DEST)
            return
        except PathRequestException:
            logger.error(
                "Transport {} could not get a path to customer. Cancelling...".format(
                    self.agent.name
                )
            )
            self.agent.status = CUSTOMER_IN_DEST
            self.set_next_state(CUSTOMER_IN_DEST)
            return


class OneShotPedestrianCarInDestState(PedestrianStrategyBehaviour):
    async def on_start(self):
        await super().on_start()
        self.agent.status = CUSTOMER_IN_DEST
        logger.debug("{} in Vehicle Moving State".format(self.agent.jid))

    async def run(self):
        logger.info("{} arrived at its destination".format(self.agent.jid))


class FSMOneShotPedestrianCarBehaviour(FSMSimfleetBehaviour):
    def setup(self):
        # Create states
        self.add_state(CUSTOMER_WAITING, OneShotPedestrianCarWaitingState(), initial=True)
        self.add_state(CUSTOMER_MOVING_TO_DEST, OneShotPedestrianCarMovingState())
        self.add_state(CUSTOMER_IN_DEST, OneShotPedestrianCarInDestState())

        # Create transitions
        self.add_transition(
            CUSTOMER_WAITING, CUSTOMER_WAITING
        )  # waiting for messages
        self.add_transition(
            CUSTOMER_WAITING, CUSTOMER_MOVING_TO_DEST
        )  # accepted by customer

        self.add_transition(
            CUSTOMER_MOVING_TO_DEST, CUSTOMER_MOVING_TO_DEST
        )  # transport refused
        self.add_transition(
            CUSTOMER_MOVING_TO_DEST, CUSTOMER_WAITING
        )  # transport refused
        self.add_transition(
            CUSTOMER_MOVING_TO_DEST, CUSTOMER_IN_DEST
        )  # going to pick up customer
