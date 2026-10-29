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
    )
    conversation.pack(fill="both", expand=True, padx=10, pady=10)

    # Selected user ki saved conversation load karna
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

    tk.Button(
        bottom_frame,
        text="Send",
        font=style.BUTTON_FONT,
        bg=style.ACCENT,
        fg=style.BLACK,
        command=send_message,
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

    back_btn = tk.Button(
        screen,
        text="Close",
        font=style.BUTTON_FONT,
        bg=style.ACCENT,
        fg=style.BLACK,
        command=screen.destroy,
    )
    back_btn.pack(pady=10)


def home_page(user_email):
    """
    user_email: login karne wale user ka email.
    Login success par home_page(user_email) call karein.
    """
    win = tk.Tk()
    win.title("Home")
    create_chat_table()
    win.geometry(style.WINDOW_SIZE)
    win.configure(bg=style.BG)

    # Logged-in user ka naam database se fetch karein.
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

    menu_items = [
        ("⚙", "Settings", settings.open_settings),
        ("📥", "Received Files", open_received_files),
        ("💬", "Message History", open_message_history),
        ("❓", "Help", open_help),
        ("ⓘ", "About", open_about),
    ]

    for icon_text, item_title, screen_function in menu_items:
        btn = tk.Button(
            top_menu_frame,
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
        fg=style.WHITE,
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

    INACTIVE_TIMEOUT = 10 * 60
    STATUS_COLORS = {
        "Online": "#22C55E",
        "Inactive": "#F59E0B",
        "Offline": "#9CA3AF",
    }

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
                fg="#9CA3AF",
            ).pack(anchor="w", padx=10, pady=5)
            return

        for user_id, user in known_users.items():
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
            user_id = user["instance_id"]
            known_users[user_id] = user
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
            if now - minimized_since >= INACTIVE_TIMEOUT:
                discovery.set_status("Inactive")
        else:
            minimized_since = None
            if now - last_activity >= INACTIVE_TIMEOUT:
                discovery.set_status("Inactive")
            else:
                discovery.set_status("Online")

        win.after(1000, check_status)

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
    win.after(1000, check_status)
    win.mainloop()
