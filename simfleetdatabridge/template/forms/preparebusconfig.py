import tkinter as tk
import pandas as pd
from tkinter import ttk, messagebox, filedialog
from tkinter import filedialog, messagebox
from tkintermapview import TkinterMapView
from simfleetdatabridge.gtfs import read_gtfs_zip, transform_gtfs_to_json  # Asegúrate de que estén en el mismo paquete
import random

class PrepareTransportConfig(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg="#EAF2F8")

        self.lines_table = None
        self.selected_lines = set()

        # Variables internas
        self.gtfs_data = {}
        self.stops_markers = []
        self.bus_markers = []
        self.line_colors = {}
        self.color_palette = [
            "#e74c3c", "#3498db", "#2ecc71", "#f1c40f", "#9b59b6",
            "#1abc9c", "#e67e22", "#34495e", "#7f8c8d", "#ff5733"
        ]

        # Mapa
        self.map_widget = TkinterMapView(self, width=800, height=600, corner_radius=0)
        self.map_widget.pack(fill="both", expand=True)
        self.map_widget.set_position(39.4699, -0.3763)  # Por defecto: Valencia
        self.map_widget.set_zoom(12)

        # Widgets UI
        self.create_widgets()

    def create_widgets(self):
        """Crea botones para cargar GTFS y exportar JSON"""
        frame_controls = tk.Frame(self, bg="#F4F6F7")
        frame_controls.pack(fill="x", padx=10, pady=5)

        # Botón de carga GTFS
        self.btn_load_gtfs = tk.Button(frame_controls, text="Cargar GTFS", command=self.load_gtfs)
        self.btn_load_gtfs.grid(row=0, column=0, padx=5)

        # Botón de exportación
        self.btn_export_json = tk.Button(frame_controls, text="Exportar a JSON", command=self.export_json)
        self.btn_export_json.grid(row=0, column=1, padx=5)

        # Tabla de resumen de líneas
        columns = ("Line ID", "Name", "# Stops", "# Buses")
        self.lines_table = ttk.Treeview(self, columns=columns, show="headings", height=8)
        for col in columns:
            self.lines_table.heading(col, text=col)
        self.lines_table.pack(fill="both", padx=10, pady=5)

        # Botón para visualizar líneas seleccionadas
        self.btn_show_selected = tk.Button(self, text="Mostrar en mapa", command=self.show_selected_lines)
        self.btn_show_selected.pack(pady=5)

    def update_lines_table(self):
        """Llena la tabla con las líneas disponibles en el GTFS"""
        self.lines_table.delete(*self.lines_table.get_children())
        if not self.gtfs_data or "routes" not in self.gtfs_data:
            return

        stop_times = self.gtfs_data.get("stop_times", pd.DataFrame())
        trips = self.gtfs_data.get("trips", pd.DataFrame())

        for _, route in self.gtfs_data["routes"].iterrows():
            line_id = route["route_id"]
            name = route.get("route_short_name", "") or route.get("route_long_name", "")

            trip_ids = trips[trips["route_id"] == line_id]["trip_id"]
            stop_ids = stop_times[stop_times["trip_id"].isin(trip_ids)]["stop_id"].unique()

            #self.lines_table.insert("", "end", iid=line_id, values=(line_id, name, len(stop_ids), len(trip_ids)))
            self.lines_table.insert("", "end", iid=str(line_id), values=(line_id, name, len(stop_ids), len(trip_ids)))

    def show_selected_lines(self):
        """Obtiene las líneas seleccionadas y muestra paradas y buses en el mapa"""
        selected_items = self.lines_table.selection()
        if not selected_items:
            messagebox.showwarning("Selección vacía", "Seleccione al menos una línea.")
            return

        self.selected_lines = set(selected_items)
        self.clear_map()
        self.display_stops(self.selected_lines)
        self.display_buses(self.selected_lines)

    def load_gtfs(self):
        """Carga un archivo GTFS .zip y actualiza la tabla de líneas, sin mostrar en el mapa aún"""
        file_path = filedialog.askopenfilename(filetypes=[("GTFS ZIP files", "*.zip")])
        if not file_path:
            return

        try:
            self.gtfs_data = read_gtfs_zip(file_path)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer el archivo GTFS:\n{e}")
            return

        messagebox.showinfo("GTFS cargado", "Archivo GTFS cargado correctamente.")
        self.clear_map()
        self.update_lines_table()

    def clear_map(self):
        """Elimina todos los marcadores actuales del mapa"""
        for marker in self.stops_markers + self.bus_markers:
            marker.delete()
        self.stops_markers.clear()
        self.bus_markers.clear()
        self.map_widget.delete_all_path()

    def display_stops(self, lines_filter=None):
        """Dibuja las paradas en el mapa, filtradas por líneas si se indica"""
        if 'stops' not in self.gtfs_data or 'stop_times' not in self.gtfs_data or 'trips' not in self.gtfs_data:
            return

        stops_df = self.gtfs_data['stops']
        stop_times_df = self.gtfs_data['stop_times']
        trips_df = self.gtfs_data['trips']

        stop_line_map = {}
        for _, row in stop_times_df.iterrows():
            trip_id = row['trip_id']
            stop_id = row['stop_id']
            line_row = trips_df[trips_df['trip_id'] == trip_id]
            if not line_row.empty:
                line_id = str(line_row.iloc[0]['route_id'])  # Forzar a string aquí también
                stop_line_map.setdefault(stop_id, set()).add(line_id)

        for _, stop in stops_df.iterrows():
            stop_id = stop['stop_id']
            lines = set(str(l) for l in stop_line_map.get(stop_id, set()))
            if lines_filter and not lines.intersection(lines_filter):
                #print(f"Saltando parada: {stop['stop_name']} — líneas: {lines}, filtro: {lines_filter}")
                continue

            color = self.get_color_for_line(next(iter(lines)) if lines else "default")
            marker = self.map_widget.set_marker(
                stop['stop_lat'], stop['stop_lon'],
                text=stop['stop_name'],
                marker_color_circle=color,
                marker_color_outside=color
            )
            self.stops_markers.append(marker)

    def get_color_for_line(self, line_id):
        """Devuelve un color único para cada línea"""
        if line_id not in self.line_colors:
            index = len(self.line_colors) % len(self.color_palette)
            self.line_colors[line_id] = self.color_palette[index]
        return self.line_colors[line_id]

    def display_buses(self, lines_filter=None):
        if 'trips' not in self.gtfs_data or 'stop_times' not in self.gtfs_data or 'stops' not in self.gtfs_data:
            return

        trips_df = self.gtfs_data['trips']
        stop_times_df = self.gtfs_data['stop_times']
        stops_df = self.gtfs_data['stops']

        for _, trip in trips_df.iterrows():
            line_id = trip['route_id']
            if lines_filter and str(line_id) not in lines_filter:
                continue

            trip_id = trip['trip_id']
            trip_stop_times = stop_times_df[stop_times_df['trip_id'] == trip_id].sort_values(by='stop_sequence')
            if trip_stop_times.empty:
                continue

            first_stop_id = trip_stop_times.iloc[0]['stop_id']
            stop_info = stops_df[stops_df['stop_id'] == first_stop_id]
            if stop_info.empty:
                continue

            lat = stop_info.iloc[0]['stop_lat']
            lon = stop_info.iloc[0]['stop_lon']
            color = self.get_color_for_line(line_id)

            marker = self.map_widget.set_marker(
                lat, lon,
                text=f"Bus {trip_id}",
                marker_color_circle=color,
                marker_color_outside="#000000"
            )
            self.bus_markers.append(marker)

    def export_json(self):
        """Exporta el GTFS cargado a un archivo JSON compatible con SimFleet"""
        if not self.gtfs_data:
            messagebox.showerror("Error", "Primero debe cargar un archivo GTFS.")
            return

        file_path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if not file_path:
            return

        try:
            # Usamos el módulo gtfs para transformar y exportar
            transform_gtfs_to_json(self.gtfs_data, file_path, selected_lines=self.selected_lines)
            messagebox.showinfo("Exportación completa", f"Archivo exportado a:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Error al exportar", f"No se pudo exportar el archivo:\n{e}")
