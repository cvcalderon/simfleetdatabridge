import tkinter as tk
from tkinter import ttk, messagebox
from tkintermapview import TkinterMapView
import random

class PrepareSimConfig(tk.Frame):
    def __init__(self, parent, tree_data):
        super().__init__(parent, bg="#EAF2F8")
        self.tree_data = {profile[0]: {"num_agents": int(profile[2]), "assigned": "No"} for profile in tree_data}
        self.bbox_points = []
        self.bbox_rectangle = None
        self.agents_data = {}

        # Lista de marcadores para poder eliminarlos después
        self.markers = []

        # Crear el mapa
        self.map_widget = TkinterMapView(self, width=800, height=600, corner_radius=0)
        self.map_widget.pack(fill="both", expand=True)
        self.map_widget.set_position(39.4699, -0.3763)  # Valencia
        self.map_widget.set_zoom(12)

        # Controles UI
        self.create_widgets()

    def create_widgets(self):
        """Crea la UI de generación de puntos y tabla de perfiles"""
        frame_controls = tk.Frame(self, bg="#F4F6F7")
        frame_controls.pack(fill="x", padx=10, pady=5)

        tk.Label(frame_controls, text="BoundingBox:", font=("Arial", 10, "bold"), bg="#F4F6F7").grid(row=0, column=0)
        self.btn_select_bbox = tk.Button(frame_controls, text="Select", command=self.select_bbox)
        self.btn_select_bbox.grid(row=0, column=1, padx=5)

        self.random_var = tk.BooleanVar()
        self.check_random = tk.Checkbutton(frame_controls, text="Random points", variable=self.random_var, bg="#F4F6F7")
        self.check_random.grid(row=0, column=2, padx=5)

        self.individual_var = tk.BooleanVar()
        self.check_individual = tk.Checkbutton(frame_controls, text="Individual", variable=self.individual_var, bg="#F4F6F7")
        self.check_individual.grid(row=0, column=3, padx=5)

        self.btn_add_agents = tk.Button(frame_controls, text="Add", command=self.generate_agents)
        self.btn_add_agents.grid(row=0, column=4, padx=5)

        # Tabla de perfiles
        self.tree = ttk.Treeview(self, columns=("Name", "Nº agents", "Assigned"), show="headings")
        self.tree.pack(expand=True, fill="both")

        self.tree.heading("Name", text="Name")
        self.tree.heading("Nº agents", text="Nº agents")
        self.tree.heading("Assigned", text="Assigned")

        self.update_profile_table()

        # Conectar eventos
        self.map_widget.add_left_click_map_command(self.map_click)

    def update_profile_table(self):
        """Actualiza la tabla de perfiles"""
        self.tree.delete(*self.tree.get_children())
        for profile_name, data in self.tree_data.items():
            self.tree.insert("", "end", values=(profile_name, data["num_agents"], data["assigned"]))

    def select_bbox(self):
        """Activa la selección de un Bounding Box"""
        self.bbox_points = []
        self.map_widget.delete_all_marker()
        self.map_widget.delete_all_path()
        self.markers.clear()
        self.map_widget.set_zoom(12)
        messagebox.showinfo("Bounding Box", "Haga clic en dos puntos para definir el Bounding Box.")

    def map_click(self, coordinates_tuple):
        """Guarda los puntos del BBox y dibuja el rectángulo"""
        if len(self.bbox_points) < 2:
            lat, lon = coordinates_tuple
            self.bbox_points.append((lat, lon))
            marker = self.map_widget.set_marker(lat, lon, text=f"P{len(self.bbox_points)}")
            self.markers.append(marker)

            if len(self.bbox_points) == 2:
                self.draw_bbox()

    def draw_bbox(self):
        """Dibuja el Bounding Box en el mapa"""
        if len(self.bbox_points) == 2:
            (lat1, lon1), (lat2, lon2) = self.bbox_points
            self.bbox_rectangle = [
                (lat1, lon1),
                (lat1, lon2),
                (lat2, lon2),
                (lat2, lon1),
                (lat1, lon1)
            ]
            self.map_widget.set_path(self.bbox_rectangle)

    def clear_previous_markers(self):
        """Elimina todos los marcadores anteriores antes de añadir nuevos"""
        for marker in self.markers:
            marker.delete()
        self.markers.clear()

    def generate_agents(self):
        """Genera puntos para los agentes dentro del Bounding Box"""
        if len(self.bbox_points) < 2:
            messagebox.showerror("Error", "Seleccione un Bounding Box primero.")
            return

        selected_item = self.tree.focus()
        if not selected_item:
            messagebox.showerror("Error", "Seleccione un perfil en la tabla.")
            return

        profile_data = self.tree.item(selected_item, "values")
        profile_name = profile_data[0]

        if self.tree_data[profile_name]["assigned"] == "Yes":
            if messagebox.askyesno("Reasignar puntos", f"El perfil {profile_name} ya tiene puntos asignados. ¿Desea reasignarlos?") == False:
                return

        num_agents = self.tree_data[profile_name]["num_agents"]

        lat_min, lon_min = min(self.bbox_points[0][0], self.bbox_points[1][0]), min(self.bbox_points[0][1], self.bbox_points[1][1])
        lat_max, lon_max = max(self.bbox_points[0][0], self.bbox_points[1][0]), max(self.bbox_points[0][1], self.bbox_points[1][1])

        # Eliminar puntos anteriores del mapa
        self.clear_previous_markers()

        # Limpiar datos previos en el diccionario
        self.agents_data[profile_name] = {}

        # Generación de puntos
        common_origin = (random.uniform(lat_min, lat_max), random.uniform(lon_min, lon_max))
        common_dest = (random.uniform(lat_min, lat_max), random.uniform(lon_min, lon_max))

        for i in range(1, num_agents + 1):
            if self.individual_var.get():
                origin = (random.uniform(lat_min, lat_max), random.uniform(lon_min, lon_max))
                destination = (random.uniform(lat_min, lat_max), random.uniform(lon_min, lon_max))
            else:
                origin, destination = common_origin, common_dest

            agent_key = f"{profile_name}{i}"
            self.agents_data[profile_name][agent_key] = {"Origen": origin, "Destino": destination}

            marker_o = self.map_widget.set_marker(*origin, text=f"{agent_key}-O")
            marker_d = self.map_widget.set_marker(*destination, text=f"{agent_key}-D")
            self.markers.extend([marker_o, marker_d])

        # Actualizar estado de asignación
        self.tree_data[profile_name]["assigned"] = "Yes"
        self.update_profile_table()

        print("Datos generados:", self.agents_data)
        messagebox.showinfo("Generación completada", f"Se generaron {num_agents} agentes.")


