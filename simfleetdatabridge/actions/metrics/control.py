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
        bus_customer_metrics = self.bus_customer_metrics(events_log)

        # Generar y exportar JSON unificado
        self.generate_combined_metrics(
            pedestrian_metrics,
            taxi_customer_metrics,
            bus_customer_metrics,
            "simfleet_metrics.json"
        )

    def llm_pedestrian_metrics(self, events_log: Log) -> dict:
        """
        Extract specific metrics for agents of type LlmPedestrian.

        Args:
            events_log (Log): Simulation event log.
        Returns:
            dict: Dictionary with processed metrics.
        """
        # Filter events of the agent LlmPedestrian
        filtered_events = events_log.filter(lambda event: event.class_type == "LlmPedestrianAgent" and
                                                          event.event_type in {"trip_completion",
                                                                               "travel_to_destination"})

        if not filtered_events.events:
            logger.warning("No relevant events found for LlmPedestrianAgent.")
            return {}

        # Convert events to DataFrame
        event_fields = ["name", "timestamp", "event_type", "class_type"]
        details_fields = ["cost", "transport", "distance"]
        dataframe = filtered_events.to_dataframe(event_fields=event_fields, details_fields=details_fields)

        # Calculate waiting time and travel time
        waiting_time = dataframe.groupby("name")["timestamp"].min()
        trip_start = dataframe[dataframe["event_type"] == "travel_to_destination"].groupby("name")["timestamp"].min()
        trip_end = dataframe[dataframe["event_type"] == "trip_completion"].groupby("name")["timestamp"].max()

        # Calculate times in seconds
        waiting_time = (trip_start - waiting_time)
        trip_time = (trip_end - trip_start)

        # Join metrics in a final DataFrame
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
        Extract specific metrics for agents of type TaxiCustomerAgent.

        Args:
            events_log (Log): Simulation event log.
        Returns:
            dict: Dictionary with processed metrics.
        """
        # Filter TaxiCustomerAgent events
        filtered_events = events_log.filter(lambda event: event.class_type == "TaxiCustomerAgent" and
                                                          event.event_type in {'customer_request', 'customer_pickup',
                                                                               'trip_completion'})

        if not filtered_events.events:
            logger.warning("No relevant events found for TaxiCustomerAgent.")
            return {}

        # Convert events to DataFrame
        event_fields = ["name", "timestamp", "event_type", "class_type"]
        details_fields = ["cost", "transport", "distance"]
        dataframe = filtered_events.to_dataframe(event_fields=event_fields, details_fields=details_fields)

        # Calculate waiting and travel times
        pivot_df = dataframe.pivot_table(index="name", columns="event_type", values="timestamp", aggfunc="first")
        waiting_time = (pivot_df["customer_pickup"] - pivot_df["customer_request"])
        trip_time = (pivot_df["trip_completion"] - pivot_df["customer_pickup"])

        # Get details of the trip_completion event
        trip_data = dataframe[dataframe["event_type"] == "trip_completion"].groupby("name")[
            ["timestamp", "cost", "transport", "distance"]].first()

        # Create final DataFrame with metrics
        result_df = pd.DataFrame({
            "name": dataframe.groupby("name")["name"].first(),
            "class_type": dataframe.groupby("name")["class_type"].first(),
            "waiting_time": waiting_time,
            "trip_time": trip_time,
            "trip_completion_timestamp": trip_data["timestamp"],
            "cost": trip_data["cost"],
            #"transport": trip_data["transport"],
            "transport": "taxi",
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

    def bus_customer_metrics(self, events_log: Log) -> dict:
        """
        Extract metrics for BusCustomerAgent agents with updated events:
        - Times based on wait_for_pickup → customer_pickup → trip_completion.
        - Trip data extracted from start_route
        """
        filtered_events = events_log.filter(lambda event: event.class_type == "BusCustomerAgent" and
                                                          event.event_type in {
                                                              "wait_for_pickup",
                                                              "customer_pickup",
                                                              "trip_completion",
                                                              "start_route"
                                                          }
                                            )

        if not filtered_events.events:
            logger.warning("No relevant events found for BusCustomerAgent.")
            return {}

        event_fields = ["name", "timestamp", "event_type", "class_type"]
        details_fields = ["cost", "transport", "distance"]
        df = filtered_events.to_dataframe(event_fields=event_fields, details_fields=details_fields)

        # Key times
        pivot_df = df.pivot_table(index="name", columns="event_type", values="timestamp", aggfunc="first")
        waiting_time = pivot_df["customer_pickup"] - pivot_df["wait_for_pickup"]
        trip_time = pivot_df["trip_completion"] - pivot_df["customer_pickup"]

        # start_route" event data
        start_data = df[df["event_type"] == "start_route"].groupby("name")[["cost", "transport", "distance"]].first()
        trip_completion_ts = df[df["event_type"] == "trip_completion"].groupby("name")["timestamp"].first()

        result_df = pd.DataFrame({
            "name": df.groupby("name")["name"].first(),
            "class_type": df.groupby("name")["class_type"].first(),
            "waiting_time": waiting_time,
            "trip_time": trip_time,
            "trip_completion_timestamp": trip_completion_ts,
            "cost": start_data["cost"],
            "transport": start_data["transport"],
            "distance": start_data["distance"]
        }).fillna(0)

        self.bus_customer_df = result_df.reset_index(drop=True)

        # General metrics
        avg_waiting = result_df["waiting_time"].mean()
        avg_trip = result_df["trip_time"].mean()

        return {
            "GeneralMetrics": {
                "Class type": "BusCustomerAgent",
                "Avg Waiting Time": f"{avg_waiting:.2f} seconds",
                "Avg Trip Time": f"{avg_trip:.2f} seconds"
            },
            "BusCustomerAgent": result_df.to_dict(orient="records")
        }

    def generate_combined_metrics(self, pedestrian_metrics: dict, taxi_metrics: dict, bus_metrics: dict,
                                  file_path: str) -> None:
        """
        Combines metrics from LlmPedestrian, TaxiCustomerAgent and BusCustomerAgent into a single JSON.

        Args:
            pedestrian_metrics (dict): LlmPedestrian metrics.
            taxi_metrics (dict): TaxiCustomerAgent metrics.
            bus_metrics (dict): BusCustomerAgent metrics.
            file_path (str): Output JSON file path.
        """
        combined_json = {
            "SimulationMetrics": {
                "Pedestrian": pedestrian_metrics.get("GeneralMetrics", {}),
                "TaxiCustomer": taxi_metrics.get("GeneralMetrics", {}),
                "BusCustomer": bus_metrics.get("GeneralMetrics", {})
            },
            "DetailedMetrics": {
                "LlmPedestrianAgent": pedestrian_metrics.get("LlmPedestrian", []),
                "TaxiCustomerAgent": taxi_metrics.get("TaxiCustomerAgent", []),
                "BusCustomerAgent": bus_metrics.get("BusCustomerAgent", [])
            }
        }

        # Guardar en JSON
        with open(file_path, "w") as json_file:
            json.dump(combined_json, json_file, indent=4)

        logger.info(f"Combined JSON exported successfully to {file_path}")


