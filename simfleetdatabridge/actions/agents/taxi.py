from simfleet.common.lib.transports.models.taxi import TaxiAgent

class TaxiCostAgent(TaxiAgent):

    def __init__(self, agentjid, password, **kwargs):
        super().__init__(agentjid, password, **kwargs)

        self.cost = 0
        self.distance = 0

    def taxi_cost(self, distancia_metros):
        # Convert the distance from meters to kilometers.
        distancia_km = distancia_metros / 1000.0

        # Tarifas
        bajada_bandera = 1.85
        precio_km = 1.24
        suplemento_app = 5.00
        precio = bajada_bandera + (distancia_km * precio_km) + suplemento_app
        self.cost = precio

    def set_distance(self, distance):
        self.distance = distance

    def get_distance(self):
        return self.distance