from tkinter import messagebox
import tkinter as tk
import style

def open_register():
    win = tk.Toplevel()
    win.title("Register Screen")
    win.geometry(style.WINDOW_SIZE)
    win.configure(bg=style.BG)
    
    card = tk.Frame (
        win,
        bg=style.CARD,
        padx=38,
        pady=28,
        highlightbackground=style.BORDER,
        highlightthickness=1
    )
    card.pack(pady=25)
    
    heading = tk.Label(
        card,
        text="Create an Account",
        font=style.TITLE_FONT,
        fg=style.WHITE,
        bg=style.CARD
    )
    heading.pack(pady=(0, 15))
    
    def create_input_fields(label_text, show=None):
        label = tk.Label(
            card,
            text=label_text,
            font=style.LABEL_FONT,
            fg=style.WHITE,
            bg=style.CARD,
            anchor="w",
            justify="left"
        )