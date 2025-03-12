import tkinter as tk
from tkinter import ttk, messagebox
import json
import os


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

        tk.Label(self.demographics_frame, text="Gender:", font=("Arial", 9, "bold"), bg="white").grid(row=1, column=0,
                                                                                                      sticky="w",
                                                                                                      padx=5, pady=2)
        self.gender_var = tk.StringVar()
        self.gender_dropdown = ttk.Combobox(self.demographics_frame, textvariable=self.gender_var, state="readonly")
        self.gender_dropdown["values"] = ["male", "female", "other"]
        self.gender_dropdown.grid(row=1, column=1, padx=5, pady=2)
        self.gender_dropdown.current(0)

        tk.Label(self.demographics_frame, text="N° of agents:", font=("Arial", 9, "bold"), bg="white").grid(row=2,
                                                                                                            column=0,
                                                                                                            sticky="w",
                                                                                                            padx=5,
                                                                                                            pady=2)
        self.agents_slider = tk.Scale(self.demographics_frame, from_=1, to=100, orient="horizontal", length=150)
        self.agents_slider.set(50)
        self.agents_slider.grid(row=2, column=1, padx=5, pady=2)

        # ========== BOTÓN "ADD" PARA VARIABLES PERSONALIZADAS ==========
        self.custom_field_frame = tk.Frame(self.demographics_frame, bg="white")
        self.custom_field_frame.grid(row=3, column=0, columnspan=2, padx=5, pady=5)

        self.add_button = tk.Button(self.demographics_frame, text="Add +", font=("Arial", 10, "bold"), bg="#D5DBDB",
                                    command=self.add_custom_field)
        self.add_button.grid(row=3, column=0, columnspan=1, padx=5, pady=5)

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

        # ========== BOTÓN "SAVE" ==========
        self.save_button = tk.Button(self.main_frame, text="Save", font=("Arial", 10, "bold"), bg="#AED6F1",
                                     command=self.save_profile)
        self.save_button.grid(row=2, column=0, columnspan=2, pady=10)

    def add_custom_field(self):
        """ Agrega un nuevo campo de variable si no se supera el límite """
        if len(self.custom_fields) < self.max_fields:
            row_index = len(self.custom_fields) + 5
            label_var = tk.Entry(self.demographics_frame, width=12)
            label_var.grid(row=row_index, column=0, padx=5, pady=2)

            value_var = tk.Entry(self.demographics_frame, width=20)
            value_var.grid(row=row_index, column=1, padx=5, pady=2)

            self.custom_fields.append((label_var, value_var))
        else:
            self.add_button.config(state="disabled")

    def save_profile(self):
        """ Guarda los datos del perfil en un archivo JSON considerando el número de agentes """

        profile_base_name = self.entry_name.get().strip()
        num_agents = self.agents_slider.get()

        if not profile_base_name:
            messagebox.showerror("Error", "Profile name is required.")
            return

        file_path = "profiles.json"

        # Cargar datos previos si el archivo existe
        if os.path.exists(file_path):
            with open(file_path, "r") as file:
                try:
                    existing_data = json.load(file)
                except json.JSONDecodeError:
                    existing_data = {}
        else:
            existing_data = {}

        # Generar múltiples perfiles según el número de agentes
        for i in range(1, num_agents + 1):
            profile_name = f"{profile_base_name}{i}"  # Ejemplo: Pedestrian1, Pedestrian2...

            profile_data = {
                "demographics": {
                    "gender": self.gender_var.get(),
                },
                "mobility_preferences": {pref: var.get() for pref, var in self.mobility_vars.items()},
                "environment": {
                    "arrival_time_limit": {
                        "type": self.arrival_type.get(),
                        "time": self.arrival_time.get(),
                        "purpose": self.purpose.get(),
                    },
                    "transport_options": [mode for mode, var in self.transport_options_vars.items() if var.get()]
                }
            }

            # Agregar los campos personalizados
            for label_entry, value_entry in self.custom_fields:
                label = label_entry.get().strip()
                value = value_entry.get().strip()
                if label and value:
                    profile_data["demographics"][label] = value

            # Agregar al JSON
            existing_data[profile_name] = profile_data

        # Guardar archivo actualizado
        with open(file_path, "w") as file:
            json.dump(existing_data, file, indent=4)

        messagebox.showinfo("Success", f"{num_agents} profiles saved successfully!")

        # Limpiar los campos después de guardar
        self.entry_name.delete(0, tk.END)
        self.gender_dropdown.current(0)
        self.agents_slider.set(50)
        self.arrival_time.delete(0, tk.END)
        self.purpose.delete(0, tk.END)

        for label_entry, value_entry in self.custom_fields:
            label_entry.destroy()
            value_entry.destroy()

        self.custom_fields.clear()
        self.add_button.config(state="normal")

        # Reiniciar selección de transporte
        for var in self.transport_options_vars.values():
            var.set(False)


