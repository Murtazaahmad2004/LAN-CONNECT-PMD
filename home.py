import atexit
import sqlite3
import time
import tkinter as tk
from tkinter import *
from tkinter import ttk
from discovery import LANDiscovery
import style
import settings

# import received_files
# import message_history
# import help_screen
# import about


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


DB_NAME = "lan_connect_project.db"


def create_chat_table():
    conn = sqlite3.connect(DB_NAME)

    try:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT NOT NULL,
                receiver TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )          
        """)
        conn.commit()
    finally:
        conn.close()


def open_chat(parent, firstname, lastname, email):

    # Right side
    for widget in parent.winfo_children():
        widget.destroy()

    # Chat header
    header = tk.Frame(parent, bg=style.CARD)
    header.pack(fill="x")

    tk.Label(
        header,
        text=f"💬  {firstname} {lastname}",
        font=("Segoe UI", 13, "bold"),
        bg=style.CARD,
        fg=style.WHITE,
    ).pack(side="left", padx=15, pady=15)

    # Messages display area
    conversation = tk.Text(
        parent,
        bg=style.BG,
        fg=style.WHITE,
        font=("Segoe UI", 10),
        wrap="word",
        state="disabled",
        relief="flat",
        insertbackground=style.BLACK,
    )
    conversation.pack(fill="both", expand=True, padx=10, pady=10)

    # Load the saved conversation of the selected user
    conn = sqlite3.connect(DB_NAME)

    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT sender, message
            FROM messages
            WHERE receiver = ?
            ORDER BY id ASC
        """,
            (email,),
        )
        messages = c.fetchall()
    finally:
        conn.close()

    conversation.config(state="normal")

    for sender, message in messages:
        conversation.insert("end", f"{sender}: {message}\n\n")

    conversation.config(state="disabled")
    conversation.see("end")

    # Bottom input area
    bottom_frame = tk.Frame(parent, bg=style.CARD)
    bottom_frame.pack(fill="x", padx=10, pady=10)

    message_input = tk.Text(
        bottom_frame,
        font=("Segoe UI", 11),
        height=3,
        wrap="word",
        bg=style.INPUT_BG,
        fg=style.BLACK,
        insertbackground=style.BLACK,
        relief="flat",
    )
    message_input.pack(side="left", fill="x", expand=True, padx=8, pady=8)

    def send_message():
        message = message_input.get("1.0", "end-1c").strip()

        if not message:
            return

        conn = sqlite3.connect(DB_NAME)

        try:
            c = conn.cursor()
            c.execute(
                """
                INSERT INTO messages
                (sender, receiver, message)
                VALUES (?, ?, ?)
            """,
                ("You", email, message),
            )
            conn.commit()
        finally:
            conn.close()

        conversation.config(state="normal")
        conversation.insert("end", f"You: {message}\n\n")
        conversation.config(state="disabled")
        conversation.see("end")

        message_input.delete("1.0", "end")

    style.make_button(
        bottom_frame, "Send", send_message, kind="primary"
    ).pack(side="right", padx=8, pady=8)

    def handle_enter(event):
        send_message()
        return "break"

    message_input.bind("<Return>", handle_enter)
    message_input.focus_set()


def open_screen(screen_title):
    screen = tk.Toplevel()
    screen.title(screen_title)
    screen.geometry("700x450")
    screen.configure(bg=style.BG)

    title = tk.Label(
        screen, text=screen_title, font=style.TITLE_FONT, bg=style.BG, fg=style.WHITE
    )
    title.pack(pady=30)

    back_btn = style.make_button(
        screen, "Close", screen.destroy, kind="primary"
    )
    back_btn.pack(pady=10)


def home_page(user_email):

    # Load logged-in user's saved settings
    user_settings = settings.load_settings(user_email)

    # Saved theme: "Auto" (follow OS), "Light" or "Dark"
    state = {
        "theme_mode": user_settings.get("theme", "Auto"),
        "inactive_on_minimize": bool(user_settings.get("inactive_on_minimize", 1)),
        "inactive_minutes": int(user_settings.get("inactive_minutes", 5) or 5),
    }

    # Apply theme + remember it so the login screen matches next time
    style.set_theme(state["theme_mode"])
    style.save_preference(state["theme_mode"])

    # Create main window
    win = tk.Tk()
    win.title("Home")
    create_chat_table()
    win.geometry(style.WINDOW_SIZE)
    win.configure(bg=style.BG)
    style.setup_ttk(win)

    # Fetch the logged-in user's name from the database.
    conn = sqlite3.connect(DB_NAME)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT firstname, lastname
            FROM register
            WHERE email = ?
            """,
            (user_email,)
        )
        logged_in_user = cursor.fetchone()
    finally:
        conn.close()

    if logged_in_user:
        local_username = " ".join(
            part for part in logged_in_user if part
        ).strip()
    else:
        local_username = user_email or "Unknown User"

    # Top Header
    header = tk.Frame(win, bg=style.CARD)
    header.pack(fill="x")
    header.pack_propagate(False)

    # Top Navigation Menu
    top_menu_frame = tk.Frame(win, bg=style.CARD)
    top_menu_frame.pack(fill="x")

    def open_settings_window():
        settings.open_settings(
            user_email=user_email,
            main_window=win,
            discovery=discovery,
            on_save=lambda new: state.update(
                theme_mode=new["theme"],
                inactive_on_minimize=bool(new["inactive_on_minimize"]),
                inactive_minutes=int(new["inactive_minutes"]),
            ),
        )

    def toggle_theme():
        new_mode = "Dark" if style.CURRENT_THEME == "Light" else "Light"

        # Remember the choice for this user
        try:
            saved = settings.load_settings(user_email)
            saved["theme"] = new_mode
            settings.save_settings(user_email, saved)
        except Exception:
            pass

        state["theme_mode"] = new_mode
        style.apply_theme(win, new_mode)
        style.save_preference(new_mode)

    menu_items = [
        ("⚙", "Settings", open_settings_window),
        ("📥", "Received Files", open_received_files),
        ("💬", "Message History", open_message_history),
        ("❓", "Help", open_help),
        ("ⓘ", "About", open_about),
    ]

    for icon_text, item_title, screen_function in menu_items:
        btn = tk.Button(
            top_menu_frame,
            text=f"{icon_text}  {item_title}",
            font=("Segoe UI", 10, "bold"),
            bg=style.CARD,
            fg=style.WHITE,
            activebackground=style.CARD,
            activeforeground=style.ACCENT,
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=12,
            pady=14,
            command=screen_function,
        )
        btn.pack(side="left", padx=5, pady=3)

    # Quick Light/Dark switch on the right side of the menu
    tk.Button(
        top_menu_frame,
        text="🌓  Theme",
        font=("Segoe UI", 10, "bold"),
        bg=style.CARD,
        fg=style.WHITE,
        activebackground=style.CARD,
        activeforeground=style.ACCENT,
        relief="flat",
        bd=0,
        cursor="hand2",
        padx=12,
        pady=14,
        command=toggle_theme,
    ).pack(side="right", padx=5, pady=3)

    # Main content layout
    main_frame = tk.Frame(win, bg=style.BG)
    main_frame.pack(fill="both", expand=True, pady=4)

    content_frame = tk.Frame(main_frame, bg=style.BG)
    content_frame.pack(side="right", fill="both", expand=True)

    tk.Label(
        content_frame,
        text="Select a user to start a conversation",
        font=("Segoe UI", 12),
        bg=style.BG,
        fg=style.MUTED,
    ).pack(expand=True)

    # Left users panel
    users_frame = tk.Frame(main_frame, bg=style.CARD, width=220)
    users_frame.pack(side="left", fill="y")
    users_frame.pack_propagate(False)

    tk.Label(
        users_frame,
        text="LAN Users",
        font=("Segoe UI", 10, "bold"),
        bg=style.CARD,
        fg=style.WHITE,
        anchor="w",
    ).pack(fill="x", padx=10, pady=8)

    online_users_frame = tk.Frame(users_frame, bg=style.CARD)
    online_users_frame.pack(fill="both", expand=True)

    # Minimized time before "Inactive" is chosen by the user in Settings
    INACTIVE_TIMEOUT = 10 * 60    # no activity for 10 minutes -> Inactive
    STATUS_COLORS = {
        "Online": style.STATUS_ONLINE,
        "Inactive": style.STATUS_INACTIVE,
        "Offline": style.STATUS_OFFLINE,
    }

    # Users are keyed by username (one entry per person). Offline users stay
    # in the list while the app is running on any computer; the list is
    # shared between computers and is empty again once every app is closed.
    known_users = {}

    last_activity = time.monotonic()
    minimized_since = None

    def render_users():
        for widget in online_users_frame.winfo_children():
            widget.destroy()

        if not known_users:
            tk.Label(
                online_users_frame,
                text="No users discovered",
                bg=style.CARD,
                fg=style.MUTED,
            ).pack(anchor="w", padx=10, pady=5)
            return

        status_order = {"Online": 0, "Inactive": 1, "Offline": 2}
        sorted_users = sorted(
            known_users.values(),
            key=lambda u: (
                status_order.get(u.get("status", "Offline"), 2),
                u["username"].lower(),
            ),
        )

        for user in sorted_users:
            status = user.get("status", "Offline")
            row = tk.Frame(online_users_frame, bg=style.CARD)
            row.pack(fill="x", padx=10, pady=5)

            tk.Label(
                row,
                text="●",
                fg=STATUS_COLORS.get(status, STATUS_COLORS["Offline"]),
                bg=style.CARD,
                font=("Segoe UI", 11),
            ).pack(side="left", padx=(0, 7))

            name_label = tk.Label(
                row,
                text=user["username"],
                font=("Segoe UI", 10),
                bg=style.CARD,
                fg=style.WHITE,
                cursor="hand2",
                anchor="w",
            )
            name_label.pack(side="left", fill="x", expand=True)


    def update_online_users(users):
        for user in users:
            name = user["username"]
            current = known_users.get(name)

            # A restarted app gets a new instance id; keep the newest entry
            if current and current.get("last_seen", 0) > user.get("last_seen", 0):
                continue

            known_users[name] = user

        # Share the Offline users with the other computers, so a computer
        # that starts later also shows them.
        discovery.set_roster(
            [
                u["username"]
                for u in known_users.values()
                if u.get("status") == "Offline"
            ]
        )

        render_users()

    def mark_activity(event=None):
        nonlocal last_activity
        last_activity = time.monotonic()
        if discovery.status != "Online":
            discovery.set_status("Online")

    def check_status():
        nonlocal minimized_since

        if not win.winfo_exists():
            return

        now = time.monotonic()
        is_minimized = win.state() == "iconic"

        if is_minimized:
            if minimized_since is None:
                minimized_since = now
            # Only when the option is enabled; time = minutes set by the user
            if (
                state["inactive_on_minimize"]
                and now - minimized_since >= state["inactive_minutes"] * 60
            ):
                discovery.set_status("Inactive")
        else:
            minimized_since = None
            if now - last_activity >= INACTIVE_TIMEOUT:
                discovery.set_status("Inactive")
            else:
                discovery.set_status("Online")

        win.after(1000, check_status)

    def follow_system_theme():
        """In 'Auto' mode, switch when the OS goes Light <-> Dark."""
        if not win.winfo_exists():
            return

        if state["theme_mode"] == "Auto":
            if style.resolve_theme("Auto") != style.CURRENT_THEME:
                style.apply_theme(win, "Auto")

        win.after(10000, follow_system_theme)

    discovery = LANDiscovery(
        username=local_username,
        on_update=lambda users: win.after(
            0,
            lambda current_users=users: update_online_users(current_users)
        ),
    )

    win.bind_all("<KeyPress>", mark_activity)
    win.bind_all("<Button>", mark_activity)
    win.bind_all("<Motion>", mark_activity)

    def close_home():
        discovery.stop()
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", close_home)
    discovery.start()
    # Also announce "Offline" if the program ends without closing the window
    atexit.register(discovery.stop)
    win.after(1000, check_status)
    win.after(10000, follow_system_theme)
    render_users()
    win.mainloop()