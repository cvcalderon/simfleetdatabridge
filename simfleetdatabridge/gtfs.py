import pandas as pd
import json
import zipfile
import re
import unicodedata

def read_gtfs_zip(zip_file_path):
    with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
        csv_files = [file for file in zip_ref.namelist() if file.endswith('.txt')]
        gtfs_data = {}
        for csv_file in csv_files:
            with zip_ref.open(csv_file) as file:
                gtfs_data[csv_file.split('.')[0]] = pd.read_csv(file)
        return gtfs_data


def normalize_name(name):
    name = name.strip().lower()
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('utf-8')
    name = re.sub(r'\s+', '_', name)
    name = re.sub(r'[^a-z0-9_]', '', name)
    return name

# Part 1 and 2 of transform_gtfs_to_json - complete

def transform_gtfs_to_json(gtfs_data, output_path, selected_lines=None):

    for key in ["routes", "trips", "stop_times", "stops", "agency"]:
        if key in gtfs_data:
            for col in gtfs_data[key].columns:
                if gtfs_data[key][col].dtype == "int64":
                    gtfs_data[key][col] = gtfs_data[key][col].astype(str)

    if selected_lines:
        selected_lines = set(map(str, selected_lines))
        routes_df = gtfs_data["routes"][gtfs_data["routes"]["route_id"].isin(selected_lines)]
        trips_df = gtfs_data["trips"][gtfs_data["trips"]["route_id"].isin(selected_lines)]
        stop_times_df = gtfs_data["stop_times"][gtfs_data["stop_times"]["trip_id"].isin(trips_df["trip_id"])]
    else:
        routes_df = gtfs_data["routes"]
        trips_df = gtfs_data["trips"]
        stop_times_df = gtfs_data["stop_times"]

    data = {
        "fleets": [],
        "transports": [],
        "customers": [],
        "stations": [],
        "vehicles": [],
        "stops": [],
        "lines": [],
        "simulation_name": "bus",
        "max_time": 200,
        "transport_strategy": "simfleet.common.lib.transports.strategies.bus.FSMBusBehaviour",
        "customer_strategy": "simfleet.common.lib.customers.strategies.buscustomer.FSMBusCustomerBehaviour",
        "mobility_metrics": "simfleetdatabridge.actions.metrics.control.AgentsMobilityClass",
        "fleetmanager_name": "fleetmanager",
        "fleetmanager_password": "fleetmanager_passwd",
        "host": "localhost",
        "http_port": 9150,
        "http_ip": "localhost"
    }

    agency_name_map = {}
    for _, agency in gtfs_data["agency"].iterrows():
        raw_name = agency["agency_name"]
        norm_name = normalize_name(raw_name)
        agency_name_map[agency["agency_id"]] = norm_name
        data["fleets"].append({
            "name": norm_name,
            "password": "secret",
            "fleet_type": "bus"
        })

    stops_map = {}
    for _, stop in gtfs_data["stops"].iterrows():
        stops_map[stop["stop_id"]] = {
            "id": stop["stop_id"],
            "name": stop["stop_name"],
            "password": "secret",
            "class": "simfleet.common.lib.stations.models.busstop.BusStopAgent",
            "position": [float(stop["stop_lat"]), float(stop["stop_lon"])],
            "lines": [],
            "icon": "bus_stop"
        }

    for _, route in routes_df.iterrows():
        line_id = route["route_id"]
        line_type = "circular"
        trips_line = trips_df[trips_df["route_id"] == line_id]
        trip_ids = trips_line["trip_id"]
        stop_ids = stop_times_df[stop_times_df["trip_id"].isin(trip_ids)]["stop_id"].unique()

        stops_positions = []
        for stop_id in stop_ids:
            if stop_id in stops_map:
                stops_map[stop_id]["lines"].append(line_id)
                stops_positions.append(stops_map[stop_id]["position"])

        data["lines"].append({
            "id": line_id,
            "line_type": line_type,
            "stops": stops_positions
        })

    used_stops = {tuple(s) for line in data["lines"] for s in line["stops"]}
    data["stops"] = [stop for stop in stops_map.values() if tuple(stop["position"]) in used_stops]

    trips_grouped = trips_df.groupby("route_id")
    for route_id, trips in trips_grouped:
        agency_id = routes_df[routes_df["route_id"] == route_id].iloc[0]["agency_id"]
        agency_name = agency_name_map.get(agency_id, "default_fleet")

        for idx, (_, trip) in enumerate(trips.iterrows()):
            trip_id = trip["trip_id"]
            trip_stops = stop_times_df[stop_times_df["trip_id"] == trip_id].sort_values(by="stop_sequence")
            if trip_stops.empty:
                continue

            first_stop_id = trip_stops.iloc[0]["stop_id"]
            stop_row = gtfs_data["stops"][gtfs_data["stops"]["stop_id"] == first_stop_id]
            if stop_row.empty:
                continue

            pos = [float(stop_row.iloc[0]["stop_lat"]), float(stop_row.iloc[0]["stop_lon"])]
            delay = idx * 5  # minutos simulados

            data["transports"].append({
                "name": f"bus{trip_id}",
                "class": "simfleet.common.lib.transports.models.bus.BusAgent",
                "optional": {
                    "fleet": f"{agency_name}@localhost"
                },
                "password": "secret",
                "position": pos,
                "fleet_type": "bus",
                "line": route_id,
                "speed": 1500,
                "capacity": 60,
                "icon": "bus",
                "delay": delay
            })

    with open(output_path, 'w', encoding='utf-8') as json_file:
        json.dump(data, json_file, indent=4)


