import pandas as pd
from loguru import logger
from tabulate import tabulate
from simfleet.metrics.basestatistics import BaseStatisticsClass
from simfleet.utils.statistics import Log
from datetime import datetime


class AgentsMobilityClass(BaseStatisticsClass):

    def run(self, events_log: Log) -> None:
        """
        Run the statistics generation process based on the agent type.

        Args:
            events_log (Log): A log containing all events from the simulation.
        """

        self.llm_pedestrian_metrics(events_log, "simfleet_pedestrian_metrics.json")
        self.taxi_customer_metrics(events_log, "simfleet_taxicustomer_metrics.json")

        self.print_stats()

    def llm_pedestrian_metrics(self, events_log: Log, file_path: str) -> None:
        """
        Extrae métricas específicas para agentes de tipo LlmPedestrian.

        Args:
            events_log (Log): Registro de eventos de la simulación.
            file_path (str): Ruta del archivo JSON donde se exportarán los datos.
        """
        # Filtrar eventos del agente LlmPedestrian
        filtered_events = events_log.filter(lambda event: event.class_type == "LlmPedestrianAgent" and
                                                          event.event_type in {"trip_completion",
                                                                               "travel_to_destination"})

        if not filtered_events.events:
            logger.warning("No relevant events found for LlmPedestrianAgent.")
            return

        # Convertir eventos a DataFrame
        event_fields = ["name", "timestamp", "event_type", "class_type"]
        details_fields = ["cost", "transport", "distance"]
        dataframe = filtered_events.to_dataframe(event_fields=event_fields, details_fields=details_fields)

        # Calcular tiempo de espera y tiempo de viaje
        dataframe["timestamp"] = pd.to_datetime(dataframe["timestamp"])
        waiting_time = dataframe.groupby("name")["timestamp"].min()  # Primer evento
        trip_start = dataframe[dataframe["event_type"] == "travel_to_destination"].groupby("name")["timestamp"].min()
        trip_end = dataframe[dataframe["event_type"] == "trip_completion"].groupby("name")["timestamp"].max()

        # Tiempo de espera (inicio del primer evento hasta que comienza el viaje)
        waiting_time = (trip_start - waiting_time)#.dt.total_seconds()
        # Tiempo de viaje (inicio hasta trip_completion)
        trip_time = (trip_end - trip_start)#.dt.total_seconds()

        # Unir métricas en un DataFrame final
        result_df = pd.DataFrame({
            "name": dataframe.groupby("name")["name"].first(),
            "class_type": dataframe.groupby("name")["class_type"].first(),
            "waiting_time": waiting_time,
            "trip_time": trip_time,
            "trip_completion_timestamp": trip_end,
            "cost": dataframe[dataframe["event_type"] == "trip_completion"].groupby("name")["cost"].first(),
            "transport": dataframe[dataframe["event_type"] == "trip_completion"].groupby("name")["transport"].first(),
            "distance": dataframe[dataframe["event_type"] == "trip_completion"].groupby("name")["distance"].first()
        }).fillna(0)

        # Exportar a JSON
        json_structure = {
            "GeneralMetrics": {
                "Class type": "LlmPedestrian",
                "Avg Waiting Time": f"{waiting_time.mean():.2f}",
                "Avg Trip Time": f"{trip_time.mean():.2f}"
            },
            "LlmPedestrian": result_df.to_dict(orient="records")
        }

        self.export_to_json(json_structure, file_path)

    def taxi_customer_metrics(self, events_log: Log, file_path: str) -> None:
        """
        Extrae métricas específicas para agentes de tipo TaxiCustomerAgent.

        Args:
            events_log (Log): Registro de eventos de la simulación.
            file_path (str): Ruta del archivo JSON donde se exportarán los datos.
        """
        # Filtrar eventos del agente TaxiCustomerAgent
        filtered_events = events_log.filter(lambda event: event.class_type == "TaxiCustomerAgent" and
                                                          event.event_type in {'customer_request', 'customer_pickup',
                                                                               'trip_completion'})

        if not filtered_events.events:
            logger.warning("No relevant events found for TaxiCustomerAgent.")
            return

        # Convertir eventos a DataFrame
        event_fields = ["name", "timestamp", "event_type", "class_type"]
        details_fields = ["cost", "transport", "distance"]
        dataframe = filtered_events.to_dataframe(event_fields=event_fields, details_fields=details_fields)

        # Convertir timestamps a formato datetime
        dataframe["timestamp"] = pd.to_datetime(dataframe["timestamp"])

        # Calcular tiempos de espera y viaje
        pivot_df = dataframe.pivot_table(index="name", columns="event_type", values="timestamp", aggfunc="first")
        waiting_time = (pivot_df["customer_pickup"] - pivot_df["customer_request"])#.dt.total_seconds()
        trip_time = (pivot_df["trip_completion"] - pivot_df["customer_pickup"])#.dt.total_seconds()

        # Obtener detalles del evento trip_completion
        trip_data = dataframe[dataframe["event_type"] == "trip_completion"].groupby("name")[
            "timestamp", "cost", "transport", "distance"].first()

        # Crear DataFrame final con métricas
        result_df = pd.DataFrame({
            "name": dataframe.groupby("name")["name"].first(),
            "class_type": dataframe.groupby("name")["class_type"].first(),
            "waiting_time": waiting_time.fillna(0),
            "trip_time": trip_time.fillna(0),
            "trip_completion_timestamp": trip_data["timestamp"],
            "cost": trip_data["cost"],
            "transport": trip_data["transport"],
            "distance": trip_data["distance"]
        }).fillna(0)

        # Exportar a JSON
        json_structure = {
            "GeneralMetrics": {
                "Class type": "TaxiCustomerAgent",
                "Avg Waiting Time": f"{waiting_time.mean():.2f}",
                "Avg Trip Time": f"{trip_time.mean():.2f}"
            },
            "TaxiCustomerAgent": result_df.to_dict(orient="records")
        }

        self.export_to_json(json_structure, file_path)

    def export_to_json(self, json_data: dict, file_path: str) -> None:
        """
        Export the final JSON structure to a JSON file.

        Args:
            json_data (dict): The data to be exported.
            file_path (str): Path where the JSON file will be saved.
        """
        with open(file_path, 'w') as f:
            import json
            json.dump(json_data, f, indent=4)
