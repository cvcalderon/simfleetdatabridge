from simfleet.common.lib.transports.models.taxi import TaxiAgent

class TaxiCostAgent(TaxiAgent):

    def __init__(self, agentjid, password, **kwargs):
        super().__init__(agentjid, password, **kwargs)

        self.cost = 0
        self.distance = 0

    def taxi_cost(self, distancia_metros):
        # Convertir la distancia de metros a kilómetros
        distancia_km = distancia_metros / 1000.0
        # Calcular el precio
        precio = distancia_km * 1.40
        self.cost = precio

    def set_distance(self, distance):
        self.distance = distance

    def get_distance(self):
        return self.distance