import pandas as pd
from loguru import logger
from tabulate import tabulate
from simfleet.metrics.basestatistics import BaseStatisticsClass
from simfleet.utils.statistics import Log
from datetime import datetime
import json


class AgentsMobilityClass(BaseStatisticsClass):

    def run(self, events_log: Log) -> None:
        """
        Run the statistics generation process based on the agent type.

        Args:
            events_log (Log): A log containing all events from the simulation.
        """
        pedestrian_metrics = self.llm_pedestrian_metrics(events_log)
        taxi_customer_metrics = self.taxi_customer_metrics(events_log)

        # Generar y exportar JSON unificado
        self.generate_combined_metrics(pedestrian_metrics, taxi_customer_metrics, "simfleet_metrics.json")

    def llm_pedestrian_metrics(self, events_log: Log) -> dict:
        """
        Extrae métricas específicas para agentes de tipo LlmPedestrian.

        Args:
            events_log (Log): Registro de eventos de la simulación.

        Returns:
            dict: Diccionario con métricas procesadas.
        """
        # Filtrar eventos del agente LlmPedestrian
        filtered_events = events_log.filter(lambda event: event.class_type == "LlmPedestrianAgent" and
                                                          event.event_type in {"trip_completion",
                                                                               "travel_to_destination"})

        if not filtered_events.events:
            logger.warning("No relevant events found for LlmPedestrianAgent.")
            return {}

        # Convertir eventos a DataFrame
        event_fields = ["name", "timestamp", "event_type", "class_type"]
        details_fields = ["cost", "transport", "distance"]
        dataframe = filtered_events.to_dataframe(event_fields=event_fields, details_fields=details_fields)

        # Calcular tiempo de espera y tiempo de viaje
        waiting_time = dataframe.groupby("name")["timestamp"].min()
        trip_start = dataframe[dataframe["event_type"] == "travel_to_destination"].groupby("name")["timestamp"].min()
        trip_end = dataframe[dataframe["event_type"] == "trip_completion"].groupby("name")["timestamp"].max()

        # Calcular tiempos en segundos
        waiting_time = (trip_start - waiting_time)
        trip_time = (trip_end - trip_start)

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

        self.pedestrian_df = result_df.reset_index(drop=True)

        # Calculating general averages for the "GeneralMetrics" section
        avg_waiting_time = self.pedestrian_df["waiting_time"].mean()
        avg_trip_time = self.pedestrian_df["trip_time"].mean()

        return {
            "GeneralMetrics": {
                "Class type": "LlmPedestrian",
                "Avg Waiting Time": f"{avg_waiting_time:.2f} seconds",
                "Avg Trip Time": f"{avg_trip_time:.2f} seconds"
            },
            "LlmPedestrian": result_df.to_dict(orient="records")
        }

    def taxi_customer_metrics(self, events_log: Log) -> dict:
        """
        Extrae métricas específicas para agentes de tipo TaxiCustomerAgent.

        Args:
            events_log (Log): Registro de eventos de la simulación.

        Returns:
            dict: Diccionario con métricas procesadas.
        """
        # Filtrar eventos del agente TaxiCustomerAgent
        filtered_events = events_log.filter(lambda event: event.class_type == "TaxiCustomerAgent" and
                                                          event.event_type in {'customer_request', 'customer_pickup',
                                                                               'trip_completion'})

        if not filtered_events.events:
            logger.warning("No relevant events found for TaxiCustomerAgent.")
            return {}

        # Convertir eventos a DataFrame
        event_fields = ["name", "timestamp", "event_type", "class_type"]
        details_fields = ["cost", "transport", "distance"]
        dataframe = filtered_events.to_dataframe(event_fields=event_fields, details_fields=details_fields)

        # Calcular tiempos de espera y viaje
        pivot_df = dataframe.pivot_table(index="name", columns="event_type", values="timestamp", aggfunc="first")
        waiting_time = (pivot_df["customer_pickup"] - pivot_df["customer_request"])
        trip_time = (pivot_df["trip_completion"] - pivot_df["customer_pickup"])

        # Obtener detalles del evento trip_completion
        trip_data = dataframe[dataframe["event_type"] == "trip_completion"].groupby("name")[
            ["timestamp", "cost", "transport", "distance"]].first()

        # Crear DataFrame final con métricas
        result_df = pd.DataFrame({
            "name": dataframe.groupby("name")["name"].first(),
            "class_type": dataframe.groupby("name")["class_type"].first(),
            "waiting_time": waiting_time,
            "trip_time": trip_time,
            "trip_completion_timestamp": trip_data["timestamp"],
            "cost": trip_data["cost"],
            "transport": trip_data["transport"],
            "distance": trip_data["distance"]
        }).fillna(0)

        self.taxicustomer_df = result_df.reset_index(drop=True)

        # Calculating general averages for the "GeneralMetrics" section
        avg_waiting_time = self.taxicustomer_df["waiting_time"].mean()
        avg_trip_time = self.taxicustomer_df["trip_time"].mean()

        return {
            "GeneralMetrics": {
                "Class type": "TaxiCustomerAgent",
                "Avg Waiting Time": f"{avg_waiting_time:.2f} seconds",
                "Avg Trip Time": f"{avg_trip_time:.2f} seconds"
            },
            "TaxiCustomerAgent": result_df.to_dict(orient="records")
        }

    def generate_combined_metrics(self, pedestrian_metrics: dict, taxi_metrics: dict, file_path: str) -> None:
        """
        Combina métricas de LlmPedestrian y TaxiCustomerAgent en un solo JSON.

        Args:
            pedestrian_metrics (dict): Métricas de LlmPedestrian.
            taxi_metrics (dict): Métricas de TaxiCustomerAgent.
            file_path (str): Ruta del archivo JSON de salida.
        """
        combined_json = {
            "SimulationMetrics": {
                "Pedestrian": pedestrian_metrics.get("GeneralMetrics", {}),
                "TaxiCustomer": taxi_metrics.get("GeneralMetrics", {})
            },
            "DetailedMetrics": {
                "LlmPedestrianAgent": pedestrian_metrics.get("LlmPedestrian", []),
                "TaxiCustomerAgent": taxi_metrics.get("TaxiCustomerAgent", [])
            }
        }

        # Guardar en JSON
        with open(file_path, "w") as json_file:
            json.dump(combined_json, json_file, indent=4)

        logger.info(f"Combined JSON exported successfully to {file_path}")

