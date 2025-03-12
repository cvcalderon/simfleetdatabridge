import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import font
import simfleetdatabridge.template.utils as utils


class LaunchGUI(tk.Tk):

    def __init__(self):
        super().__init__()

        self.config_window()
        self.panels()
        self.upper_bar_controls()
        self.side_menu_controls()
        self.menu_visible = True  # Estado del menú lateral
        self.profile_expanded = False  # Estado del submenú "Profile"

    def config_window(self):
        self.title("SimfleetAI")
        self.iconbitmap(utils.absolute_path("./images/icon.ico"))
        w, h = 1024, 600
        utils.center_window(self, app_width=w, app_height=h)

    def panels(self):
        self.upper_bar = tk.Frame(self, bg=utils.COLOR_UPPER_BAR, height=50)
        self.upper_bar.pack(side=tk.TOP, fill='x')

        self.side_menu = tk.Frame(self, bg=utils.COLOR_SIDE_MENU_COLOR, width=150)
        self.side_menu.pack(side=tk.LEFT, fill='y')

        self.principal_body = tk.Frame(self, bg=utils.COLOR_PRINCIPAL_BODY)
        self.principal_body.pack(side=tk.RIGHT, fill='both', expand=True)

    def upper_bar_controls(self):
        universal_font = font.Font(family="DejaVu Sans", size=12)

        # Title label
        self.labelTitle = tk.Label(self.upper_bar, text="SimfleetAI", fg="#fff",
                                   font=("Noto Sans", 15), bg=utils.COLOR_UPPER_BAR, pady=10, width=14)
        self.labelTitle.pack(side=tk.LEFT, padx=10)

        # Side menu button ☰ (Unicode)
        self.sideMenuButton = tk.Button(self.upper_bar, text=" ☰ ", font=universal_font,
                                        command=self.toggle_panel, bd=0, bg=utils.COLOR_UPPER_BAR, fg="white")
        self.sideMenuButton.pack(side=tk.LEFT)

        # Contact Label
        self.labelContact = tk.Label(self.upper_bar, text="Contact: ccalderon@upv.es",
                                     fg="#fff", font=("Noto Sans", 10), bg=utils.COLOR_UPPER_BAR, padx=10, width=20)
        self.labelContact.pack(side=tk.RIGHT)

    def side_menu_controls(self):
        menu_width = 20
        menu_height = 2
        universal_font = font.Font(family="DejaVu Sans", size=12)

        # Botón "Profiles"
        self.buttonProfiles = tk.Button(self.side_menu, text="👤 Profiles", anchor="w", font=universal_font,
                                       bd=0, bg=utils.COLOR_SIDE_MENU_COLOR, fg="white",
                                       width=menu_width, height=menu_height, command=self.toggle_profile_menu)
        self.buttonProfiles.pack(side=tk.TOP, pady=2, padx=5, fill="x")
        self.bind_hover_events(self.buttonProfiles)

        # Frame para submenú de "Profile"
        self.profile_submenu_frame = tk.Frame(self.side_menu, bg=utils.COLOR_SIDE_MENU_COLOR)
        # Inicialmente oculto, no se usa pack()

        # Botones de subcategoría
        self.buttonCreateProfile = tk.Button(self.profile_submenu_frame, text="   🧑🏻‍ Create", anchor="w",
                                             font=universal_font,
                                             bd=0, bg=utils.COLOR_SIDE_MENU_COLOR, fg="white",
                                             width=menu_width - 2, height=menu_height, command=self.open_create_profile)

        self.buttonUpdateProfile = tk.Button(self.profile_submenu_frame, text="   🔧 Update", anchor="w",
                                             font=universal_font,
                                             bd=0, bg=utils.COLOR_SIDE_MENU_COLOR, fg="white",
                                             width=menu_width - 2, height=menu_height, command=self.update_profile)

        # Botón "Simulation"
        self.buttonSimulation = tk.Button(self.side_menu, text="⚙️ Simulation", anchor="w", font=universal_font,
                                          bd=0, bg=utils.COLOR_SIDE_MENU_COLOR, fg="white",
                                          width=menu_width, height=menu_height, command=self.open_simulation)
        self.buttonSimulation.pack(side=tk.TOP, pady=2, padx=5, fill="x")
        self.bind_hover_events(self.buttonSimulation)

    def bind_hover_events(self, button):
        button.bind("<Enter>", lambda event: self.on_enter(event, button))
        button.bind("<Leave>", lambda event: self.on_leave(event, button))

    def on_enter(self, event, button):
        button.config(bg=utils.COLOR_MENU_CURSOR_ENTER, fg='white')

    def on_leave(self, event, button):
        button.config(bg=utils.COLOR_SIDE_MENU_COLOR, fg='white')

    def toggle_panel(self):
        if self.menu_visible:
            self.side_menu.pack_forget()
        else:
            self.side_menu.pack(side=tk.LEFT, fill='y')
        self.menu_visible = not self.menu_visible

    def toggle_profile_menu(self):
        """Expande o contrae el menú de 'Profile'"""
        if self.profile_expanded:
            self.profile_submenu_frame.pack_forget()
        else:
            # Se empaqueta el frame justo después de "Profile" y antes de "Simulation"
            self.profile_submenu_frame.pack(side=tk.TOP, fill="x", before=self.buttonSimulation)
            self.buttonCreateProfile.pack(side=tk.TOP, padx=15, fill="x")  # Sangría visual
            self.buttonUpdateProfile.pack(side=tk.TOP, padx=15, fill="x")  # Sangría visual
        self.profile_expanded = not self.profile_expanded

    # Métodos de acción
    def open_create_profile(self):
        """Carga la interfaz de creación de perfiles en el área principal"""
        for widget in self.principal_body.winfo_children():
            widget.destroy()  # Limpiar el contenido anterior

        CreateProfile(self.principal_body).pack(expand=True, fill="both")

    def update_profile(self):
        print("Update Profile")

    def open_simulation(self):
        print("Simulation Opened")


class CreateProfile(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg="#EAF2F8")

        self.custom_fields = []  # Lista para almacenar campos dinámicos
        self.max_fields = 3  # Límite de campos personalizables

        self.create_widgets()

    def create_widgets(self):
        self.main_frame = tk.Frame(self, bg="white", padx=10, pady=10)
        self.main_frame.pack(expand=True, fill="both", padx=20, pady=20)

        # ========== DEMOGRAPHICS ==========
        self.demographics_frame = tk.LabelFrame(self.main_frame, text="Demographics", font=("Arial", 10, "bold"), bg="white")
        self.demographics_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

        tk.Label(self.demographics_frame, text="Name:", font=("Arial", 9, "bold"), bg="white").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.entry_name = tk.Entry(self.demographics_frame, width=20)
        self.entry_name.grid(row=0, column=1, padx=5, pady=2)

        tk.Label(self.demographics_frame, text="Gender:", font=("Arial", 9, "bold"), bg="white").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.gender_var = tk.StringVar()
        self.gender_dropdown = ttk.Combobox(self.demographics_frame, textvariable=self.gender_var, state="readonly")
        self.gender_dropdown["values"] = ["male", "female", "other"]
        self.gender_dropdown.grid(row=1, column=1, padx=5, pady=2)
        self.gender_dropdown.current(0)

        tk.Label(self.demographics_frame, text="N° of agents:", font=("Arial", 9, "bold"), bg="white").grid(row=2, column=0, sticky="w", padx=5, pady=2)
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
        self.mobility_frame = tk.LabelFrame(self.main_frame, text="Mobility Preferences", font=("Arial", 10, "bold"), bg="white")
        self.mobility_frame.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")

        preferences = ["Eco consciousness", "Time sensitivity", "Comfort preference", "Budget sensitivity", "Reliability sensitivity"]
        options = ["Not at all important", "Slightly important", "Moderately important", "Very important", "Extremely important"]

        self.mobility_vars = {}  # Guardar las selecciones de Combobox

        for i, pref in enumerate(preferences):
            tk.Label(self.mobility_frame, text=f"{pref}:", font=("Arial", 9, "bold"), bg="white").grid(row=i, column=0, sticky="w", padx=5, pady=2)
            var = tk.StringVar()
            combobox = ttk.Combobox(self.mobility_frame, textvariable=var, state="readonly")
            combobox["values"] = options
            combobox.grid(row=i, column=1, padx=5, pady=2)
            combobox.current(0)
            self.mobility_vars[pref] = var

        # ========== PERSONAL ENVIRONMENT ==========
        self.environment_frame = tk.LabelFrame(self.main_frame, text="Personal Environment", font=("Arial", 10, "bold"), bg="white")
        self.environment_frame.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="nsew")

        # ========== BOTÓN "SAVE" PARA EXPORTAR JSON ==========
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
        """ Guarda los datos del perfil en un archivo JSON """

        # Obtener valores del formulario
        profile_name = self.entry_name.get().strip()
        gender = self.gender_var.get()
        num_agents = self.agents_slider.get()

        if not profile_name:
            messagebox.showerror("Error", "Profile name is required.")
            return

        # Diccionario base del perfil
        profile_data = {
            profile_name: {
                "demographics": {
                    "gender": gender,
                    "num_agents": num_agents
                },
                "mobility_preferences": {pref: var.get() for pref, var in self.mobility_vars.items()}
            }
        }

        # Agregar los campos personalizados
        for label_entry, value_entry in self.custom_fields:
            label = label_entry.get().strip()
            value = value_entry.get().strip()
            if label and value:
                profile_data[profile_name]["demographics"][label] = value

        # Guardar en JSON
        file_path = "profiles.json"

        if os.path.exists(file_path):
            with open(file_path, "r") as file:
                try:
                    existing_data = json.load(file)
                except json.JSONDecodeError:
                    existing_data = {}
        else:
            existing_data = {}

        existing_data.update(profile_data)

        with open(file_path, "w") as file:
            json.dump(existing_data, file, indent=4)

        messagebox.showinfo("Success", f"Profile '{profile_name}' saved successfully!")

        # Limpiar los campos
        self.entry_name.delete(0, tk.END)
        self.gender_dropdown.current(0)
        self.agents_slider.set(50)

        for label_entry, value_entry in self.custom_fields:
            label_entry.destroy()
            value_entry.destroy()

        self.custom_fields.clear()
        self.add_button.config(state="normal")