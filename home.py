import sqlite3
import tkinter as tk
from tkinter import *
from tkinter import ttk
import style
import settings
# import received_files
# import message_history
# import help_screen
# import about

def open_screen(screen_title):
    screen = tk.Toplevel()
    screen.title(screen_title)
    screen.geometry("700x450")
    screen.configure(bg=style.BG)

    title = tk.Label(
        screen, text=screen_title, font=style.TITLE_FONT, bg=style.BG, fg=style.WHITE
    )
    title.pack(pady=30)

    back_btn = tk.Button(
        screen,
        text="Close",
        font=style.BUTTON_FONT,
        bg=style.ACCENT,
        fg=style.BLACK,
        command=screen.destroy,
    )
    back_btn.pack(pady=10)


def open_settings():
    open_screen("Settings")


def open_received_files():
    open_screen("Received Files")


def open_message_history():
    open_screen("Message History")


def open_help():
    open_screen("Help")


def open_about():
    open_screen("About")


def home_page():
    win = tk.Tk()
    win.title("Home")
    win.geometry(style.WINDOW_SIZE)
    win.configure(bg=style.BG)

    # Top Header
    header = tk.Frame(win, bg=style.CARD)
    header.pack(fill="x")
    header.pack_propagate(False)

    # Top Navigation Menu
    menu_frame = tk.Frame(win, bg=style.CARD)
    menu_frame.pack(fill="x")

    menu_items = [
        ("⚙", "Settings", settings.open_settings),
        ("📥", "Received Files", open_received_files),
        ("💬", "Message History", open_message_history),
        ("❓", "Help", open_help),
        ("ⓘ", "About", open_about),
    ]

    for icon_text, item_title, screen_function in menu_items:
        btn = tk.Button(
            menu_frame,
            text=f"{icon_text}  {item_title}",
            font=("Segoe UI", 10),
            bg=style.CARD,
            fg=style.WHITE,
            activebackground=style.BORDER,
            activeforeground=style.ACCENT,
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=14,
            command=screen_function,
        )
        btn.pack(side="left", padx=5, pady=3)

    # left side menu
    main_frame = tk.Frame(
        win,
        bg=style.BG,
    )
    main_frame.pack(fill="both", expand=True, pady=4)

    menu_frame = tk.Frame(main_frame, bg=style.CARD, width=220)
    menu_frame.pack(side="left", fill="y")
    menu_frame.pack_propagate(False)

    conn = sqlite3.connect("lan_connect_project.db")
    c = conn.cursor()
    c.execute("SELECT firstname, lastname FROM register")
    users = c.fetchall()
    conn.close()

    choices = [firstname + " " + lastname for firstname, lastname in users]

    branch_label = tk.Label(
        menu_frame,
        text="Select a User",
        font=("Segoe UI", 10, "bold"),
        bg=style.CARD,
        fg=style.WHITE,
        anchor="w",
    )
    branch_label.pack(anchor=tk.W, padx=10)
    branch_dropdown = ttk.Combobox(menu_frame, values=choices, state="readonly")
    branch_dropdown.pack(anchor=tk.W, padx=10)

    if choices:
        branch_dropdown.current(0)

    win.mainloop()
