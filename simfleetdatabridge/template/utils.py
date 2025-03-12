from pathlib import Path
from PIL import ImageTk, Image


########## Colors ##########

COLOR_UPPER_BAR = "#1f2329"
COLOR_SIDE_MENU_COLOR = "#2a3138"
COLOR_PRINCIPAL_BODY = "#f1faff"
COLOR_MENU_CURSOR_ENTER = "#2f88c5"


########## Images ##########

def read_image(path, size):
    return ImageTk.PhotoImage(Image.open(path).resize(size, Image.ADAPTIVE))


########## Window ##########

def center_window(window, app_width, app_height):

    window_width = window.winfo_screenwidth()
    window_height = window.winfo_screenheight()

    x = int((window_width / 2) - (window_width / 2))
    y = int((window_height / 2) - (window_height / 2))

    return  window.geometry(f"{app_width}x{app_height}+{x}+{y}")


########## Paths ##########

def absolute_path(path):
    # Definir la ruta usando pathlib
    elem_path = Path(__file__).parent / path
    elem_path = elem_path.resolve()
    return str(elem_path)