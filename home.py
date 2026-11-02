
import atexit
import json
import socket
import sqlite3
import threading
import time
import tkinter as tk
from tkinter import messagebox

import pystray
from PIL import Image, ImageDraw

from discovery import CHAT_PORT, LANDiscovery
import style
import settings


DB_NAME = style.data_path("lan_connect_project.db")


def create_chat_table():
    conn = sqlite3.connect(DB_NAME, timeout=30)
    try:
        conn.execute("""
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


def save_message(sender, receiver, message):
    conn = sqlite3.connect(DB_NAME, timeout=30)
    try:
        conn.execute(
            """
            INSERT INTO messages (sender, receiver, message)
            VALUES (?, ?, ?)
            """,
            (sender, receiver, message),
        )
        conn.commit()
    finally:
        conn.close()


def get_chat_history(local_username, peer_username):
    conn = sqlite3.connect(DB_NAME, timeout=30)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT sender, message, timestamp
            FROM messages
            WHERE
                (sender = ? AND receiver = ?)
                OR
                (sender = ? AND receiver = ?)
            ORDER BY id ASC
            """,
            (
                local_username,
                peer_username,
                peer_username,
                local_username,
            ),
        )
        return cursor.fetchall()
    finally:
        conn.close()


def get_registered_usernames():
    conn = sqlite3.connect(DB_NAME, timeout=30)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT firstname, lastname FROM register")
        usernames = []

        for firstname, lastname in cursor.fetchall():
            username = " ".join(
                part for part in (firstname, lastname) if part
            ).strip()

            if username and username not in usernames:
                usernames.append(username)

        return usernames
    finally:
        conn.close()


class MessageService:

    def __init__(self, username, on_message, find_peer):
        self.username = username
        self.on_message = on_message
        self.find_peer = find_peer
        self.running = False
        self.server = None

    def start(self):
        try:
            self.server = socket.socket(
                socket.AF_INET,
                socket.SOCK_STREAM
            )
            self.server.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_REUSEADDR,
                1
            )
            self.server.bind(("", CHAT_PORT))
            self.server.listen(10)
            self.server.settimeout(1)
            self.running = True

            threading.Thread(
                target=self._accept_loop,
                daemon=True
            ).start()

            print(
                f"[CHAT] Server started for {self.username} "
                f"on port {CHAT_PORT}"
            )
            return True

        except OSError as e:
            print("[CHAT] Server could not start:", e)

            if self.server:
                self.server.close()
                self.server = None

            return False

    def _accept_loop(self):
        while self.running:
            try:
                conn, address = self.server.accept()
                print(f"[CHAT] Incoming connection from {address}")

                threading.Thread(
                    target=self._handle,
                    args=(conn,),
                    daemon=True
                ).start()

            except socket.timeout:
                continue
            except OSError:
                break

    def _handle(self, conn):
        try:
            conn.settimeout(5)
            data = b""

            while b"\n" not in data:
                chunk = conn.recv(4096)

                if not chunk:
                    break

                data += chunk

                if len(data) > 65536:
                    return

            if b"\n" not in data:
                return

            raw_message = data.split(b"\n", 1)[0]
            msg = json.loads(raw_message.decode("utf-8"))

            if msg.get("type") != "chat":
                return

            if msg.get("to") != self.username:
                print("[CHAT] Message receiver does not match.")
                return

            sender = str(msg.get("from", "")).strip()
            message = str(msg.get("text", ""))

            if sender and message.strip():
                print(
                    f"[CHAT] Message received from {sender}: {message}"
                )
                self.on_message(sender, message)

        except (
            OSError,
            ValueError,
            UnicodeDecodeError,
            TypeError
        ) as e:
            print("[CHAT] Receive error:", e)

        finally:
            try:
                conn.close()
            except OSError:
                pass

    def send(self, receiver, message):
        peer = self.find_peer(receiver)

        if not peer:
            print(f"[CHAT] Peer not found: {receiver}")
            return False

        ip, port = peer

        payload = json.dumps({
            "type": "chat",
            "from": self.username,
            "to": receiver,
            "text": message,
        }).encode("utf-8") + b"\n"

        try:
            with socket.create_connection(
                (ip, port),
                timeout=5
            ) as sock:
                sock.sendall(payload)

            print(
                f"[CHAT] Message sent to {receiver} at {ip}:{port}"
            )
            return True

        except OSError as e:
            print(
                f"[CHAT] Could not send message to {receiver}: {e}"
            )
            return False

    def stop(self):
        self.running = False

        if self.server is not None:
            try:
                self.server.close()
            except OSError:
                pass

            self.server = None

        print("[CHAT] Message service stopped.")


def create_tray_image():
    img = Image.new("RGB", (64, 64), "#2563eb")
    draw = ImageDraw.Draw(img)
    draw.ellipse((16, 16, 48, 48), fill="white")
    return img


def open_screen(screen_title):
    screen = tk.Toplevel()
    screen.title(screen_title)
    screen.geometry("700x450")
    screen.configure(bg=style.BG)

    tk.Label(
        screen,
        text=screen_title,
        font=style.TITLE_FONT,
        bg=style.BG,
        fg=style.WHITE
    ).pack(pady=30)

    style.make_button(
        screen,
        "Close",
        screen.destroy,
        kind="primary"
    ).pack(pady=10)


def open_received_files():
    open_screen("Received Files")


def open_message_history():
    open_screen("Message History")


def open_help():
    open_screen("Help")


def open_about():
    open_screen("About")


def home_page(user_email):

    user_settings = settings.load_settings(user_email)

    state = {
        "theme_mode": user_settings.get("theme", "Auto"),
        "inactive_on_minimize": bool(
            user_settings.get("inactive_on_minimize", 1)
        ),
        "inactive_minutes": int(
            user_settings.get("inactive_minutes", 5) or 5
        ),
        "hide_offline_users": bool(
            user_settings.get("hide_offline_users", 0)
        ),
        "hide_away_users": bool(
            user_settings.get("hide_away_users", 0)
        ),
    }

    style.set_theme(state["theme_mode"])
    style.save_preference(state["theme_mode"])

    win = tk.Tk()
    win.title("LAN Connect")
    style.center_window(win)
    win.configure(bg=style.BG)
    style.setup_ttk(win)

    create_chat_table()

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
        local_username = user_email

    print("[HOME] Logged in user:", local_username)

    try:
        registered_usernames = get_registered_usernames()
    except sqlite3.Error as e:
        print("[DATABASE] Could not load registered users:", e)
        registered_usernames = []

    registered_usernames = [
        name for name in registered_usernames
        if name != local_username
    ]

    known_users = {}

    active_chat = {
        "username": None,
        "conversation": None,
        "input": None,
    }

    last_activity = time.monotonic()
    minimized_since = None
    status_after_id = None
    theme_after_id = None
    tray_icon = None
    message_service = None

    header = tk.Frame(win, bg=style.CARD, height=5)
    header.pack(fill="x")

    top_menu_frame = tk.Frame(win, bg=style.CARD)
    top_menu_frame.pack(fill="x")

    main_frame = tk.Frame(win, bg=style.BG)
    main_frame.pack(fill="both", expand=True, pady=4)

    content_frame = tk.Frame(main_frame, bg=style.BG)
    content_frame.pack(side="right", fill="both", expand=True)

    tk.Label(
        content_frame,
        text="Select a user to start a conversation",
        font=("Segoe UI", 12),
        bg=style.BG,
        fg=style.MUTED
    ).pack(expand=True)

    users_frame = tk.Frame(
        main_frame,
        bg=style.CARD,
        width=220
    )
    users_frame.pack(side="left", fill="y")
    users_frame.pack_propagate(False)

    tk.Label(
        users_frame,
        text="LAN Users",
        font=("Segoe UI", 10, "bold"),
        bg=style.CARD,
        fg=style.WHITE,
        anchor="w"
    ).pack(fill="x", padx=10, pady=8)

    online_users_frame = tk.Frame(users_frame, bg=style.CARD)
    online_users_frame.pack(fill="both", expand=True)

    INACTIVE_TIMEOUT = 10 * 60

    STATUS_COLORS = {
        "Online": style.STATUS_ONLINE,
        "Inactive": style.STATUS_INACTIVE,
        "Offline": style.STATUS_OFFLINE,
    }

    def open_user_chat(peer_username):
        active_chat["username"] = peer_username

        for widget in content_frame.winfo_children():
            widget.destroy()

        chat_header = tk.Frame(content_frame, bg=style.CARD)
        chat_header.pack(fill="x")

        tk.Label(
            chat_header,
            text=f"💬  {peer_username}",
            font=("Segoe UI", 13, "bold"),
            bg=style.CARD,
            fg=style.WHITE
        ).pack(side="left", padx=15, pady=15)

        conversation = tk.Text(
            content_frame,
            bg=style.BG,
            fg=style.WHITE,
            font=("Segoe UI", 10),
            wrap="word",
            state="disabled",
            relief="flat",
            insertbackground=style.WHITE
        )
        conversation.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=10
        )

        active_chat["conversation"] = conversation

        try:
            messages = get_chat_history(
                local_username,
                peer_username
            )

            conversation.config(state="normal")

            for sender, message, timestamp in messages:
                display_name = (
                    "You"
                    if sender == local_username
                    else sender
                )

                conversation.insert(
                    "end",
                    f"{display_name}: {message}\n\n"
                )

            conversation.config(state="disabled")
            conversation.see("end")

        except sqlite3.Error as e:
            print("[DATABASE] History error:", e)

        bottom_frame = tk.Frame(content_frame, bg=style.CARD)
        bottom_frame.pack(fill="x", padx=10, pady=10)

        message_input = tk.Text(
            bottom_frame,
            font=("Segoe UI", 11),
            height=3,
            wrap="word",
            bg=style.INPUT_BG,
            fg=style.BLACK,
            insertbackground=style.BLACK,
            relief="flat"
        )
        message_input.pack(
            side="left",
            fill="x",
            expand=True,
            padx=8,
            pady=8
        )

        active_chat["input"] = message_input

        def display_message(sender, message):
            current_chat = active_chat["conversation"]

            if current_chat is None:
                return

            if not current_chat.winfo_exists():
                return

            display_name = (
                "You"
                if sender == local_username
                else sender
            )

            current_chat.config(state="normal")
            current_chat.insert(
                "end",
                f"{display_name}: {message}\n\n"
            )
            current_chat.config(state="disabled")
            current_chat.see("end")

        def send_message():
            message = message_input.get(
                "1.0",
                "end-1c"
            ).strip()

            if not message:
                return

            receiver = active_chat["username"]

            if not receiver:
                return

            if message_service is None:
                messagebox.showerror(
                    "Chat Error",
                    "Message service is not running.",
                    parent=win
                )
                return

            success = message_service.send(
                receiver,
                message
            )

            if not success:
                messagebox.showerror(
                    "Message Not Sent",
                    "Could not send the message.\n\n"
                    "Please check that the other computer is online "
                    "and connected to the same LAN.",
                    parent=win
                )
                return

            try:
                save_message(
                    local_username,
                    receiver,
                    message
                )
            except sqlite3.Error as e:
                messagebox.showerror(
                    "Database Error",
                    str(e),
                    parent=win
                )
                return

            display_message(local_username, message)
            message_input.delete("1.0", "end")

        style.make_button(
            bottom_frame,
            "Send",
            send_message,
            kind="primary"
        ).pack(side="right", padx=8, pady=8)

        def handle_enter(event):
            send_message()
            return "break"

        message_input.bind("<Return>", handle_enter)
        message_input.focus_set()

    def find_peer(username):
        users = discovery.get_users()

        for user in users:
            if user.get("username") == username:
                if user.get("status") == "Offline":
                    continue

                ip = user.get("ip")
                port = user.get("port", CHAT_PORT)

                if ip and port:
                    return ip, int(port)

        return None

    def on_incoming_message(sender, message):
        print(
            f"[HOME] Incoming message from {sender}: {message}"
        )

        try:
            save_message(
                sender,
                local_username,
                message
            )
        except sqlite3.Error as e:
            print("[DATABASE] Incoming save error:", e)
            return

        def update_chat():
            try:
                if not win.winfo_exists():
                    return

                if active_chat["username"] == sender:
                    conversation = active_chat["conversation"]

                    if conversation and conversation.winfo_exists():
                        conversation.config(state="normal")
                        conversation.insert(
                            "end",
                            f"{sender}: {message}\n\n"
                        )
                        conversation.config(state="disabled")
                        conversation.see("end")

            except tk.TclError as e:
                print("[UI] Incoming message UI error:", e)

        try:
            win.after(0, update_chat)
        except tk.TclError:
            pass

    def render_users():
        for widget in online_users_frame.winfo_children():
            widget.destroy()

        visible_users = [
            user
            for user in known_users.values()
            if not (
                state["hide_offline_users"]
                and user.get("status") == "Offline"
            )
            and not (
                state["hide_away_users"]
                and user.get("status") == "Inactive"
            )
        ]

        if not visible_users:
            tk.Label(
                online_users_frame,
                text="No users to show",
                bg=style.CARD,
                fg=style.MUTED
            ).pack(anchor="w", padx=10, pady=5)
            return

        status_order = {
            "Online": 0,
            "Inactive": 1,
            "Offline": 2
        }

        sorted_users = sorted(
            visible_users,
            key=lambda user: (
                status_order.get(
                    user.get("status", "Offline"),
                    2
                ),
                user["username"].lower()
            )
        )

        for user in sorted_users:
            username = user["username"]
            status = user.get("status", "Offline")

            row = tk.Frame(online_users_frame, bg=style.CARD)
            row.pack(fill="x", padx=10, pady=5)

            tk.Label(
                row,
                text="●",
                fg=STATUS_COLORS.get(
                    status,
                    STATUS_COLORS["Offline"]
                ),
                bg=style.CARD,
                font=("Segoe UI", 11)
            ).pack(side="left", padx=(0, 7))

            name_label = tk.Label(
                row,
                text=username,
                font=("Segoe UI", 10),
                bg=style.CARD,
                fg=style.WHITE,
                cursor="hand2",
                anchor="w"
            )
            name_label.pack(side="left", fill="x", expand=True)

            for widget in (row, name_label):
                widget.bind(
                    "<Button-1>",
                    lambda event, name=username: open_user_chat(name)
                )

    def update_online_users(users):
        current_names = set()

        for user in users:
            username = user.get("username")

            if not username or username == local_username:
                continue

            current_names.add(username)
            known_users[username] = user.copy()

        for username in list(known_users):
            if username not in current_names:
                known_users[username]["status"] = "Offline"

        render_users()

    def safe_update_users(users):
        try:
            if win.winfo_exists():
                win.after(
                    0,
                    lambda snapshot=users: (
                        update_online_users(snapshot)
                        if win.winfo_exists()
                        else None
                    )
                )
        except tk.TclError:
            pass

    discovery = LANDiscovery(
        username=local_username,
        on_update=safe_update_users
    )
    discovery.set_roster(registered_usernames)

    message_service = MessageService(
        username=local_username,
        on_message=on_incoming_message,
        find_peer=find_peer
    )

    chat_started = message_service.start()

    if not chat_started:
        messagebox.showwarning(
            "Chat Service Warning",
            f"Could not start the chat server on port {CHAT_PORT}.\n"
            "You may not receive incoming messages.",
            parent=win
        )

    def mark_activity(event=None):
        nonlocal last_activity

        last_activity = time.monotonic()

        if discovery.status != "Online":
            discovery.set_status("Online")

    def check_status():
        nonlocal minimized_since, status_after_id

        try:
            if not win.winfo_exists():
                return
        except tk.TclError:
            return

        now = time.monotonic()
        is_hidden = win.state() in ("iconic", "withdrawn")

        if is_hidden:
            if minimized_since is None:
                minimized_since = now

            if (
                state["inactive_on_minimize"]
                and now - minimized_since
                >= state["inactive_minutes"] * 60
            ):
                if discovery.status != "Inactive":
                    discovery.set_status("Inactive")

        else:
            minimized_since = None

            if now - last_activity >= INACTIVE_TIMEOUT:
                if discovery.status != "Inactive":
                    discovery.set_status("Inactive")
            elif discovery.status != "Online":
                discovery.set_status("Online")

        status_after_id = win.after(1000, check_status)

    def follow_system_theme():
        nonlocal theme_after_id

        try:
            if not win.winfo_exists():
                return
        except tk.TclError:
            return

        if state["theme_mode"] == "Auto":
            if style.resolve_theme("Auto") != style.CURRENT_THEME:
                style.apply_theme(win, "Auto")

        theme_after_id = win.after(10000, follow_system_theme)

    def on_settings_saved(new):
        state.update(
            theme_mode=new["theme"],
            inactive_on_minimize=bool(
                new["inactive_on_minimize"]
            ),
            inactive_minutes=int(
                new["inactive_minutes"]
            ),
            hide_offline_users=bool(
                new["hide_offline_users"]
            ),
            hide_away_users=bool(
                new.get(
                    "hide_away_users",
                    state["hide_away_users"]
                )
            )
        )

        render_users()

    def open_settings_window():
        settings.open_settings(
            user_email=user_email,
            main_window=win,
            discovery=discovery,
            on_save=on_settings_saved
        )

    def toggle_theme():
        new_mode = (
            "Dark"
            if style.CURRENT_THEME == "Light"
            else "Light"
        )

        try:
            saved = settings.load_settings(user_email)
            saved["theme"] = new_mode
            settings.save_settings(user_email, saved)
        except Exception as e:
            print("[THEME] Save error:", e)

        state["theme_mode"] = new_mode
        style.apply_theme(win, new_mode)
        style.save_preference(new_mode)

    def stop_tray():
        nonlocal tray_icon

        if tray_icon is not None:
            try:
                tray_icon.stop()
            except Exception:
                pass

            tray_icon = None

    def shutdown():
        nonlocal status_after_id, theme_after_id

        for after_id in (status_after_id, theme_after_id):
            if after_id is not None:
                try:
                    win.after_cancel(after_id)
                except tk.TclError:
                    pass

        status_after_id = None
        theme_after_id = None

        try:
            win.unbind_all("<KeyPress>")
            win.unbind_all("<Button>")
            win.unbind_all("<Motion>")
        except tk.TclError:
            pass

        stop_tray()

        if message_service is not None:
            message_service.stop()

        try:
            discovery.stop()
        except Exception as e:
            print("[DISCOVERY] Stop error:", e)

    def restore_window():
        stop_tray()
        win.deiconify()
        win.lift()
        win.focus_force()

    def exit_app():
        shutdown()
        win.destroy()

    def hide_to_tray():
        nonlocal tray_icon

        win.withdraw()

        if tray_icon is None:
            menu = pystray.Menu(
                pystray.MenuItem(
                    "Open LAN Connect",
                    lambda icon, item: win.after(0, restore_window),
                    default=True
                ),
                pystray.MenuItem(
                    "Exit",
                    lambda icon, item: win.after(0, exit_app)
                )
            )

            tray_icon = pystray.Icon(
                "LANConnect",
                create_tray_image(),
                "LAN Connect",
                menu
            )

            tray_icon.run_detached()

    def open_logout():
        shutdown()
        win.destroy()

        from login import show_login
        show_login()

    menu_items = [
        ("⚙", "Settings", open_settings_window),
        ("📥", "Received Files", open_received_files),
        ("💬", "Message History", open_message_history),
        ("❓", "Help", open_help),
        ("ⓘ", "About", open_about),
        ("⇥", "Logout", open_logout),
    ]

    for icon_text, item_title, screen_function in menu_items:
        tk.Button(
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
            command=screen_function
        ).pack(side="left", padx=5, pady=3)

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
        command=toggle_theme
    ).pack(side="right", padx=5, pady=3)

    win.bind_all("<KeyPress>", mark_activity)
    win.bind_all("<Button>", mark_activity)
    win.bind_all("<Motion>", mark_activity)

    win.protocol("WM_DELETE_WINDOW", hide_to_tray)

    discovery.start()

    atexit.register(discovery.stop)

    status_after_id = win.after(1000, check_status)
    theme_after_id = win.after(10000, follow_system_theme)

    render_users()

    print("[HOME] LAN Connect started successfully.")

    win.mainloop()


if __name__ == "__main__":
    home_page()