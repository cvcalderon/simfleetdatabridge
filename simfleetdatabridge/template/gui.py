import os
import json
import tkinter as tk
from tkinter import ttk, messagebox, font
import simfleetdatabridge.template.utils as utils
from simfleetdatabridge.template.forms.createprofile import CreateProfile
from simfleetdatabridge.template.forms.prepareconfig import PrepareSimConfig

class LaunchGUI(tk.Tk):

    def __init__(self):
        super().__init__()

        #Variables
        self.tree_data = []  # Almacena los datos de perfiles

        #Elements
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

        self.buttonUpdateProfile = tk.Button(self.profile_submenu_frame, text="   🔧 Prepare Config", anchor="w",
                                             font=universal_font,
                                             bd=0, bg=utils.COLOR_SIDE_MENU_COLOR, fg="white",
                                             width=menu_width - 2, height=menu_height, command=self.prepare_sim_config)

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
        """Carga la interfaz de creación de perfiles en el área principal y conserva los datos."""
        for widget in self.principal_body.winfo_children():
            widget.destroy()  # Limpiar el contenido anterior

        self.create_profile_frame = CreateProfile(self.principal_body, self)
        self.create_profile_frame.pack(expand=True, fill="both")

    def prepare_sim_config(self):
        """Carga la interfaz de configuración de simulación en el área principal."""
        for widget in self.principal_body.winfo_children():
            widget.destroy()  # Limpiar el contenido anterior

        PrepareSimConfig(self.principal_body, self.tree_data).pack(expand=True, fill="both")

    def open_simulation(self):
        print("Simulation Opened")


