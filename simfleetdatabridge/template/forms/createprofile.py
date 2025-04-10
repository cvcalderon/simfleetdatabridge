import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from collections import defaultdict
import json
import os
import re


class CreateProfile(tk.Frame):
    def __init__(self, parent, main_app):
        super().__init__(parent, bg="#EAF2F8")

        self.main_app = main_app  # Referencia a LaunchGUI
        self.create_widgets()
        self.restore_tree_data()  # Restaurar datos al abrir

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

        # ========== CAMPOS OPCIONALES ==========
        tk.Label(self.demographics_frame, text="Education:", font=("Arial", 9, "bold"), bg="white").grid(row=4, column=0,
                                                                                                 sticky="w", padx=5,
                                                                                                 pady=2)
        self.entry_education = tk.Entry(self.demographics_frame, width=20)
        self.entry_education.grid(row=4, column=1, padx=5, pady=2)

        tk.Label(self.demographics_frame, text="Occupation:", font=("Arial", 9, "bold"), bg="white").grid(row=5, column=0,
                                                                                                  sticky="w", padx=5,
                                                                                                  pady=2)
        self.entry_occupation = tk.Entry(self.demographics_frame, width=20)
        self.entry_occupation.grid(row=5, column=1, padx=5, pady=2)

        tk.Label(self.demographics_frame, text="Annual Income:", font=("Arial", 9, "bold"), bg="white").grid(row=6, column=0,
                                                                                                     sticky="w", padx=5,
                                                                                                     pady=2)
        self.entry_income = tk.Entry(self.demographics_frame, width=20)
        self.entry_income.grid(row=6, column=1, padx=5, pady=2)


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
        transport_modes = ["walk", "taxi", "personal-car", "personal-bike"]

        self.transport_frame = tk.Frame(self.environment_frame, bg="white")
        self.transport_frame.grid(row=5, column=0, columnspan=2, padx=5, pady=2)

        for mode in transport_modes:
            var = tk.BooleanVar()
            chk = tk.Checkbutton(self.transport_frame, text=mode, variable=var, bg="white")
            chk.pack(side=tk.LEFT, padx=5)
            self.transport_options_vars[mode] = var

        # ========= BOTONES =========
        self.button_frame = tk.Frame(self.main_frame, bg="white")
        self.button_frame.grid(row=2, column=0, columnspan=2, pady=10)

        self.load_button = tk.Button(self.button_frame, text="Load Profiles", command=self.load_profiles)
        self.load_button.pack(side=tk.LEFT, padx=5)

        self.modify_button = tk.Button(self.button_frame, text="Modify", command=self.modify_profile, state=tk.DISABLED)
        self.modify_button.pack(side=tk.LEFT, padx=5)

        self.save_button = tk.Button(self.button_frame, text="Save", command=self.save_profile)
        self.save_button.pack(side=tk.LEFT, padx=5)

        self.delete_button = tk.Button(self.button_frame, text="Delete", command=self.delete_profiles)
        self.delete_button.pack(side=tk.LEFT, padx=5)

        self.generate_button = tk.Button(self.button_frame, text="Generate JSON", command=self.generate_json)
        self.generate_button.pack(side=tk.LEFT, padx=5)

        # ========= TABLA =========
        self.create_profiles_table()

        # ========= VARIABLE PARA GUARDAR ID DEL REGISTRO QUE SE MODIFICA =========
        self.selected_item_id = None

        # Vincular evento de selección de tabla a la función de habilitar el botón "Modify"
        self.tree.bind("<<TreeviewSelect>>", self.enable_modify_button)

    def create_profiles_table(self):
        """Crea la tabla de perfiles en la interfaz con soporte para campos dinámicos."""

        # Definir columnas base
        self.columns = ["Name", "Age", "Nº agents", "Gender", "Education", "Occupation", "Income", "Eco", "Time", "Comfort", "Budget", "Reliability",
                        "Hour", "Purpose", "Transport options"]

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

    def enable_modify_button(self, event):
        """Habilita el botón Modify cuando se selecciona un perfil en la tabla."""
        selected = self.tree.selection()
        if selected:
            self.modify_button.config(state=tk.NORMAL)
        else:
            self.modify_button.config(state=tk.DISABLED)

    def update_tree_data(self):
        """Guarda la información actual de la tabla en main_app.tree_data."""
        self.main_app.tree_data = []
        for item in self.tree.get_children():
            self.main_app.tree_data.append(self.tree.item(item, "values"))

    def restore_tree_data(self):
        """Restaura los perfiles guardados en la tabla cuando se vuelve a abrir."""
        for row in self.tree.get_children():
            self.tree.delete(row)  # Limpiar la tabla

        for profile in self.main_app.tree_data:
            self.tree.insert("", "end", values=profile)

    def validate_time_format(self, time_str):
        """Verifica si el tiempo ingresado sigue el formato correcto (HH:MM AM/PM)."""
        time_pattern = r"^(0[1-9]|1[0-2]):[0-5][0-9] (AM|PM)$"
        return re.match(time_pattern, time_str) is not None

    def save_profile(self):
        """Guarda un perfil nuevo o actualiza uno existente si se está modificando, con confirmación."""

        profile_name = self.entry_name.get().strip()
        profile_age = self.entry_age.get().strip()
        num_agents = self.agents_slider.get()
        gender = self.gender_var.get()
        arrival_time_value = self.arrival_time.get().strip()
        purpose_value = self.purpose.get().strip()

        education = self.entry_education.get().strip() if self.entry_education.get().strip() else "N/A"
        occupation = self.entry_occupation.get().strip() if self.entry_occupation.get().strip() else "N/A"
        annual_income = self.entry_income.get().strip() if self.entry_income.get().strip() else "N/A"

        if not profile_name:
            messagebox.showerror("Error", "Profile name is required.")
            return

        if not profile_age:
            messagebox.showerror("Error", "Profile age is required.")
            return

        if arrival_time_value and not self.validate_time_format(arrival_time_value):
            messagebox.showerror("Error", "Invalid time format! Please enter time as HH:MM AM/PM (e.g., 01:20 PM).")
            return

        eco = self.mobility_vars["Eco consciousness"].get()
        time_sens = self.mobility_vars["Time sensitivity"].get()
        comfort = self.mobility_vars["Comfort preference"].get()
        budget = self.mobility_vars["Budget sensitivity"].get()
        reliability = self.mobility_vars["Reliability sensitivity"].get()

        transport_selected = [mode for mode, var in self.transport_options_vars.items() if var.get()]
        transport_str = ", ".join(transport_selected) if transport_selected else "None"

        profile_data = (
            profile_name, profile_age, num_agents, gender, education, occupation, annual_income,
            eco, time_sens, comfort, budget, reliability,
            arrival_time_value, purpose_value, transport_str
        )

        if self.selected_item_id:
            # Preguntar antes de sobrescribir el perfil existente
            confirm = messagebox.askyesno("Confirm Modification",
                                          f"Are you sure you want to modify the profile '{profile_name}'?")
            if confirm:
                self.tree.item(self.selected_item_id, values=profile_data)
                self.selected_item_id = None  # Restablecer para futuras creaciones
            else:
                return  # Si el usuario cancela, no hacer nada
        else:
            # Guardar un nuevo perfil
            self.tree.insert("", "end", values=profile_data)

        self.update_tree_data()  # Guardar datos en LaunchGUI

        # Limpiar el formulario después de guardar
        self.entry_name.delete(0, tk.END)
        self.entry_age.delete(0, tk.END)
        self.gender_dropdown.current(0)
        self.agents_slider.set(50)
        self.arrival_time.delete(0, tk.END)
        self.purpose.delete(0, tk.END)
        self.entry_education.delete(0, tk.END)
        self.entry_occupation.delete(0, tk.END)
        self.entry_income.delete(0, tk.END)

        for var in self.transport_options_vars.values():
            var.set(False)

    def modify_profile(self):
        """Carga los datos del perfil seleccionado en el formulario para su modificación."""

        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showerror("Error", "Please select a profile to modify.")
            return

        self.selected_item_id = selected_item[0]  # Guardamos el ID del registro seleccionado
        values = self.tree.item(self.selected_item_id, "values")

        # Cargar valores en el formulario
        self.entry_name.delete(0, tk.END)
        self.entry_name.insert(0, values[0])

        self.entry_age.delete(0, tk.END)
        self.entry_age.insert(0, values[1])

        self.agents_slider.set(values[2])
        self.gender_dropdown.set(values[3])
        self.entry_education.delete(0, tk.END)
        self.entry_education.insert(0, values[4])

        self.entry_occupation.delete(0, tk.END)
        self.entry_occupation.insert(0, values[5])

        self.entry_income.delete(0, tk.END)
        self.entry_income.insert(0, values[6])

        self.mobility_vars["Eco consciousness"].set(values[7])
        self.mobility_vars["Time sensitivity"].set(values[8])
        self.mobility_vars["Comfort preference"].set(values[9])
        self.mobility_vars["Budget sensitivity"].set(values[10])
        self.mobility_vars["Reliability sensitivity"].set(values[11])

        self.arrival_time.delete(0, tk.END)
        self.arrival_time.insert(0, values[12])

        self.purpose.delete(0, tk.END)
        self.purpose.insert(0, values[13])

        # Restaurar las opciones de transporte
        transport_options = values[14].split(", ") if values[14] != "None" else []
        for mode, var in self.transport_options_vars.items():
            var.set(mode in transport_options)

        self.update_tree_data()

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


        for name, data in profiles.items():
            base_name = "".join(filter(lambda x: not x.isdigit(), name)).strip()
            grouped_profiles[base_name]["num_agents"] += 1  # Contar cuántos agentes hay
            grouped_profiles[base_name]["data"] = data  # Guardar datos de referencia



        # Insertar perfiles agrupados en la tabla
        for base_name, info in grouped_profiles.items():
            data = info["data"]
            num_agents = info["num_agents"]

            gender = data["demographics"].get("gender", "N/A")
            age = data["demographics"].get("age", "N/A")
            education = data["demographics"].get("education", "N/A")
            occupation = data["demographics"].get("occupation", "N/A")
            annual_income = data["demographics"].get("annual_income", "N/A")
            eco = data["mobility_preferences"].get("Eco consciousness", "N/A")
            time_sens = data["mobility_preferences"].get("Time sensitivity", "N/A")
            comfort = data["mobility_preferences"].get("Comfort preference", "N/A")
            budget = data["mobility_preferences"].get("Budget sensitivity", "N/A")
            reliability = data["mobility_preferences"].get("Reliability sensitivity", "N/A")
            arrival_time = data["environment"]["arrival_time_limit"].get("time", "N/A")
            purpose = data["environment"]["arrival_time_limit"].get("purpose", "N/A")
            transport_options = ", ".join(data["environment"].get("transport_options", [])) if data["environment"].get(
                "transport_options") else "None"

            # Agregar datos a la tabla
            profile_data = (base_name, age, num_agents, gender, education, occupation, annual_income, eco, time_sens, comfort, budget, reliability,
                            arrival_time, purpose, transport_options)

            self.tree.insert("", "end", values=profile_data)

            self.update_tree_data()  # Guardar datos en LaunchGUI

        messagebox.showinfo("Success", f"Profiles loaded successfully from {file_path}")

    def generate_json(self):
        """Genera múltiples perfiles en JSON según el número de agentes, excluyendo valores opcionales si están vacíos."""

        profiles = {}

        for item in self.tree.get_children():
            values = self.tree.item(item, "values")

            # Extraer valores base
            profile_base_name = values[0]  # Nombre base (ejemplo: "Pedestrian")
            profile_age = values[1]
            num_agents = int(values[2])  # Número de agentes
            gender = values[3]
            education = values[4].strip() if values[4] and values[4] != "N/A" else None
            occupation = values[5].strip() if values[5] and values[5] != "N/A" else None
            annual_income = values[6].strip() if values[6] and values[6] != "N/A" else None
            eco = values[7]
            time_sens = values[8]
            comfort = values[9]
            budget = values[10]
            reliability = values[11]
            arrival_time = values[12]
            purpose = values[13]
            transport_options = values[14].split(", ") if values[14] != "None" else []

            # Construir JSON dinámicamente, excluyendo valores vacíos
            demographics = {
                "age": profile_age,
                "gender": gender
            }
            if education:
                demographics["education"] = education
            if occupation:
                demographics["occupation"] = occupation
            if annual_income:
                demographics["annual_income"] = annual_income

            # Generar múltiples perfiles numerados si num_agents > 1
            for i in range(1, num_agents + 1):
                profile_name = f"{profile_base_name}{i}"  # Ejemplo: Pedestrian1, Pedestrian2...

                profiles[profile_name] = {
                    "demographics": demographics,  # Solo los valores opcionales que no sean vacíos
                    "mobility_preferences": {
                        "eco-consciousness": eco,
                        "time-sensitivity": time_sens,
                        "comfort-preference": comfort,
                        "budget-sensitivity": budget,
                        "reliability-sensitivity": reliability
                    },
                    "environment": {
                        "arrival_time_limit": {
                            "type": self.arrival_type.get(),
                            "time": arrival_time,
                            "purpose": purpose
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
        self.update_tree_data()
