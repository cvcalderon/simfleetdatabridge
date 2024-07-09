import pandas as pd
import json
import zipfile


def read_gtfs_zip(zip_file_path):
    with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
        csv_files = [file for file in zip_ref.namelist() if file.endswith('.txt')]
        gtfs_data = {}
        for csv_file in csv_files:
            with zip_ref.open(csv_file) as file:
                gtfs_data[csv_file.split('.')[0]] = pd.read_csv(file)
        return gtfs_data


def transform_gtfs_to_json(zip_file_path, output_path):
    gtfs_data = read_gtfs_zip(zip_file_path)

    data = {
        "fleets": [],
        "transports": [],
        "customers": [],
        "stations": [],
        "vehicles": [],
        "stops": [],
        "lines": [],
        "simulation_name": "test_bus_line",
        "max_time": 10000,
        "verbose": 4,
        "fleetmanager_strategy": "simfleet.common.extensions.fleet.strategies.fleetmanager.DelegateRequestBehaviour",
        "transport_strategy": "simfleet.common.extensions.transports.strategies.bus.FSMBusStrategyBehaviour",
        "customer_strategy": "simfleet.common.extensions.customers.strategies.buscustomer.FSMBusCustomerStrategyBehaviour",
        "bus_stop_strategy": "simfleet.common.extensions.stations.models.busstop.BusStopStrategyBehaviour",
        "directory_strategy": "simfleet.common.agents.directory.DirectoryStrategyBehaviour",
        "station_strategy": "simfleet.common.extensions.stations.models.chargingstation.ChargingService",
        "vehicle_strategy": "simfleet.common.extensions.vehicles.strategies.vehicle.FSMOneShotVehicleStrategyBehaviour",
        "route_host": "http://morty.dsic.upv.es:5000/",
        "route_name": "route",
        "route_password": "route_passwd",
        "fleetmanager_name": "fleetmanager",
        "fleetmanager_password": "fleetmanager_passwd",
        "directory_name": "directory",
        "directory_password": "directory_passwd",
        "host": "localhost",
        "xmpp_port": 5222,
        "http_port": 9000,
        "http_ip": "localhost",
        "coords": [
            42.02822099999999,
            -93.610403
        ]
    }

    for _, agency in gtfs_data['agency'].iterrows():
        data['fleets'].append({
            "name": agency['agency_name'],
            "password": "secret",
            "fleet_type": "bus_line"
        })

    for _, stop in gtfs_data['stops'].iterrows():
        data['stops'].append({
            "id": stop['stop_id'],
            "name": stop['stop_name'],
            "password": "secret",
            "class": "simfleet.common.extensions.stations.models.busstop.BusStopAgent",
            "position": [stop['stop_lat'], stop['stop_lon']],
            "lines": []
        })

    for _, route in gtfs_data['routes'].iterrows():
        line_id = route['route_id']
        line_name = route['route_short_name'] if 'route_short_name' in route else line_id
        line_type = "circular"

        stops_in_line = gtfs_data['stop_times'][gtfs_data['stop_times']['trip_id'].isin(
            gtfs_data['trips'][gtfs_data['trips']['route_id'] == line_id]['trip_id']
        )]['stop_id'].unique()

        stops_positions = [
            [gtfs_data['stops'][gtfs_data['stops']['stop_id'] == stop_id].iloc[0]['stop_lat'],
             gtfs_data['stops'][gtfs_data['stops']['stop_id'] == stop_id].iloc[0]['stop_lon']]
            for stop_id in stops_in_line
        ]

        data['lines'].append({
            "id": line_id,
            "line_type": line_type,
            "stops": stops_positions
        })

        for stop_id in stops_in_line:
            for stop in data['stops']:
                if stop['id'] == stop_id:
                    stop['lines'].append(line_id)
                    break

    for _, trip in gtfs_data['trips'].iterrows():
        transport_name = f"bus{trip['trip_id']}"
        line_id = trip['route_id']
        initial_stop = gtfs_data['stop_times'][gtfs_data['stop_times']['trip_id'] == trip['trip_id']].iloc[0]
        initial_stop_position = [
            gtfs_data['stops'][gtfs_data['stops']['stop_id'] == initial_stop['stop_id']].iloc[0]['stop_lat'],
            gtfs_data['stops'][gtfs_data['stops']['stop_id'] == initial_stop['stop_id']].iloc[0]['stop_lon']
        ]

        agency_id = gtfs_data['routes'][gtfs_data['routes']['route_id'] == line_id].iloc[0]['agency_id']
        agency_name = gtfs_data['agency'][gtfs_data['agency']['agency_id'] == agency_id].iloc[0]['agency_name']

        data['transports'].append({
            "name": transport_name,
            "class": "simfleet.common.extensions.transports.models.bus.BusAgent",
            "optional": {
                "fleet": f"{agency_name}@localhost"
            },
            "password": "secret",
            "position": initial_stop_position,
            "fleet_type": "bus_line",
            "line": line_id,
            "speed": 350,
            "capacity": 60
        })

    with open(output_path, 'w') as json_file:
        json.dump(data, json_file, indent=4)
