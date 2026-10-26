import tkinter as tk
from tkinter import ttk, filedialog
import style
import time


def open_settings():
    screen = tk.Toplevel()
    screen.title("Settings")
    screen.geometry("850x500")
    screen.configure(bg=style.BG)

    # Main application window
    main_window = screen.master

    # Timer variables
    minimized_since = None
    away_timer_id = None

    # Notebook / Tabs
    notebook = ttk.Notebook(screen)
    notebook.pack(fill="both", expand=True, padx=10, pady=10)

    # Tab frames
    sound_tab = tk.Frame(notebook, bg=style.BG)
    network_tab = tk.Frame(notebook, bg=style.BG)
    transfer_tab = tk.Frame(notebook, bg=style.BG)
    logging_tab = tk.Frame(notebook, bg=style.BG)
    hotkeys_tab = tk.Frame(notebook, bg=style.BG)
    general_tab = tk.Frame(notebook, bg=style.BG)
    user_tab = tk.Frame(notebook, bg=style.BG)
    messaging_tab = tk.Frame(notebook, bg=style.BG)

    # Tabs
    notebook.add(general_tab, text="General")
    notebook.add(user_tab, text="User Information")
    notebook.add(messaging_tab, text="Messaging")
    notebook.add(sound_tab, text="Sound Events")
    notebook.add(network_tab, text="Network")
    notebook.add(transfer_tab, text="File Transfer")
    notebook.add(logging_tab, text="Logging")
    notebook.add(hotkeys_tab, text="Hot Keys")

    # Heading helper
    def heading(parent, text):
        tk.Label(
            parent,
            text=text,
            font=style.TITLE_FONT,
            bg=style.BG,
            fg=style.WHITE
        ).pack(anchor="w", padx=20, pady=(20, 15))

    # General tab
    heading(general_tab, "General Settings")

    tk.Label(
        general_tab,
        text="User List",
        bg=style.BG,
        fg=style.WHITE,
        font=("Segoe UI", 10, "bold")
    ).pack(anchor="w", padx=25, pady=8)

    tk.Frame(
        general_tab,
        bg=style.BORDER,
        height=1
    ).pack(fill="x", padx=25, pady=5)

    choices = tk.BooleanVar(value=True)

    tk.Checkbutton(
        general_tab,
        text='Change status to "Away" after being inactive',
        variable=choices,
        bg=style.BG,
        fg=style.WHITE,
        selectcolor=style.CARD,
        activebackground=style.BG,
        activeforeground=style.WHITE,
        highlightthickness=0,
        takefocus=0
    ).pack(anchor="w", padx=28, pady=8)

    tk.Label(
        general_tab,
        text="Inactive time (minutes)",
        bg=style.BG,
        fg=style.WHITE,
        font=style.LABEL_FONT
    ).pack(anchor="w", padx=28, pady=(8, 4))

    away_minutes = tk.Entry(
        general_tab,
        bg=style.CARD,
        fg=style.WHITE,
        insertbackground=style.WHITE,
        font=style.INPUT_FONT,
        relief="flat",
        highlightthickness=1,
        highlightbackground=style.BORDER,
        highlightcolor=style.ACCENT
    )
    away_minutes.insert(0, "5")
    away_minutes.pack(fill="x", padx=28, pady=(0, 10))

    # Current status
    status_label = tk.Label(
        general_tab,
        text="Status: Online",
        bg=style.BG,
        fg=style.ACCENT,
        font=style.LABEL_FONT
    )
    status_label.pack(anchor="w", padx=28, pady=8)

    # Inactivity timer
    def check_inactivity():
        nonlocal minimized_since, away_timer_id

        if not screen.winfo_exists():
            return

        try:
            minutes = int(away_minutes.get().strip())
        except ValueError:
            status_label.config(text="Status: Enter valid minutes")
            away_timer_id = screen.after(1000, check_inactivity)
            return

        if minutes <= 0:
            status_label.config(text="Status: Enter valid minutes")
            minimized_since = None

        elif not choices.get():
            status_label.config(text="Status: Online")
            minimized_since = None

        else:
            try:
                is_minimized = main_window.state() == "iconic"
            except tk.TclError:
                is_minimized = False

            if is_minimized:
                if minimized_since is None:
                    minimized_since = time.time()

                elapsed = time.time() - minimized_since

                if elapsed >= minutes * 60:
                    status_label.config(text="Status: Away")
                else:
                    status_label.config(text="Status: Online")
            else:
                minimized_since = None
                status_label.config(text="Status: Online")

        away_timer_id = screen.after(1000, check_inactivity)

    check_inactivity()

    # User Information tab
    heading(user_tab, "User Information")

    tk.Label(
        user_tab,
        text="Display Name",
        bg=style.BG,
        fg=style.LABEL
    ).pack(anchor="w", padx=25)

    display_name = tk.Entry(user_tab, font=style.INPUT_FONT)
    display_name.pack(anchor="w", padx=25, pady=8)

    tk.Label(
        user_tab,
        text="Department",
        bg=style.BG,
        fg=style.LABEL
    ).pack(anchor="w", padx=25)

    department = ttk.Combobox(
        user_tab,
        values=["CS", "EC", "Mechanical"],
        state="readonly"
    )
    department.pack(anchor="w", padx=25, pady=8)

    # Network tab
    heading(network_tab, "Network Settings")

    tk.Label(
        network_tab,
        text="Listening Port",
        bg=style.BG,
        fg=style.LABEL
    ).pack(anchor="w", padx=25)

    port_entry = tk.Entry(network_tab)
    port_entry.insert(0, "5000")
    port_entry.pack(anchor="w", padx=25, pady=8)

    discover_peers = tk.BooleanVar(value=True)

    tk.Checkbutton(
        network_tab,
        text="Enable peer discovery",
        variable=discover_peers,
        bg=style.BG,
        fg=style.WHITE,
        selectcolor=style.CARD
    ).pack(anchor="w", padx=25, pady=8)

    # File Transfer tab
    heading(transfer_tab, "File Transfer Settings")

    folder_var = tk.StringVar()

    tk.Label(
        transfer_tab,
        text="Download Folder",
        bg=style.BG,
        fg=style.LABEL
    ).pack(anchor="w", padx=25)

    folder_frame = tk.Frame(transfer_tab, bg=style.BG)
    folder_frame.pack(fill="x", padx=25, pady=8)

    tk.Entry(
        folder_frame,
        textvariable=folder_var
    ).pack(side="left", fill="x", expand=True)

    def browse_folder():
        folder = filedialog.askdirectory(parent=screen)
        if folder:
            folder_var.set(folder)

    tk.Button(
        folder_frame,
        text="Browse",
        command=browse_folder
    ).pack(side="left", padx=5)

    # Sound Events tab
    heading(sound_tab, "Sound Events")

    sound_enabled = tk.BooleanVar(value=True)

    tk.Checkbutton(
        sound_tab,
        text="Enable sound events",
        variable=sound_enabled,
        bg=style.BG,
        fg=style.WHITE,
        selectcolor=style.CARD
    ).pack(anchor="w", padx=25, pady=8)

    # Logging tab
    heading(logging_tab, "Logging Settings")

    logging_enabled = tk.BooleanVar(value=True)

    tk.Checkbutton(
        logging_tab,
        text="Enable application logging",
        variable=logging_enabled,
        bg=style.BG,
        fg=style.WHITE,
        selectcolor=style.CARD
    ).pack(anchor="w", padx=25, pady=8)

    # Hot Keys tab
    heading(hotkeys_tab, "Keyboard Shortcuts")

    tk.Label(
        hotkeys_tab,
        text="Open Settings: Ctrl + ,\n"
             "Send Message: Enter\n"
             "Close Window: Alt + F4",
        justify="left",
        bg=style.BG,
        fg=style.LABEL,
        font=style.INPUT_FONT
    ).pack(anchor="w", padx=25)

    # Messaging tab
    heading(messaging_tab, "Messaging Settings")

    enter_to_send = tk.BooleanVar(value=True)

    tk.Checkbutton(
        messaging_tab,
        text="Press Enter to send messages",
        variable=enter_to_send,
        bg=style.BG,
        fg=style.WHITE,
        selectcolor=style.CARD
    ).pack(anchor="w", padx=25, pady=8)

    # Save button
    def save_settings():
        print(
            "Settings values:",
            display_name.get(),
            department.get(),
            port_entry.get(),
            folder_var.get(),
            "Away enabled:", choices.get(),
            "Inactive minutes:", away_minutes.get()
        )

    tk.Button(
        screen,
        text="Save Settings",
        font=style.BUTTON_FONT,
        bg=style.ACCENT,
        fg=style.BLACK,
        command=save_settings
    ).pack(pady=(0, 10))

    # Stop timer when settings window closes
    def close_settings():
        nonlocal away_timer_id

        if away_timer_id is not None:
            screen.after_cancel(away_timer_id)
            away_timer_id = None

        screen.destroy()

    screen.protocol("WM_DELETE_WINDOW", close_settings)