import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkintermapview import TkinterMapView
import random
import json

class PrepareSimConfig(tk.Frame):
    def __init__(self, parent, tree_data):
        super().__init__(parent, bg="#EAF2F8")
        self.tree_data = {profile[0]: {"num_agents": int(profile[2]), "assigned": "No"} for profile in tree_data}
        self.agents_data = {}

        # Bounding Boxes
        self.bbox_origin_points = []
        self.bbox_dest_points = []
        self.bbox_rectangle_origin = None
        self.bbox_rectangle_dest = None

        # Estado interno de selección
        self.bbox_selection_type = None

        # Marcadores
        self.markers = []

        # Mapa
        self.map_widget = TkinterMapView(self, width=800, height=600, corner_radius=0)
        self.map_widget.pack(fill="both", expand=True)
        self.map_widget.set_position(39.4699, -0.3763)  # Valencia
        self.map_widget.set_zoom(12)

        self.create_widgets()

    def create_widgets(self):
        frame_controls = tk.Frame(self, bg="#F4F6F7")
        frame_controls.pack(fill="x", padx=10, pady=5)

        # Botones de selección de BBoxes
        self.btn_select_origin = tk.Button(frame_controls, text="Seleccionar BBox Origen", command=lambda: self.select_bbox("origin"))
        self.btn_select_origin.grid(row=0, column=0, padx=5)

        self.btn_select_dest = tk.Button(frame_controls, text="Seleccionar BBox Destino", command=lambda: self.select_bbox("dest"))
        self.btn_select_dest.grid(row=0, column=1, padx=5)

        self.random_var = tk.BooleanVar()
        self.check_random = tk.Checkbutton(frame_controls, text="Random points", variable=self.random_var, bg="#F4F6F7")
        self.check_random.grid(row=0, column=2, padx=5)

        self.individual_var = tk.BooleanVar()
        self.check_individual = tk.Checkbutton(frame_controls, text="Individual", variable=self.individual_var, bg="#F4F6F7")
        self.check_individual.grid(row=0, column=3, padx=5)

        self.btn_add_agents = tk.Button(frame_controls, text="Add", command=self.generate_agents)
        self.btn_add_agents.grid(row=0, column=4, padx=5)

        self.btn_export_json = tk.Button(frame_controls, text="Export to JSON", command=self.export_to_json)
        self.btn_export_json.grid(row=0, column=5, padx=5)

        # Tabla de perfiles
        self.tree = ttk.Treeview(self, columns=("Name", "Nº agents", "Assigned"), show="headings")
        self.tree.pack(expand=True, fill="both")
        self.tree.heading("Name", text="Name")
        self.tree.heading("Nº agents", text="Nº agents")
        self.tree.heading("Assigned", text="Assigned")

        self.update_profile_table()

        self.map_widget.add_left_click_map_command(self.map_click)

    def update_profile_table(self):
        self.tree.delete(*self.tree.get_children())
        for profile_name, data in self.tree_data.items():
            self.tree.insert("", "end", values=(profile_name, data["num_agents"], data["assigned"]))

    def select_bbox(self, selection_type):
        """Activa selección de bbox origen o destino"""
        self.bbox_selection_type = selection_type
        if selection_type == "origin":
            self.bbox_origin_points = []
            messagebox.showinfo("BBox Origen", "Haz clic en dos puntos para definir el Bounding Box de origen.")
        elif selection_type == "dest":
            self.bbox_dest_points = []
            messagebox.showinfo("BBox Destino", "Haz clic en dos puntos para definir el Bounding Box de destino.")


    def map_click(self, coordinates_tuple):
        """Guarda puntos del bbox según el tipo en selección y dibuja su rectángulo"""
        lat, lon = coordinates_tuple

        if self.bbox_selection_type == "origin":
            if len(self.bbox_origin_points) < 2:
                self.bbox_origin_points.append((lat, lon))
                marker = self.map_widget.set_marker(lat, lon, text=f"O{len(self.bbox_origin_points)}")
                self.markers.append(marker)
            if len(self.bbox_origin_points) == 2:
                self.draw_bbox("origin")

        elif self.bbox_selection_type == "dest":
            if len(self.bbox_dest_points) < 2:
                self.bbox_dest_points.append((lat, lon))
                marker = self.map_widget.set_marker(lat, lon, text=f"D{len(self.bbox_dest_points)}")
                self.markers.append(marker)
            if len(self.bbox_dest_points) == 2:
                self.draw_bbox("dest")

    def draw_bbox(self, bbox_type):
        """Dibuja el Bounding Box (origen o destino) como una ruta cerrada"""
        if bbox_type == "origin" and len(self.bbox_origin_points) == 2:
            points = self.bbox_origin_points
        elif bbox_type == "dest" and len(self.bbox_dest_points) == 2:
            points = self.bbox_dest_points
        else:
            return

        (lat1, lon1), (lat2, lon2) = points
        rectangle = [
            (lat1, lon1),
            (lat1, lon2),
            (lat2, lon2),
            (lat2, lon1),
            (lat1, lon1)
        ]

        path = self.map_widget.set_path(rectangle)

        if bbox_type == "origin":
            if self.bbox_rectangle_origin:
                self.bbox_rectangle_origin.delete()
            self.bbox_rectangle_origin = path
        elif bbox_type == "dest":
            if self.bbox_rectangle_dest:
                self.bbox_rectangle_dest.delete()
            self.bbox_rectangle_dest = path

    def clear_previous_markers(self):
        """Elimina solo los marcadores (no los BBoxes)"""
        for marker in self.markers:
            marker.delete()
        self.markers.clear()


    def generate_agents(self):
        """Genera puntos para los agentes usando BBox origen y destino"""
        if len(self.bbox_origin_points) < 2 or len(self.bbox_dest_points) < 2:
            messagebox.showerror("Error", "Debe definir ambos Bounding Boxes: origen y destino.")
            return

        selected_item = self.tree.focus()
        if not selected_item:
            messagebox.showerror("Error", "Seleccione un perfil en la tabla.")
            return

        profile_data = self.tree.item(selected_item, "values")
        profile_name = profile_data[0]

        if self.tree_data[profile_name]["assigned"] == "Yes":
            if not messagebox.askyesno("Reasignar puntos", f"El perfil {profile_name} ya tiene puntos asignados. ¿Desea reasignarlos?"):
                return

        num_agents = self.tree_data[profile_name]["num_agents"]
        self.clear_previous_markers()
        self.agents_data[profile_name] = {}

        # Bounding box de origen
        lat_min_o = min(self.bbox_origin_points[0][0], self.bbox_origin_points[1][0])
        lat_max_o = max(self.bbox_origin_points[0][0], self.bbox_origin_points[1][0])
        lon_min_o = min(self.bbox_origin_points[0][1], self.bbox_origin_points[1][1])
        lon_max_o = max(self.bbox_origin_points[0][1], self.bbox_origin_points[1][1])

        # Bounding box de destino
        lat_min_d = min(self.bbox_dest_points[0][0], self.bbox_dest_points[1][0])
        lat_max_d = max(self.bbox_dest_points[0][0], self.bbox_dest_points[1][0])
        lon_min_d = min(self.bbox_dest_points[0][1], self.bbox_dest_points[1][1])
        lon_max_d = max(self.bbox_dest_points[0][1], self.bbox_dest_points[1][1])

        common_origin = (random.uniform(lat_min_o, lat_max_o), random.uniform(lon_min_o, lon_max_o))
        common_dest = (random.uniform(lat_min_d, lat_max_d), random.uniform(lon_min_d, lon_max_d))

        for i in range(1, num_agents + 1):
            if self.individual_var.get():
                origin = (random.uniform(lat_min_o, lat_max_o), random.uniform(lon_min_o, lon_max_o))
                dest = (random.uniform(lat_min_d, lat_max_d), random.uniform(lon_min_d, lon_max_d))
            else:
                origin = common_origin
                dest = common_dest

            agent_key = f"{profile_name}{i}"
            self.agents_data[profile_name][agent_key] = {"Origen": origin, "Destino": dest}

            marker_o = self.map_widget.set_marker(*origin, text=f"{agent_key}-O")
            marker_d = self.map_widget.set_marker(*dest, text=f"{agent_key}-D")
            self.markers.extend([marker_o, marker_d])

        self.tree_data[profile_name]["assigned"] = "Yes"
        self.update_profile_table()
        print("Datos generados:", self.agents_data)
        messagebox.showinfo("Generación completada", f"Se generaron {num_agents} agentes.")

        # Opcional: limpiar los bounding boxes después de usar
        # self.bbox_rectangle_origin.delete()
        # self.bbox_rectangle_dest.delete()

    def export_to_json(self):
        if not self.agents_data:
            messagebox.showerror("Error", "No hay agentes generados para exportar.")
            return

        simulation_data = {
            "fleets": [],
            "transports": [],
            "customers": [],
            "stations": [],
            "stops": [],
            "lines": [],
            "vehicles": [],
            "simulation_name": "city",
            "max_time": 120,
            "transport_strategy": "simfleetdatabridge.actions.strategies.taxi.FSMTaxiBehaviour",
            "customer_strategy": "simfleet.common.lib.customers.strategies.taxicustomer.AcceptFirstRequestBehaviour",
            "fleetmanager_strategy": "simfleet.common.lib.fleet.strategies.fleetmanager.DelegateRequestBehaviour",
            "mobility_metrics": "simfleetdatabridge.actions.metrics.control.AgentsMobilityClass",
            "fleetmanager_name": "fleetmanager",
            "fleetmanager_password": "fleetmanager_passwd",
            "host": "localhost",
            "http_port": 9150,
            "http_ip": "localhost"
        }

        for profile_name, agents in self.agents_data.items():
            for agent_name, coords in agents.items():
                agent_data = {
                    "class": "simfleet.common.lib.customers.models.pedestrian.PedestrianAgent",
                    "strategy": "simfleet.common.lib.customers.strategies.pedestrian.FSMOneShotPedestrianBehaviour",
                    "position": list(coords["Origen"]),
                    "destination": list(coords["Destino"]),
                    "name": agent_name.lower(),
                    "password": "secret",
                    "speed": 300,
                    "fleet_type": "taxi",
                    "delay": 0
                }
                simulation_data["customers"].append(agent_data)

        file_path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if file_path:
            with open(file_path, "w", encoding="utf-8") as json_file:
                json.dump(simulation_data, json_file, indent=4)
            messagebox.showinfo("Exportación completa", f"Archivo guardado en: {file_path}")

