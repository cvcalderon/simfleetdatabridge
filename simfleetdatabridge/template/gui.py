import tkinter as tk
from tkinter import font

from simfleetdatabridge.template.utils import COLOR_UPPER_BAR, COLOR_SIDE_MENU_COLOR, COLOR_PRINCIPAL_BODY, COLOR_MENU_CURSOR_ENTER
import simfleetdatabridge.template.utils as utils


class launch_gui(tk.Tk):

    def __init__(self):
        super().__init__()
        #self.logo = utils.read_image("./images/logo.png",(560,136))

        self.config_window()
        self.panels()
        self.upper_bar_controls()

    def config_window(self):

        self.title("SimfleetAI")
        self.iconbitmap(utils.absolute_path("./images/icon.ico"))
        w, h = 1024, 600
        utils.center_window(self, app_width = w, app_height = h)

    def panels(self):

        # Create upper bar
        self.upper_bar = tk.Frame(self, bg=COLOR_UPPER_BAR, height=50)
        self.upper_bar.pack(side=tk.TOP, fill='both')

        # Create side menu
        self.side_menu = tk.Frame(self, bg=COLOR_SIDE_MENU_COLOR, width=150)
        self.side_menu.pack(side=tk.LEFT, fill='both', expand=False)

        # Create principal body
        self.principal_body = tk.Frame(self, bg=COLOR_PRINCIPAL_BODY)
        self.principal_body.pack(side=tk.RIGHT, fill='both', expand=True)

    def upper_bar_controls(self):

        # Config upper bar
        font_awesome = font.Font(family="FontAwesome", size=12)

        # Title label
        self.labelTitle = tk.Label(self.upper_bar, text="SimfleetAI")
        self.labelTitle.config(fg="#fff", font=("Roboto", 15),
                               bg=COLOR_UPPER_BAR, pady=10, width=14)
        self.labelTitle.pack(side=tk.LEFT)

        # Side menu buttom
        self.SideMenuButtom = tk.Button(self.upper_bar, text='\uf0c9', font=font_awesome,
                                        bd=0, bg=COLOR_UPPER_BAR, fg="white")
        self.SideMenuButtom.pack(side=tk.LEFT)

        # Label information
        self.labelTitle = tk.Label(self.upper_bar, text="Contact: ccalderon@upv.es")
        self.labelTitle.config(fg="#fff", font=("Roboto", 10),
                               bg=COLOR_UPPER_BAR, padx=10, width=20)
        self.labelTitle.pack(side=tk.RIGHT)
