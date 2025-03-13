import tkinter as tk
from tkinter import ttk, messagebox
from tkintermapview import TkinterMapView

class PrepareSimConfig(tk.Frame):
    def __init__(self, parent, tree_data):
        super().__init__(parent, bg="#EAF2F8")

        self.tree_data = tree_data  # Recibe datos desde LaunchGUI

        # Crear el widget del mapa
        self.map_widget = TkinterMapView(self, width=800, height=600, corner_radius=0)
        self.map_widget.pack(fill="both", expand=True)

        # Establecer ubicación inicial (ejemplo: Ciudad de Valencia)
        self.map_widget.set_position(39.4699, -0.3763)  # [Lat, Lon]
        self.map_widget.set_zoom(12)

        # Variables para almacenar puntos
        self.origin = None
        self.destination = None

        self.create_widgets()

        # Conectar eventos de clic
        self.map_widget.bind("<Button-1>", self.set_point)

    def set_point(self, event):
        # Obtener coordenadas donde se hizo clic
        lat, lon = self.map_widget.get_position_from_event(event)

        if self.origin is None:
            self.origin = (lat, lon)
            self.map_widget.set_marker(lat, lon, text="Origen")
            print(f"Origen: {self.origin}")
        elif self.destination is None:
            self.destination = (lat, lon)
            self.map_widget.set_marker(lat, lon, text="Destino")
            print(f"Destino: {self.destination}")

        # Si ya tenemos origen y destino, mostramos el perfil
        if self.origin and self.destination:
            print(f"Perfil generado: Origen {self.origin} → Destino {self.destination}")


    def create_widgets(self):
        """Muestra los datos de perfiles cargados desde CreateProfile."""
        tk.Label(self, text="Simulation Configuration", font=("Arial", 12, "bold"), bg="#F4F6F7").pack(pady=10)

        self.tree = ttk.Treeview(self, columns=("Name", "Age", "Gender"), show="headings")
        self.tree.pack(expand=True, fill="both")

        self.tree.heading("Name", text="Name")
        self.tree.heading("Age", text="Age")
        self.tree.heading("Gender", text="Gender")

        for profile in self.tree_data:
            self.tree.insert("", "end", values=(profile[0], profile[1], profile[3]))  # Name, Age, Gender