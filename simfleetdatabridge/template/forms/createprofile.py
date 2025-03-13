import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from collections import defaultdict
import json
import os
import re


class CreateProfile(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg="#EAF2F8")

        self.custom_fields = []  # Lista para almacenar campos dinámicos
        self.max_fields = 3  # Límite de campos personalizables
        self.transport_options = []  # Opciones de transporte seleccionadas

        self.create_widgets()

    def create_widgets(self):
        self.main_frame = tk.Frame(self, bg="white", padx=10, pady=10)
        self.main_frame.pack(expand=True, fill="both", padx=20, pady=20)

        # ========== DEMOGRAPHICS ==========
        self.demographics_frame = tk.LabelFrame(self.main_frame, text="Demographics", font=("Arial", 10, "bold"),
                                                bg="white")
        self.demographics_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

        tk.Label(self.demographics_frame, text="Name:", font=("Arial", 9, "bold"), bg="white").grid(row=0, column=0,
                                                                                                    sticky="w", padx=5,
                                                                                                    pady=2)
        self.entry_name = tk.Entry(self.demographics_frame, width=20)
        self.entry_name.grid(row=0, column=1, padx=5, pady=2)


        tk.Label(self.demographics_frame, text="Age:", font=("Arial", 9, "bold"), bg="white").grid(row=1, column=0,
                                                                                                    sticky="w", padx=5,
                                                                                                    pady=2)
        self.entry_age = tk.Entry(self.demographics_frame, width=20)
        self.entry_age.grid(row=1, column=1, padx=5, pady=2)


        tk.Label(self.demographics_frame, text="Gender:", font=("Arial", 9, "bold"), bg="white").grid(row=2, column=0,
                                                                                                      sticky="w",
                                                                                                      padx=5, pady=2)

        self.gender_var = tk.StringVar()
        self.gender_dropdown = ttk.Combobox(self.demographics_frame, textvariable=self.gender_var, state="readonly")
        self.gender_dropdown["values"] = ["male", "female", "other"]
        self.gender_dropdown.grid(row=2, column=1, padx=5, pady=2)
        self.gender_dropdown.current(0)

        tk.Label(self.demographics_frame, text="N° of agents:", font=("Arial", 9, "bold"), bg="white").grid(row=3,
                                                                                                            column=0,
                                                                                                            sticky="w",
                                                                                                            padx=5,
                                                                                                            pady=2)
        self.agents_slider = tk.Scale(self.demographics_frame, from_=1, to=100, orient="horizontal", length=150)
        self.agents_slider.set(50)
        self.agents_slider.grid(row=3, column=1, padx=5, pady=2)

        # ========== BOTÓN "ADD" PARA VARIABLES PERSONALIZADAS ==========
        self.custom_field_frame = tk.Frame(self.demographics_frame, bg="white")
        self.custom_field_frame.grid(row=4, column=0, columnspan=2, padx=5, pady=5)

        self.add_button = tk.Button(self.demographics_frame, text="Add +", font=("Arial", 10, "bold"), bg="#D5DBDB",
                                    command=self.add_custom_field)
        self.add_button.grid(row=4, column=0, columnspan=1, padx=5, pady=5)

        # ========== MOBILITY PREFERENCES ==========
        self.mobility_frame = tk.LabelFrame(self.main_frame, text="Mobility Preferences", font=("Arial", 10, "bold"),
                                            bg="white")
        self.mobility_frame.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")

        preferences = ["Eco consciousness", "Time sensitivity", "Comfort preference", "Budget sensitivity",
                       "Reliability sensitivity"]
        options = ["Not at all important", "Slightly important", "Moderately important", "Very important",
                   "Extremely important"]

        self.mobility_vars = {}

        for i, pref in enumerate(preferences):
            tk.Label(self.mobility_frame, text=f"{pref}:", font=("Arial", 9, "bold"), bg="white").grid(row=i, column=0,
                                                                                                       sticky="w",
                                                                                                       padx=5, pady=2)
            var = tk.StringVar()
            combobox = ttk.Combobox(self.mobility_frame, textvariable=var, state="readonly")
            combobox["values"] = options
            combobox.grid(row=i, column=1, padx=5, pady=2)
            combobox.current(0)
            self.mobility_vars[pref] = var

        # ========== PERSONAL ENVIRONMENT ==========
        self.environment_frame = tk.LabelFrame(self.main_frame, text="Personal Environment", font=("Arial", 10, "bold"),
                                               bg="white")
        self.environment_frame.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="nsew")

        # Arrival Time Limit
        tk.Label(self.environment_frame, text="Arrival time limit:", font=("Arial", 9, "bold"), bg="white").grid(row=0,
                                                                                                                 column=0,
                                                                                                                 columnspan=2,
                                                                                                                 sticky="w",
                                                                                                                 padx=5,
                                                                                                                 pady=2)

        tk.Label(self.environment_frame, text="Type:", font=("Arial", 9), bg="white").grid(row=1, column=0, sticky="w",
                                                                                           padx=5, pady=2)
        self.arrival_type = ttk.Combobox(self.environment_frame, state="readonly", values=["strict", "flexible"])
        self.arrival_type.grid(row=1, column=1, padx=5, pady=2)
        self.arrival_type.current(0)

        tk.Label(self.environment_frame, text="Time:", font=("Arial", 9), bg="white").grid(row=2, column=0, sticky="w",
                                                                                           padx=5, pady=2)
        self.arrival_time = tk.Entry(self.environment_frame, width=10)
        self.arrival_time.grid(row=2, column=1, padx=5, pady=2)

        tk.Label(self.environment_frame, text="Purpose:", font=("Arial", 9), bg="white").grid(row=3, column=0,
                                                                                              sticky="w", padx=5,
                                                                                              pady=2)
        self.purpose = tk.Entry(self.environment_frame, width=15)
        self.purpose.grid(row=3, column=1, padx=5, pady=2)

        # Transport Options (Seleccionable)
        tk.Label(self.environment_frame, text="Transport options:", font=("Arial", 9, "bold"), bg="white").grid(row=4,
                                                                                                                column=0,
                                                                                                                columnspan=2,
                                                                                                                sticky="w",
                                                                                                                padx=5,
                                                                                                                pady=2)

        self.transport_options_vars = {}
        transport_modes = ["walk", "taxi", "car", "bike"]

        self.transport_frame = tk.Frame(self.environment_frame, bg="white")
        self.transport_frame.grid(row=5, column=0, columnspan=2, padx=5, pady=2)

        for mode in transport_modes:
            var = tk.BooleanVar()
            chk = tk.Checkbutton(self.transport_frame, text=mode, variable=var, bg="white")
            chk.pack(side=tk.LEFT, padx=5)
            self.transport_options_vars[mode] = var


        # ========== BOTONES ==========
        self.button_frame = tk.Frame(self.main_frame, bg="white")
        self.button_frame.grid(row=2, column=0, columnspan=2, pady=10)

        self.load_button = tk.Button(self.button_frame, text="Load Profiles", command=self.load_profiles)
        self.load_button.pack(side=tk.LEFT, padx=5)

        self.generate_button = tk.Button(self.button_frame, text="Generate JSON", command=self.generate_json)
        self.generate_button.pack(side=tk.LEFT, padx=5)

        self.save_button = tk.Button(self.button_frame, text="Save", command=self.save_profile)
        self.save_button.pack(side=tk.LEFT, padx=5)

        self.delete_button = tk.Button(self.button_frame, text="Delete", command=self.delete_profiles)
        self.delete_button.pack(side=tk.LEFT, padx=5)

        # ========== TABLA DE PERFILES ==========
        self.create_profiles_table()

    def create_profiles_table(self):
        """Crea la tabla de perfiles en la interfaz con soporte para campos dinámicos."""

        # Definir columnas base
        self.columns = ["Name", "Age", "Nº agents", "Gender", "Eco", "Time", "Comfort", "Budget", "Reliability",
                        "Hour", "Purpose", "Transport options", "Select"]

        # Crear Treeview con las columnas base
        self.tree = ttk.Treeview(self.main_frame, columns=self.columns, show="headings", selectmode="extended")

        # Configurar encabezados y ancho de columnas
        for col in self.columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=120)

        # Agregar Treeview a la interfaz
        self.tree.grid(row=3, column=0, columnspan=2, pady=10, sticky="nsew")

        # Agregar barra de desplazamiento
        scrollbar = ttk.Scrollbar(self.main_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=3, column=2, sticky="ns")


    def add_custom_field(self):
        """ Agrega un nuevo campo personalizado si no se ha alcanzado el límite """
        if len(self.custom_fields) < self.max_fields:
            row_index = len(self.custom_fields) + 5
            label_entry = tk.Entry(self.demographics_frame, width=12)
            label_entry.grid(row=row_index, column=0, padx=5, pady=2)

            value_entry = tk.Entry(self.demographics_frame, width=20)
            value_entry.grid(row=row_index, column=1, padx=5, pady=2)

            self.custom_fields.append((label_entry, value_entry))

            # Agregar la columna dinámica a self.tree si aún no está
            custom_label = label_entry.get().strip()
            if custom_label and custom_label not in self.tree["columns"]:
                self.tree["columns"] = self.tree["columns"] + (custom_label,)
                self.tree.heading(custom_label, text=custom_label)
                self.tree.column(custom_label, width=100)
        else:
            self.add_button.config(state="disabled")

    def validate_time_format(self, time_str):
        """Verifica si el tiempo ingresado sigue el formato correcto (HH:MM AM/PM)."""
        time_pattern = r"^(0[1-9]|1[0-2]):[0-5][0-9] (AM|PM)$"
        return re.match(time_pattern, time_str) is not None

    def save_profile(self):
        """Guarda un perfil en la lista asegurando que todos los valores del formulario estén incluidos."""

        profile_name = self.entry_name.get().strip()
        profile_age = self.entry_age.get().strip()
        num_agents = self.agents_slider.get()
        gender = self.gender_var.get()
        arrival_time_value = self.arrival_time.get().strip()
        purpose_value = self.purpose.get().strip()

        if not profile_name:
            messagebox.showerror("Error", "Profile name is required.")
            return

        if not profile_age:
            messagebox.showerror("Error", "Profile age is required.")
            return

        # Validar formato de la hora
        if arrival_time_value and not self.validate_time_format(arrival_time_value):
            messagebox.showerror("Error", "Invalid time format! Please enter time as HH:MM AM/PM (e.g., 01:20 PM).")
            return

        # Obtener valores de movilidad
        eco = self.mobility_vars["Eco consciousness"].get()
        time_sens = self.mobility_vars["Time sensitivity"].get()
        comfort = self.mobility_vars["Comfort preference"].get()
        budget = self.mobility_vars["Budget sensitivity"].get()
        reliability = self.mobility_vars["Reliability sensitivity"].get()

        # Obtener opciones de transporte seleccionadas
        transport_selected = [mode for mode, var in self.transport_options_vars.items() if var.get()]
        transport_str = ", ".join(transport_selected) if transport_selected else "None"

        # Obtener valores de los campos personalizados
        custom_values = {}
        for label_entry, value_entry in self.custom_fields:
            label = label_entry.get().strip()
            value = value_entry.get().strip()
            if label and value:
                custom_values[label] = value

        # Crear perfil con todos los valores, incluyendo los personalizados
        profile_data = (
                           profile_name, profile_age, num_agents, gender, eco, time_sens, comfort, budget, reliability,
                           arrival_time_value,
                           purpose_value, transport_str
                       ) + tuple(custom_values.values())  # Añadir valores personalizados dinámicamente

        # Insertar perfil en la tabla con columnas dinámicas
        self.tree.insert("", "end", values=profile_data)

        # Limpiar los campos después de guardar
        self.entry_name.delete(0, tk.END)
        self.entry_age.delete(0, tk.END)
        self.gender_dropdown.current(0)
        self.agents_slider.set(50)
        self.arrival_time.delete(0, tk.END)
        self.purpose.delete(0, tk.END)

        for label_entry, value_entry in self.custom_fields:
            label_entry.delete(0, tk.END)
            value_entry.delete(0, tk.END)

        # Reiniciar selección de transporte
        for var in self.transport_options_vars.values():
            var.set(False)

    def load_profiles(self):
        """Carga perfiles desde un archivo JSON y los agrega a la tabla, incluyendo campos personalizados."""

        # Abrir el explorador de archivos para seleccionar un JSON
        file_path = filedialog.askopenfilename(
            title="Select a JSON file",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )

        if not file_path:  # Si el usuario cancela, no hacer nada
            return

        try:
            with open(file_path, "r") as file:
                profiles = json.load(file)
        except (json.JSONDecodeError, FileNotFoundError):
            messagebox.showerror("Error", "Invalid JSON file or file not found.")
            return

        # Diccionario para agrupar perfiles con el mismo nombre base
        grouped_profiles = defaultdict(lambda: {"num_agents": 0, "data": None})

        # Detectar todas las columnas personalizadas
        detected_custom_fields = set()

        for name, data in profiles.items():
            base_name = "".join(filter(lambda x: not x.isdigit(), name)).strip()
            grouped_profiles[base_name]["num_agents"] += 1  # Contar cuántos agentes hay
            grouped_profiles[base_name]["data"] = data  # Guardar datos de referencia

            # Detectar campos personalizados
            for key in data.get("demographics", {}):
                if key not in ["age", "gender"]:  # Excluir campos estándar
                    detected_custom_fields.add(key)

        # Limpiar la tabla antes de cargar nuevos perfiles
        for row in self.tree.get_children():
            self.tree.delete(row)

        # Agregar nuevas columnas personalizadas si aún no están en la tabla
        for custom_col in detected_custom_fields:
            if custom_col not in self.tree["columns"]:
                self.tree["columns"] += (custom_col,)
                self.tree.heading(custom_col, text=custom_col)
                self.tree.column(custom_col, width=120)

        # Insertar perfiles agrupados en la tabla
        for base_name, info in grouped_profiles.items():
            data = info["data"]
            num_agents = info["num_agents"]

            gender = data["demographics"].get("gender", "N/A")
            age = data["demographics"].get("age", "N/A")
            eco = data["mobility_preferences"].get("Eco consciousness", "N/A")
            time_sens = data["mobility_preferences"].get("Time sensitivity", "N/A")
            comfort = data["mobility_preferences"].get("Comfort preference", "N/A")
            budget = data["mobility_preferences"].get("Budget sensitivity", "N/A")
            reliability = data["mobility_preferences"].get("Reliability sensitivity", "N/A")
            arrival_time = data["environment"]["arrival_time_limit"].get("time", "N/A")
            purpose = data["environment"]["arrival_time_limit"].get("purpose", "N/A")
            transport_options = ", ".join(data["environment"].get("transport_options", [])) if data["environment"].get(
                "transport_options") else "None"

            # Obtener valores de campos personalizados
            custom_values = [data["demographics"].get(col, "N/A") for col in detected_custom_fields]

            # Agregar datos a la tabla
            profile_data = (base_name, age, num_agents, gender, eco, time_sens, comfort, budget, reliability,
                            arrival_time, purpose, transport_options) + tuple(custom_values)

            self.tree.insert("", "end", values=profile_data)

        messagebox.showinfo("Success", f"Profiles loaded successfully from {file_path}")

    def generate_json(self):
        """Genera múltiples perfiles en JSON según el número de agentes, incluyendo campos personalizados desde la tabla."""

        profiles = {}

        # Obtener todas las columnas del Treeview, excluyendo "Select" (el checkbox de la tabla)
        tree_columns = list(self.tree["columns"])
        if "Select" in tree_columns:
            tree_columns.remove("Select")

        # Determinar qué columnas son personalizadas (todas después de la columna "Transport options")
        base_columns_count = 12  # Número de columnas estándar hasta "Transport options"
        custom_columns = tree_columns[base_columns_count:]  # Obtener columnas personalizadas

        for item in self.tree.get_children():
            values = self.tree.item(item, "values")

            # Extraer valores base
            profile_base_name = values[0]  # Nombre base (ejemplo: "Pedestrian")
            profile_age = values[1]
            num_agents = int(values[2])  # Número de agentes
            gender = values[3]
            eco = values[4]
            time_sens = values[5]
            comfort = values[6]
            budget = values[7]
            reliability = values[8]
            arrival_time = values[9]
            purpose = values[10]
            transport_options = values[11].split(", ") if values[11] != "None" else []

            # Extraer los valores personalizados desde la tabla
            custom_fields = {}
            for i, col_name in enumerate(custom_columns):
                custom_fields[col_name] = values[i + base_columns_count]  # Tomar el valor correspondiente

            # Generar múltiples perfiles numerados si num_agents > 1
            for i in range(1, num_agents + 1):
                profile_name = f"{profile_base_name}{i}"  # Ejemplo: Pedestrian1, Pedestrian2...

                profiles[profile_name] = {
                    "demographics": {
                        "age": profile_age,
                        "gender": gender,
                        **custom_fields  # Incluir campos personalizados
                    },
                    "mobility_preferences": {
                        "Eco consciousness": eco,
                        "Time sensitivity": time_sens,
                        "Comfort preference": comfort,
                        "Budget sensitivity": budget,
                        "Reliability sensitivity": reliability,
                    },
                    "environment": {
                        "arrival_time_limit": {
                            "type": self.arrival_type.get(),
                            "time": arrival_time,
                            "purpose": purpose,
                        },
                        "transport_options": transport_options
                    }
                }

        # Pedir al usuario que seleccione dónde guardar el JSON
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All Files", "*.*")],
            title="Save JSON File"
        )

        if not file_path:
            return  # Si el usuario cancela, no hacer nada

        # Guardar JSON en el archivo seleccionado
        with open(file_path, "w") as file:
            json.dump(profiles, file, indent=4)

        messagebox.showinfo("Success", f"{len(profiles)} profiles saved successfully to {file_path}!")

    def delete_profiles(self):
        """Elimina los perfiles seleccionados de la lista."""
        selected_items = self.tree.selection()
        for item in selected_items:
            self.tree.delete(item)
