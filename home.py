import atexit
import json
import os
import re
import socket
import sqlite3
import threading
import time
import tkinter as tk
import uuid
from datetime import datetime, timezone
from tkinter import messagebox, ttk

import pystray
from PIL import Image, ImageDraw

from discovery import CHAT_PORT, LANDiscovery
import style
import settings
import netconfig

# Optional spell checker:  pip install pyspellchecker
try:
    from spellchecker import SpellChecker
    _SPELL = SpellChecker()
except Exception:
    _SPELL = None

try:
    import winsound          # Windows system sounds (other systems: bell)
except ImportError:
    winsound = None

DB_NAME = style.data_path("lan_connect_project.db")

PORT_TRIES = 10            # ports CHAT_PORT .. CHAT_PORT+9 are tried (several apps on one PC)
RECENT_LIMIT = 30          # how many old messages "Display recent messages" shows
WORD_RE = re.compile(r"[A-Za-z']+")


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

        # Unique id per message: the same message is never stored twice
        columns = {r[1] for r in conn.execute("PRAGMA table_info(messages)")}
        if "msg_uid" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN msg_uid TEXT")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_uid "
            "ON messages(msg_uid)"
        )
        conn.commit()
    finally:
        conn.close()


def save_message(sender, receiver, message, uid=None):
    """Stores a message permanently (messages are never deleted)."""
    conn = sqlite3.connect(DB_NAME, timeout=30)
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO messages (sender, receiver, message, msg_uid)
            VALUES (?, ?, ?, ?)
            """,
            (sender, receiver, message, uid),
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
        # Several copies of the app can run on one PC (testing), so we try
        # CHAT_PORT, CHAT_PORT+1, ... and keep the first free one.
        for offset in range(PORT_TRIES):
            port = CHAT_PORT + offset
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            try:
                # On Windows SO_REUSEADDR lets TWO programs share one port,
                # and messages then go to the wrong one. Use an exclusive bind.
                if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                    sock.setsockopt(
                        socket.SOL_SOCKET,
                        socket.SO_EXCLUSIVEADDRUSE,
                        1
                    )
                else:
                    sock.setsockopt(
                        socket.SOL_SOCKET,
                        socket.SO_REUSEADDR,
                        1
                    )

                sock.bind(("", port))
                sock.listen(10)
                sock.settimeout(1)

            except OSError as e:
                sock.close()
                print(f"[CHAT] Port {port} is busy: {e}")
                continue

            self.server = sock
            self.port = port
            self.running = True

            threading.Thread(
                target=self._accept_loop,
                daemon=True
            ).start()

            print(
                f"[CHAT] Server started for {self.username} "
                f"on port {port}"
            )
            return True

        print("[CHAT] Server could not start on any port.")
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
        accepted = False

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
                # Message is for another copy of the app on this PC.
                # We answer "NO" (in finally) so the sender tries the next port.
                print("[CHAT] Message receiver does not match.")
                return

            sender = str(msg.get("from", "")).strip()
            message = str(msg.get("text", ""))
            uid = str(msg.get("id", "")).strip() or None

            if sender and message.strip():
                accepted = True

                try:
                    conn.sendall(b"OK\n")
                except OSError:
                    pass

                print(
                    f"[CHAT] Message received from {sender}: {message}"
                )
                self.on_message(sender, message, uid)

        except (
            OSError,
            ValueError,
            UnicodeDecodeError,
            TypeError
        ) as e:
            print("[CHAT] Receive error:", e)

        finally:
            if not accepted:
                try:
                    conn.sendall(b"NO\n")
                except OSError:
                    pass

            try:
                conn.close()
            except OSError:
                pass

    def _try_send(self, ip, port, payload):
        """Returns 'ok', 'rejected' (someone else owns that port),
        'refused' (nobody listening) or 'error'."""
        try:
            with socket.create_connection(
                (ip, port),
                timeout=2
            ) as sock:
                sock.sendall(payload)
                sock.settimeout(3)
                reply = sock.recv(16).strip()

            return "ok" if reply == b"OK" else "rejected"

        except ConnectionRefusedError:
            return "refused"
        except OSError as e:
            print(f"[CHAT] Send error to {ip}:{port}: {e}")
            return "error"

    def send(self, receiver, message):
        peer = self.find_peer(receiver)

        if not peer:
            print(f"[CHAT] Peer not found: {receiver}")
            return False

        ip, port = peer

        uid = uuid.uuid4().hex

        payload = json.dumps({
            "type": "chat",
            "id": uid,
            "from": self.username,
            "to": receiver,
            "text": message,
        }).encode("utf-8") + b"\n"

        # Try the advertised port first, then the other ports of the range
        ports = [port] + [
            p for p in range(CHAT_PORT, CHAT_PORT + PORT_TRIES)
            if p != port
        ]

        for p in ports:
            result = self._try_send(ip, p, payload)

            if result == "ok":
                print(f"[CHAT] Message sent to {receiver} at {ip}:{p}")
                return uid

            if result == "error":
                break

        print(f"[CHAT] Could not send message to {receiver}")
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


class ChatView(tk.Frame):
    """Scrollable conversation area with chat bubbles.

    My messages: right side, accent coloured bubble.
    Other person's messages: left side, card coloured bubble.
    Right-click a bubble to copy its text.
    """

    def __init__(self, parent, font_size=13):
        super().__init__(parent, bg=style.BG)
        self.font_size = font_size
        self._width = 600
        self._bubbles = []          # (text_label, time_label)
        self._copy_text = ""

        self.canvas = tk.Canvas(self, bg=style.BG, highlightthickness=0, bd=0)
        self.scroll = ttk.Scrollbar(self, orient="vertical",
                                    command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = tk.Frame(self.canvas, bg=style.BG)
        self._window = self.canvas.create_window(
            (0, 0), window=self.inner, anchor="nw"
        )

        self.inner.bind("<Configure>", self._on_inner_resize)
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="Copy", command=self._copy)

        self.bind_all("<MouseWheel>", self._on_wheel)
        self.bind_all("<Button-4>", self._on_wheel)
        self.bind_all("<Button-5>", self._on_wheel)

    # ---- layout helpers
    def _wrap(self):
        return max(220, int(self._width * 0.62))

    def _on_inner_resize(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_resize(self, event):
        self._width = event.width
        self.canvas.itemconfigure(self._window, width=event.width)

        wrap = self._wrap()
        for text_label, _time_label in self._bubbles:
            try:
                text_label.config(wraplength=wrap)
            except tk.TclError:
                pass

    def _on_wheel(self, event):
        try:
            if not self.winfo_exists():
                return
            widget = self.winfo_containing(event.x_root, event.y_root)
        except (tk.TclError, KeyError):
            return

        while widget is not None and widget is not self:
            widget = widget.master
        if widget is None:
            return

        if event.num == 4:
            step = -1
        elif event.num == 5:
            step = 1
        else:
            step = -1 if event.delta > 0 else 1

        if self.inner.winfo_height() > self.canvas.winfo_height():
            self.canvas.yview_scroll(step * 2, "units")

    def _copy(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(self._copy_text)
        except tk.TclError:
            pass

    def _popup_menu(self, event, text):
        self._copy_text = text
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def scroll_to_end(self):
        self.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.yview_moveto(1.0)

    # ---- public API
    def set_font(self, size):
        self.font_size = size
        for text_label, time_label in self._bubbles:
            try:
                text_label.config(font=(style.FONT, size))
                time_label.config(font=(style.FONT, max(size - 4, 8)))
            except tk.TclError:
                pass

    def add_message(self, text, time_text, is_me):
        row = tk.Frame(self.inner, bg=style.BG)
        row.pack(fill="x", pady=(0, 10))

        if is_me:
            bubble_bg, text_fg, time_fg = style.ACCENT, style.ON_ACCENT, style.ON_ACCENT
            border = style.ACCENT
            side, pad = "right", (70, 16)
        else:
            bubble_bg, text_fg, time_fg = style.CARD, style.TEXT, style.MUTED
            border = style.BORDER
            side, pad = "left", (16, 70)

        bubble = tk.Frame(
            row,
            bg=bubble_bg,
            highlightthickness=1,
            highlightbackground=border,
            padx=14,
            pady=8,
        )
        bubble.pack(side=side, padx=pad)

        text_label = tk.Label(
            bubble,
            text=text,
            bg=bubble_bg,
            fg=text_fg,
            font=(style.FONT, self.font_size),
            justify="left",
            anchor="w",
            wraplength=self._wrap(),
        )
        text_label.pack(anchor="w")

        time_label = tk.Label(
            bubble,
            text=time_text,
            bg=bubble_bg,
            fg=time_fg,
            font=(style.FONT, max(self.font_size - 4, 8)),
        )
        time_label.pack(anchor="e", pady=(4, 0))

        for widget in (bubble, text_label, time_label):
            widget.bind(
                "<Button-3>",
                lambda e, t=text: self._popup_menu(e, t),
            )

        self._bubbles.append((text_label, time_label))
        self.after_idle(self.scroll_to_end)


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
        # ---- Messaging tab settings ----
        "message_mode": user_settings.get("message_mode", "conversation"),
        "display_recent_messages": bool(
            user_settings.get("display_recent_messages", 1)
        ),
        "hide_date_in_timestamp": bool(
            user_settings.get("hide_date_in_timestamp", 1)
        ),
        "incoming_behavior": user_settings.get(
            "incoming_behavior", "foreground"
        ),
        "keep_focus": bool(user_settings.get("keep_focus", 0)),
        "spell_check": bool(user_settings.get("spell_check", 1)),
        "font_size": user_settings.get("font_size", "Large"),
        "enter_to_send": bool(user_settings.get("enter_to_send", 1)),
        "quick_messages": settings.get_quick_messages(user_settings),
        # ---- Sound Events tab ----
        "sound_enabled": bool(user_settings.get("sound_enabled", 1)),
        "sound_incoming_message": bool(
            user_settings.get("sound_incoming_message", 1)
        ),
        "sound_broadcast": bool(user_settings.get("sound_broadcast", 1)),
        "sound_when": user_settings.get("sound_when", "background"),
        "sound_tune": user_settings.get("sound_tune", "Classic Bell"),
        "repeat_sound": bool(user_settings.get("repeat_sound", 0)),
        "repeat_seconds": int(user_settings.get("repeat_seconds", 5) or 5),
        "sound_user_online": bool(user_settings.get("sound_user_online", 0)),
        "sound_incoming_file": bool(
            user_settings.get("sound_incoming_file", 1)
        ),
        "sound_incoming_call": bool(
            user_settings.get("sound_incoming_call", 1)
        ),
    }

    style.set_theme(state["theme_mode"])
    style.save_preference(state["theme_mode"])

    win = tk.Tk()
    win.title("NEXO LAN Messenger")
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

    # Diagnostic: shows exactly which database file the app is reading
    try:
        _c = sqlite3.connect(DB_NAME, timeout=30)
        _n = _c.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        _c.close()
        print(f"[DATABASE] File in use: {os.path.abspath(DB_NAME)}")
        print(f"[DATABASE] Messages stored in it: {_n}")
    except sqlite3.Error as e:
        print("[DATABASE] Diagnostic error:", e)

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
    unread = {}          # username -> number of unread messages

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

    header = tk.Frame(win, bg=style.ACCENT, height=3)
    header.pack(fill="x")

    top_menu_frame = tk.Frame(win, bg=style.CARD)
    top_menu_frame.pack(fill="x")

    tk.Frame(win, bg=style.BORDER, height=1).pack(fill="x")

    main_frame = tk.Frame(win, bg=style.BG)
    main_frame.pack(fill="both", expand=True, pady=4)

    content_frame = tk.Frame(main_frame, bg=style.BG)
    content_frame.pack(side="right", fill="both", expand=True)

    tk.Label(
        content_frame,
        text="Select a user to start a conversation",
        font=style.ui_font(12),
        bg=style.BG,
        fg=style.MUTED
    ).pack(expand=True)

    users_frame = tk.Frame(
        main_frame,
        bg=style.CARD,
        width=220
    )
    users_frame.pack(side="left", fill="y", before=content_frame)
    users_frame.pack_propagate(False)

    tk.Label(
        users_frame,
        text="LAN Users",
        font=style.ui_font(11, True),
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

    # ------------------------------------------------------------------
    # Messaging-settings helpers
    # ------------------------------------------------------------------
    def font_px():
        return settings.FONT_SIZES.get(state["font_size"], 13)

    def format_timestamp(ts=None):
        """Time stamp text. Respects 'Do not show date in time stamp'."""
        fmt = "%I:%M %p" if state["hide_date_in_timestamp"] \
            else "%d-%m-%Y %I:%M %p"
        if ts is None:
            dt = datetime.now()
        else:
            try:
                # SQLite CURRENT_TIMESTAMP is stored in UTC
                dt = datetime.strptime(
                    str(ts)[:19], "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=timezone.utc).astimezone()
            except ValueError:
                dt = datetime.now()
        return dt.strftime(fmt)

    def apply_chat_fonts():
        """Applies the chosen Font Size to the open chat (live)."""
        size = font_px()
        try:
            conv = active_chat["conversation"]
            if conv is not None and conv.winfo_exists():
                conv.set_font(size)
            box = active_chat["input"]
            if box is not None and box.winfo_exists():
                box.config(font=(style.FONT, size))
        except tk.TclError:
            pass

    def append_message(sender, message, ts=None):
        conv = active_chat["conversation"]
        try:
            if conv is None or not conv.winfo_exists():
                return
        except tk.TclError:
            return

        is_me = sender == local_username
        conv.add_message(message, format_timestamp(ts), is_me)

    def check_spelling(event=None):
        """Red underline for misspelled words (needs pyspellchecker)."""
        box = active_chat["input"]
        try:
            if box is None or not box.winfo_exists():
                return
            box.tag_remove("misspelled", "1.0", "end")
            if not state["spell_check"] or _SPELL is None:
                return
            text = box.get("1.0", "end-1c")
            for m in WORD_RE.finditer(text):
                if m.end() == len(text):      # word still being typed
                    continue
                word = m.group().strip("'").lower()
                if len(word) > 2 and word in _SPELL.unknown([word]):
                    box.tag_add("misspelled",
                                f"1.0+{m.start()}c", f"1.0+{m.end()}c")
        except tk.TclError:
            pass

    def bring_to_front():
        try:
            if win.state() == "withdrawn":
                stop_tray()
            win.deiconify()
            win.lift()
            win.attributes("-topmost", True)
            win.after(300, lambda: win.attributes("-topmost", False))
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Sound events (Settings -> Sound Events)
    # ------------------------------------------------------------------
    repeat_jobs = {}                 # sender -> pending "repeat sound" timer
    app_started = time.monotonic()

    SOUND_KEYS = {
        "message": "sound_incoming_message",
        "broadcast": "sound_broadcast",
        "online": "sound_user_online",
        "file": "sound_incoming_file",
        "call": "sound_incoming_call",
    }

    def play_event_sound(kind):
        """Plays the sound of one event, only if 'Play sounds on' and that
        event are both enabled.  kind: message, broadcast, online, file, call
        (file / call / broadcast are ready for when those features exist)."""
        if not state["sound_enabled"] or not state.get(SOUND_KEYS[kind]):
            return

        try:
            if kind in ("message", "broadcast"):
                # the notification tune chosen in Settings -> Sound Events
                if not settings.play_tune(state["sound_tune"]):
                    win.bell()
            elif winsound is not None:
                tones = {
                    "message": winsound.MB_ICONASTERISK,
                    "broadcast": winsound.MB_ICONQUESTION,
                    "online": winsound.MB_OK,
                    "file": winsound.MB_ICONEXCLAMATION,
                    "call": winsound.MB_ICONHAND,
                }
                winsound.MessageBeep(tones[kind])
            else:
                win.bell()
        except Exception as e:
            print("[SOUND] Could not play sound:", e)

    def conversation_active(sender):
        """True when the user is looking at the chat with this sender."""
        try:
            return (
                state["message_mode"] != "single"
                and win.state() in ("normal", "zoomed")
                and win.focus_displayof() is not None
                and active_chat["username"] == sender
            )
        except tk.TclError:
            return False

    def stop_repeat(sender):
        job = repeat_jobs.pop(sender, None)

        if job is not None:
            try:
                win.after_cancel(job)
            except tk.TclError:
                pass

    def start_repeat(sender):
        """Repeat the sound every N seconds until the chat is active."""
        stop_repeat(sender)
        delay = max(1, int(state["repeat_seconds"])) * 1000

        def tick():
            repeat_jobs.pop(sender, None)

            try:
                if not win.winfo_exists():
                    return
            except tk.TclError:
                return

            if (
                conversation_active(sender)
                or not state["sound_enabled"]
                or not state["repeat_sound"]
            ):
                return

            play_event_sound("message")
            repeat_jobs[sender] = win.after(delay, tick)

        repeat_jobs[sender] = win.after(delay, tick)

    def incoming_sound(sender, was_active):
        """Sound for a new chat message (rules from Sound Events tab)."""
        if not state["sound_enabled"] or not state["sound_incoming_message"]:
            return

        # "only when conversation window stays in background"
        if state["sound_when"] == "background" and was_active:
            return

        play_event_sound("message")

        if state["repeat_sound"] and not was_active:
            start_repeat(sender)

    def open_user_chat(peer_username):
        active_chat["username"] = peer_username
        stop_repeat(peer_username)
        unread.pop(peer_username, None)
        render_users()

        for widget in content_frame.winfo_children():
            widget.destroy()

        chat_header = tk.Frame(content_frame, bg=style.CARD)
        chat_header.pack(fill="x")
        tk.Frame(content_frame, bg=style.BORDER, height=1).pack(fill="x")

        tk.Label(
            chat_header,
            text=f"💬  {peer_username}",
            font=style.HEADING_FONT,
            bg=style.CARD,
            fg=style.WHITE
        ).pack(side="left", padx=15, pady=15)

        conversation = ChatView(content_frame, font_px())
        conversation.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=(10, 4)
        )

        active_chat["conversation"] = conversation

        # Every saved message between the two users is always shown.
        # Nothing is ever removed from the chat.
        try:
            history = get_chat_history(local_username, peer_username)
            apply_chat_fonts()

            for sender, message, timestamp in history:
                append_message(sender, message, timestamp)

            print(
                f"[CHAT] Loaded {len(history)} saved message(s) "
                f"with {peer_username}"
            )
        except sqlite3.Error as e:
            print("[DATABASE] History error:", e)

        bottom_frame = tk.Frame(content_frame, bg=style.CARD)
        bottom_frame.pack(side="bottom", fill="x", padx=10, pady=10,
                          before=conversation)

        message_input = tk.Text(
            bottom_frame,
            font=(style.FONT, font_px()),
            width=1,
            height=3,
            wrap="word",
            bg=style.INPUT_BG,
            fg=style.BLACK,
            insertbackground=style.BLACK,
            relief="flat",
            padx=10,
            pady=8,
            highlightthickness=1,
            highlightbackground=style.BORDER,
            highlightcolor=style.ACCENT
        )
        message_input.pack(
            side="left",
            fill="x",
            expand=True,
            padx=8,
            pady=8
        )
        message_input.tag_config("misspelled", foreground=style.RED,
                                 underline=True)

        active_chat["input"] = message_input
        apply_chat_fonts()

        def send_message(text=None):
            from_box = text is None
            message = (
                message_input.get("1.0", "end-1c") if from_box else text
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
                    message,
                    success
                )
            except sqlite3.Error as e:
                messagebox.showerror(
                    "Database Error",
                    str(e),
                    parent=win
                )
                return

            append_message(local_username, message)

            if from_box:
                message_input.delete("1.0", "end")
                check_spelling()

        style.make_button(
            bottom_frame,
            "Send",
            send_message,
            kind="primary"
        ).pack(side="right", padx=8, pady=8)

        # ---- Quick Messages (one click = send) ----
        quick_btn = tk.Menubutton(
            bottom_frame,
            text="⚡ Quick",
            font=style.ui_font(10, True),
            bg=style.CARD,
            fg=style.WHITE,
            activebackground=style.CARD,
            activeforeground=style.ACCENT,
            relief="flat",
            cursor="hand2"
        )

        def fill_quick_menu():
            quick_menu.delete(0, "end")
            items = state["quick_messages"]
            if not items:
                quick_menu.add_command(label="(no quick messages)",
                                       state="disabled")
            for item in items:
                quick_menu.add_command(
                    label=item,
                    command=lambda t=item: send_message(t)
                )

        quick_menu = tk.Menu(quick_btn, tearoff=0, postcommand=fill_quick_menu)
        quick_btn.config(menu=quick_menu)
        quick_btn.pack(side="right", padx=4)

        # ---- Enter key behaviour ("Press Enter to send messages") ----
        def handle_enter(event):
            shift = bool(event.state & 0x1)
            ctrl = bool(event.state & 0x4)

            if state["enter_to_send"]:
                if shift:
                    return None          # Shift+Enter = new line
                send_message()
                return "break"

            if ctrl:                     # Enter off: Ctrl+Enter sends
                send_message()
                return "break"
            return None                  # plain Enter = new line

        message_input.bind("<Return>", handle_enter)
        message_input.bind("<KeyRelease>", check_spelling)
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

    # ------------------------------------------------------------------
    # Incoming messages
    # ------------------------------------------------------------------
    def show_single_popup(sender, message):
        """Single message mode: every message gets its own small window."""
        pop = tk.Toplevel(win)
        pop.title(f"Message from {sender}")
        pop.configure(bg=style.BG)
        style.center_window(pop, 400, 240)

        tk.Label(pop, text=sender, font=style.ui_font(13, True),
                 bg=style.BG, fg=style.ACCENT).pack(anchor="w", padx=15, pady=(12, 0))
        tk.Label(pop, text=format_timestamp(), bg=style.BG,
                 fg=style.MUTED).pack(anchor="w", padx=15)
        tk.Label(pop, text=message, wraplength=360, justify="left",
                 font=(style.FONT, font_px()), bg=style.BG,
                 fg=style.WHITE).pack(anchor="w", padx=15, pady=10)

        def close():
            stop_repeat(sender)
            pop.destroy()

        pop.protocol("WM_DELETE_WINDOW", close)

        def reply():
            pop.destroy()
            bring_to_front()
            open_user_chat(sender)

        btns = tk.Frame(pop, bg=style.BG)
        btns.pack(side="bottom", fill="x", padx=15, pady=12)
        style.make_button(btns, "Reply", reply, kind="primary", width=10
                          ).pack(side="right", padx=5)
        style.make_button(btns, "Close", close, kind="secondary",
                          width=10).pack(side="right", padx=5)

        # "Minimize incoming messages to taskbar" / "foreground"
        if state["incoming_behavior"] == "taskbar":
            pop.iconify()
        else:
            pop.lift()
            pop.attributes("-topmost", True)
            pop.after(300, lambda: pop.attributes("-topmost", False))
            if state["keep_focus"]:
                pop.focus_force()

    def notify_incoming(sender):
        """Conversation mode: foreground / taskbar behaviour."""
        if state["incoming_behavior"] == "foreground":
            bring_to_front()

            if active_chat["username"] is None:
                open_user_chat(sender)

            if state["keep_focus"]:
                win.focus_force()
                box = active_chat["input"]
                if box is not None and active_chat["username"] == sender:
                    box.focus_set()
        else:
            # Taskbar: do not steal the screen. If the app is hidden in the
            # tray, show it minimized in the taskbar instead.
            try:
                if win.state() == "withdrawn":
                    stop_tray()
                    win.iconify()
            except tk.TclError:
                pass

    def on_incoming_message(sender, message, uid=None):
        print(
            f"[HOME] Incoming message from {sender}: {message}"
        )

        try:
            save_message(
                sender,
                local_username,
                message,
                uid
            )
        except sqlite3.Error as e:
            print("[DATABASE] Incoming save error:", e)
            return

        def handle():
            try:
                if not win.winfo_exists():
                    return

                was_active = conversation_active(sender)

                if state["message_mode"] == "single":
                    show_single_popup(sender, message)
                    incoming_sound(sender, was_active)
                    return

                if active_chat["username"] == sender:
                    append_message(sender, message)
                else:
                    unread[sender] = unread.get(sender, 0) + 1
                    render_users()

                notify_incoming(sender)
                incoming_sound(sender, was_active)

            except tk.TclError as e:
                print("[UI] Incoming message UI error:", e)

        try:
            win.after(0, handle)
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
            count = unread.get(username, 0)

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
                font=style.ui_font(11)
            ).pack(side="left", padx=(0, 7))

            name_label = tk.Label(
                row,
                text=f"{username}  ({count})" if count else username,
                font=style.ui_font(11, bool(count)),
                bg=style.CARD,
                fg=style.ACCENT if count else style.WHITE,
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
        came_online = False

        for user in users:
            username = user.get("username")

            if not username or username == local_username:
                continue

            previous = known_users.get(username, {}).get("status", "Offline")

            if previous == "Offline" and user.get("status") == "Online":
                came_online = True

            current_names.add(username)
            known_users[username] = user.copy()

        for username in list(known_users):
            if username not in current_names:
                known_users[username]["status"] = "Offline"

        # (no sounds while the first users are still being discovered)
        if came_online and time.monotonic() - app_started > 8:
            play_event_sound("online")

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

    def apply_network_config():
        """Gives discovery the broadcast list and network tag chosen in
        Settings -> Network.  Runs at start-up and after every Settings save."""
        targets = netconfig.get_send_targets()
        tag = netconfig.get_network_tag()
        print(f"[NETWORK] Broadcast targets: {targets}  tag: {tag or '(none)'}")

        setter = getattr(discovery, "set_broadcasts", None)
        if not callable(setter):
            print("[NETWORK] discovery.py has no set_broadcasts() yet - "
                  "the Network settings are saved but not used for discovery.")
            return
        try:
            setter(targets, tag)
        except Exception as e:
            print("[NETWORK] Could not apply network settings:", e)

    apply_network_config()

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
            ),
            # ---- Messaging tab ----
            message_mode=new.get("message_mode", state["message_mode"]),
            display_recent_messages=bool(
                new.get("display_recent_messages", 1)
            ),
            hide_date_in_timestamp=bool(
                new.get("hide_date_in_timestamp", 1)
            ),
            incoming_behavior=new.get(
                "incoming_behavior", state["incoming_behavior"]
            ),
            keep_focus=bool(new.get("keep_focus", 0)),
            spell_check=bool(new.get("spell_check", 1)),
            font_size=new.get("font_size", state["font_size"]),
            enter_to_send=bool(new.get("enter_to_send", 1)),
            quick_messages=settings.get_quick_messages(new),
            sound_enabled=bool(new.get("sound_enabled", 1)),
            sound_incoming_message=bool(new.get("sound_incoming_message", 1)),
            sound_broadcast=bool(new.get("sound_broadcast", 1)),
            sound_when=new.get("sound_when", state["sound_when"]),
            sound_tune=new.get("sound_tune", state["sound_tune"]),
            repeat_sound=bool(new.get("repeat_sound", 0)),
            repeat_seconds=int(new.get("repeat_seconds", 5)),
            sound_user_online=bool(new.get("sound_user_online", 0)),
            sound_incoming_file=bool(new.get("sound_incoming_file", 1)),
            sound_incoming_call=bool(new.get("sound_incoming_call", 1)),
        )

        apply_chat_fonts()      # font size changes live in the open chat
        check_spelling()        # spell checking on/off live
        apply_network_config()  # new broadcasts / network tag take effect now
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

        for name in list(repeat_jobs):
            stop_repeat(name)

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
                    "Open NEXO LAN Messenger",
                    lambda icon, item: win.after(0, restore_window),
                    default=True
                ),
                pystray.MenuItem(
                    "Exit",
                    lambda icon, item: win.after(0, exit_app)
                )
            )

            tray_icon = pystray.Icon(
                "NEXO LAN Messenger",
                create_tray_image(),
                "NEXO LAN Messenger",
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
        menu_btn = tk.Button(
            top_menu_frame,
            text=f"{icon_text}  {item_title}",
            font=style.ui_font(10, True),
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
        )
        menu_btn.pack(side="left", padx=5, pady=3)
        style.hover_text(menu_btn)

    theme_btn = tk.Button(
        top_menu_frame,
        text="🌓  Theme",
        font=style.ui_font(10, True),
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
    )
    theme_btn.pack(side="right", padx=5, pady=3)
    style.hover_text(theme_btn)

    win.bind_all("<KeyPress>", mark_activity)
    win.bind_all("<Button>", mark_activity)
    win.bind_all("<Motion>", mark_activity)

    win.protocol("WM_DELETE_WINDOW", hide_to_tray)

    discovery.start()

    atexit.register(discovery.stop)

    status_after_id = win.after(1000, check_status)
    theme_after_id = win.after(10000, follow_system_theme)

    render_users()

    print("[HOME] NEXO LAN Messenger started successfully.")

    win.mainloop()


if __name__ == "__main__":
    from login import show_login
    show_login()