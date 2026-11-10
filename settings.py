import json
import math
import os
import sqlite3
import struct
import wave
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from contextlib import contextmanager
import style
import netconfig
import filestore

try:
    import winsound
except ImportError:
    winsound = None

DB_NAME = style.data_path("lan_connect_project.db")

DEFAULT_QUICK_MESSAGES = ["OK", "Thanks", "Busy right now, will reply soon",
                          "Call me please", "Be right back"]

# Message font sizes (used by Messaging tab and by your chat window)
FONT_SIZES = {"Normal": 10, "Large": 13, "Extra large": 16}

DEFAULTS = {
    "away_on_screensaver": 1, "show_taskbar_when_minimized": 1,
    "hide_offline_users": 0,
    "theme": "Auto", "language": "English",
    "display_name": "", "department": "", "listening_port": "5000",
    "discover_peers": 1, "download_folder": "", "sound_enabled": 1,
    "logging_enabled": 1, "enter_to_send": 1,
    "inactive_on_minimize": 1, "inactive_minutes": 5,
    # ---- Message Window (Messaging tab) ----
    "message_mode": "conversation",          # "single" or "conversation"
    "display_recent_messages": 1,
    "hide_date_in_timestamp": 1,
    "incoming_behavior": "foreground",       # "taskbar" or "foreground"
    "keep_focus": 0,
    "spell_check": 1,
    "font_size": "Large",                    # Normal / Large / Extra large
    "quick_messages": json.dumps(DEFAULT_QUICK_MESSAGES),
    # ---- Sound Events tab ("sound_enabled" = Play sounds on) ----
    "sound_incoming_message": 1,
    "sound_broadcast": 1,
    "sound_when": "background",              # "always" or "background"
    "repeat_sound": 0,
    "repeat_seconds": 5,
    "sound_user_online": 0,
    "sound_incoming_file": 1,
    "sound_incoming_call": 1,
    "sound_tune": "Classic Bell",            # notification tune for messages
    # ---- File Transfer tab ("download_folder" = the custom folder) ----
    "file_accept": "auto",                   # "auto" or "ask"
    "show_image_previews": 1,
    "incoming_location": "system",           # "system" or "custom"
    "custom_user_subfolder": 0,
    "save_mode": "per_transfer",             # "per_transfer" or "one_folder"
    "sender_subfolders": 1,
    "if_file_exists": "rename",              # "rename" / "overwrite" / "skip"
}

@contextmanager
def _db():
    conn = sqlite3.connect(DB_NAME, timeout=30)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def ensure_settings_table():
    definitions = {
        "away_on_screensaver": "INTEGER NOT NULL DEFAULT 1",
        "show_taskbar_when_minimized": "INTEGER NOT NULL DEFAULT 1",
        "hide_offline_users": "INTEGER NOT NULL DEFAULT 0",
        "legacy_view": "INTEGER NOT NULL DEFAULT 0",
        "theme": "TEXT NOT NULL DEFAULT 'Auto'",
        "language": "TEXT NOT NULL DEFAULT 'English'",
        "display_name": "TEXT DEFAULT ''",
        "department": "TEXT DEFAULT ''",
        "listening_port": "TEXT DEFAULT '5000'",
        "discover_peers": "INTEGER NOT NULL DEFAULT 1",
        "download_folder": "TEXT DEFAULT ''",
        "sound_enabled": "INTEGER NOT NULL DEFAULT 1",
        "logging_enabled": "INTEGER NOT NULL DEFAULT 1",
        "enter_to_send": "INTEGER NOT NULL DEFAULT 1",
        "inactive_on_minimize": "INTEGER NOT NULL DEFAULT 1",
        "inactive_minutes": "INTEGER NOT NULL DEFAULT 5",
        "message_mode": "TEXT NOT NULL DEFAULT 'conversation'",
        "display_recent_messages": "INTEGER NOT NULL DEFAULT 1",
        "hide_date_in_timestamp": "INTEGER NOT NULL DEFAULT 1",
        "incoming_behavior": "TEXT NOT NULL DEFAULT 'foreground'",
        "keep_focus": "INTEGER NOT NULL DEFAULT 0",
        "spell_check": "INTEGER NOT NULL DEFAULT 1",
        "font_size": "TEXT NOT NULL DEFAULT 'Large'",
        "quick_messages": "TEXT DEFAULT ''",
        "sound_incoming_message": "INTEGER NOT NULL DEFAULT 1",
        "sound_broadcast": "INTEGER NOT NULL DEFAULT 1",
        "sound_when": "TEXT NOT NULL DEFAULT 'background'",
        "repeat_sound": "INTEGER NOT NULL DEFAULT 0",
        "repeat_seconds": "INTEGER NOT NULL DEFAULT 5",
        "sound_user_online": "INTEGER NOT NULL DEFAULT 0",
        "sound_incoming_file": "INTEGER NOT NULL DEFAULT 1",
        "sound_incoming_call": "INTEGER NOT NULL DEFAULT 1",
        "sound_tune": "TEXT NOT NULL DEFAULT 'Classic Bell'",
        "file_accept": "TEXT NOT NULL DEFAULT 'auto'",
        "show_image_previews": "INTEGER NOT NULL DEFAULT 1",
        "incoming_location": "TEXT NOT NULL DEFAULT 'system'",
        "custom_user_subfolder": "INTEGER NOT NULL DEFAULT 0",
        "save_mode": "TEXT NOT NULL DEFAULT 'per_transfer'",
        "sender_subfolders": "INTEGER NOT NULL DEFAULT 1",
        "if_file_exists": "TEXT NOT NULL DEFAULT 'rename'",
    }
    with _db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS app_settings
            (user_email TEXT PRIMARY KEY)""")
        existing = {r[1] for r in conn.execute("PRAGMA table_info(app_settings)")}
        for name, definition in definitions.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE app_settings ADD COLUMN {name} {definition}")

def load_settings(user_email=""):
    ensure_settings_table()
    result = DEFAULTS.copy()
    if user_email:
        with _db() as conn:
            cur = conn.execute(
                "SELECT * FROM app_settings WHERE user_email=?", (user_email,)
            )
            rows = cur.fetchall()          # read everything: no lock is left
            row = rows[0] if rows else None
            cols = [d[0] for d in cur.description]
            cur.close()
        if row:
            saved = dict(zip(cols, row))
            result.update({k: saved[k] for k in DEFAULTS
                           if k in saved and saved[k] not in (None, "")})
    return result

def save_settings(user_email, values):
    if not user_email:
        raise ValueError("Logged-in user's email is required.")
    ensure_settings_table()
    data = DEFAULTS.copy()
    data.update(values)
    cols = ["user_email"] + list(DEFAULTS)
    with _db() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO app_settings ({','.join(cols)}) "
            f"VALUES ({','.join('?' for _ in cols)})",
            [user_email] + [data[k] for k in DEFAULTS],
        )

# ---------------------------------------------------------------------------
# Notification tunes: small WAV files created automatically on first use
# ---------------------------------------------------------------------------
SAMPLE_RATE = 22050
SOUND_DIR = os.path.join(os.path.dirname(os.path.abspath(DB_NAME)), "sounds")
DEFAULT_TUNE = "Classic Bell"

# timbre -> parts of the sound: (frequency ratio, volume, decay speed)
TIMBRES = {
    "bell":    [(1.0, 1.0, 3.0), (2.0, 0.5, 4.0), (2.76, 0.35, 5.0), (5.4, 0.2, 7.0)],
    "chime":   [(1.0, 1.0, 2.5), (2.0, 0.4, 3.5), (3.0, 0.2, 4.5)],
    "marimba": [(1.0, 1.0, 9.0), (4.0, 0.4, 14.0), (10.0, 0.15, 20.0)],
    "soft":    [(1.0, 1.0, 5.0), (2.0, 0.15, 8.0)],
    "digital": [(1.0, 1.0, 6.0), (3.0, 0.3, 8.0), (5.0, 0.15, 10.0)],
}

# tune name -> notes: (frequency Hz, start second, length seconds, timbre)
TUNES = {
    "Classic Bell":   [(1046.5, 0.00, 1.4, "bell")],
    "Double Chime":   [(784.0, 0.00, 0.9, "chime"), (1046.5, 0.25, 1.3, "chime")],
    "Ding Dong":      [(880.0, 0.00, 1.0, "bell"), (659.3, 0.50, 1.5, "bell")],
    "Marimba":        [(659.3, 0.00, 0.5, "marimba"), (784.0, 0.12, 0.5, "marimba"),
                       (1046.5, 0.24, 0.7, "marimba")],
    "Soft Notify":    [(523.3, 0.00, 0.9, "soft"), (659.3, 0.18, 1.2, "soft")],
    "Digital Alert":  [(1318.5, 0.00, 0.25, "digital"), (1568.0, 0.15, 0.40, "digital")],
}


def tune_names():
    return list(TUNES)


def _render_tune(notes):
    total = max(start + length for _f, start, length, _t in notes) + 0.05
    count = int(total * SAMPLE_RATE)
    buf = [0.0] * count

    for freq, start, length, timbre in notes:
        first = int(start * SAMPLE_RATE)
        for i in range(int(length * SAMPLE_RATE)):
            idx = first + i
            if idx >= count:
                break
            t = i / SAMPLE_RATE
            value = 0.0
            for ratio, volume, decay in TIMBRES[timbre]:
                f = freq * ratio
                if f < SAMPLE_RATE / 2:
                    value += volume * math.exp(-decay * t) * math.sin(
                        2 * math.pi * f * t)
            fade_in = min(1.0, t / 0.004)                 # no click at the start
            fade_out = max(0.0, min(1.0, (length - t) / 0.03))
            buf[idx] += value * fade_in * fade_out

    peak = max(abs(x) for x in buf) or 1.0
    scale = 0.8 * 32767 / peak
    return b"".join(struct.pack("<h", int(x * scale)) for x in buf)


def tune_path(name):
    """Returns the WAV file of a tune (creates it the first time)."""
    if name not in TUNES:
        name = DEFAULT_TUNE
    os.makedirs(SOUND_DIR, exist_ok=True)
    path = os.path.join(SOUND_DIR, name.lower().replace(" ", "_") + ".wav")

    if not os.path.exists(path):
        temp = path + ".tmp"
        with wave.open(temp, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(_render_tune(TUNES[name]))
        os.replace(temp, path)

    return path


def play_tune(name):
    """Plays a notification tune. Returns False if it could not be played."""
    if winsound is None:
        return False
    try:
        winsound.PlaySound(tune_path(name),
                           winsound.SND_FILENAME | winsound.SND_ASYNC)
        return True
    except Exception as e:
        print("[SOUND] Could not play tune:", e)
        return False


def _local_user_name(user_email, discovery=None):
    """The logged-in user's name (used in 'Create \\<name> subfolder')."""
    name = getattr(discovery, "username", "") if discovery is not None else ""
    if name:
        return str(name)
    try:
        with _db() as conn:
            row = conn.execute(
                "SELECT firstname, lastname FROM register WHERE email=?",
                (user_email,)).fetchone()
        if row:
            return " ".join(part for part in row if part).strip() or user_email
    except sqlite3.Error:
        pass
    return user_email or "User"


# ---------- Helpers for your chat / message window ----------
def message_font(size_name):
    """Returns a tkinter font tuple for the chosen font size."""
    return (style.FONT, FONT_SIZES.get(size_name, 13))

def get_quick_messages(settings_dict):
    """Returns the saved quick messages as a Python list."""
    try:
        items = json.loads(settings_dict.get("quick_messages") or "[]")
        return [str(i) for i in items]
    except (ValueError, TypeError):
        return list(DEFAULT_QUICK_MESSAGES)

def open_settings(user_email="", main_window=None, discovery=None, on_save=None):
    data = load_settings(user_email)
    win = tk.Toplevel(main_window) if main_window else tk.Toplevel()
    win.title("Settings")
    # Tall enough for every tab (no scrolling), but never taller than the screen
    height = min(650, win.winfo_screenheight() - 90)
    style.center_window(win, 850, int(height))
    win.minsize(700, min(600, height))
    win.configure(bg=style.BG)
    style.setup_ttk(win)

    # Footer is packed first so the OK / Cancel buttons are always visible
    footer = tk.Frame(win, bg=style.BG)
    footer.pack(side="bottom", fill="x", padx=12, pady=(0, 12))

    notebook = ttk.Notebook(win)
    notebook.pack(fill="both", expand=True, padx=10, pady=(10, 6))
    tabs = {}
    for name in ("General", "Messaging", "Sound Events",
                 "Network", "File Transfer", "Logging", "Hot Keys"):
        tabs[name] = tk.Frame(notebook, bg=style.BG)
        notebook.add(tabs[name], text=name)

    def heading(tab, title):
        tk.Label(tab, text=title, font=style.ui_font(17, True), bg=style.BG,
                 fg=style.WHITE).pack(anchor="w", padx=22, pady=(10, 6))

    def section(tab, title):
        tk.Label(tab, text=title, bg=style.BG, fg=style.WHITE,
                 font=style.ui_font(11, True)).pack(anchor="w", padx=25, pady=(5, 2))
        tk.Frame(tab, bg=style.BORDER, height=1).pack(fill="x", padx=25, pady=4)

    vars_ = {}
    def check(tab, label, key, padx=28, pady=2, command=None):
        vars_[key] = tk.BooleanVar(value=bool(data[key]))
        cb = tk.Checkbutton(tab, text=label, variable=vars_[key], command=command,
                            bg=style.BG,
                            fg=style.WHITE, selectcolor=style.INPUT_BG,
                            activebackground=style.BG, activeforeground=style.WHITE,
                            disabledforeground="#888888", highlightthickness=0)
        cb.pack(anchor="w", padx=padx, pady=pady)
        return cb

    def radio(tab, label, var, value, padx=28, command=None):
        rb = tk.Radiobutton(tab, text=label, variable=var, value=value,
                            command=command, bg=style.BG, fg=style.WHITE,
                            selectcolor=style.INPUT_BG, activebackground=style.BG,
                            activeforeground=style.WHITE, highlightthickness=0)
        rb.pack(anchor="w", padx=padx, pady=2)
        return rb

    # General options matching the supplied screenshot
    tab = tabs["General"]
    heading(tab, "General")
    tk.Label(tab, text="User List", bg=style.BG, fg=style.WHITE,
             font=style.ui_font(11, True)).pack(anchor="w", padx=25, pady=(5, 2))
    tk.Frame(tab, bg=style.BORDER, height=1).pack(fill="x", padx=25, pady=4)
    check(tab, 'Change status to "Away" when screen saver starts', "away_on_screensaver")
    check(tab, "Set status to Inactive when the application is minimized",
          "inactive_on_minimize")
    minutes_row = tk.Frame(tab, bg=style.BG)
    minutes_row.pack(anchor="w", padx=50, pady=2)
    tk.Label(minutes_row, text="Change to Inactive after", bg=style.BG,
             fg=style.WHITE).pack(side="left")
    minutes_entry = style.make_entry(minutes_row, width=5, justify="center")
    minutes_entry.insert(0, str(data["inactive_minutes"]))
    minutes_entry.pack(side="left", padx=8, ipady=2)
    tk.Label(minutes_row, text="minute(s) of being minimized", bg=style.BG,
             fg=style.WHITE).pack(side="left")
    check(tab, "Show taskbar button when list is minimized", "show_taskbar_when_minimized")
    check(tab, "Hide offline users", "hide_offline_users")

    tk.Label(tab, text="Appearance", bg=style.BG, fg=style.WHITE,
             font=style.ui_font(11, True)).pack(anchor="w", padx=25, pady=(5, 2))
    tk.Frame(tab, bg=style.BORDER, height=1).pack(fill="x", padx=25, pady=4)
    theme = tk.StringVar(value=data["theme"])
    language = tk.StringVar(value="English")
    row = tk.Frame(tab, bg=style.BG); row.pack(anchor="w", padx=50, pady=4)
    tk.Label(row, text="Theme:", bg=style.BG, fg=style.WHITE).pack(side="left", padx=8)
    ttk.Combobox(row, textvariable=theme, values=["Auto", "Light", "Dark"],
                 state="readonly", width=14).pack(side="left")
    row2 = row  # Language sits on the same line as Theme to save height
    tk.Label(row2, text="Language:", bg=style.BG, fg=style.WHITE).pack(side="left", padx=(30, 8))
    ttk.Combobox(row2, textvariable=language, values=["English"],
                 state="readonly", width=17).pack(side="left")

    # ------------------------------------------------------------------
    # Messaging tab  ->  "Message Window" screen
    # ------------------------------------------------------------------
    tab = tabs["Messaging"]
    heading(tab, "Message Window")
    section(tab, "Message Window")

    message_mode = tk.StringVar(value=data["message_mode"])
    incoming = tk.StringVar(value=data["incoming_behavior"])
    font_size = tk.StringVar(value=data["font_size"])

    def refresh_message_options():
        conv = message_mode.get() == "conversation"
        recent_cb.config(state="normal" if conv else "disabled")
        nodate_cb.config(state="normal" if conv else "disabled")
        fore = incoming.get() == "foreground"
        keep_cb.config(state="normal" if fore else "disabled")

    radio(tab, "Single message mode", message_mode, "single",
          command=lambda: refresh_message_options())
    radio(tab, "Conversation mode", message_mode, "conversation",
          command=lambda: refresh_message_options())
    recent_cb = check(tab, "Display recent messages", "display_recent_messages", padx=55)
    nodate_cb = check(tab, "Do not show date in time stamp", "hide_date_in_timestamp", padx=55)

    tk.Frame(tab, bg=style.BG, height=6).pack()
    radio(tab, "Minimize incoming messages to taskbar", incoming, "taskbar",
          command=lambda: refresh_message_options())
    radio(tab, "Set incoming messages foreground", incoming, "foreground",
          command=lambda: refresh_message_options())
    keep_cb = check(tab, "Keep keyboard focus in message window", "keep_focus", padx=55)

    tk.Frame(tab, bg=style.BG, height=6).pack()
    check(tab, "Enable spell checking", "spell_check")
    check(tab, "Press Enter to send messages", "enter_to_send")

    # ----- Quick Messages (link opens a small editor) -----
    quick_list = get_quick_messages(data)

    def open_quick_messages():
        dlg = tk.Toplevel(win)
        dlg.title("Quick Messages")
        dlg.configure(bg=style.BG)
        dlg.transient(win)
        style.center_window(dlg, 430, 400)
        dlg.resizable(False, False)

        tk.Label(dlg, text="Quick Messages", font=style.ui_font(14, True),
                 bg=style.BG, fg=style.WHITE).pack(anchor="w", padx=15, pady=(12, 4))
        tk.Label(dlg, text="Ready-made replies you can send with one click.",
                 bg=style.BG, fg=style.WHITE).pack(anchor="w", padx=15)

        lb = tk.Listbox(dlg, height=10, bg=style.INPUT_BG, fg=style.WHITE,
                        highlightthickness=1, highlightbackground=style.BORDER,
                        selectbackground=style.ACCENT, selectforeground=style.ON_ACCENT,
                        activestyle="none", exportselection=False)
        lb.pack(fill="both", expand=True, padx=15, pady=8)
        for item in quick_list:
            lb.insert("end", item)

        text_var = tk.StringVar()
        entry = style.make_entry(dlg, textvariable=text_var)
        entry.pack(fill="x", padx=15, ipady=3)

        def on_select(_=None):
            sel = lb.curselection()
            if sel:
                text_var.set(lb.get(sel[0]))
        lb.bind("<<ListboxSelect>>", on_select)

        def add():
            t = text_var.get().strip()
            if t:
                lb.insert("end", t)
                text_var.set("")

        def update():
            sel = lb.curselection()
            t = text_var.get().strip()
            if sel and t:
                lb.delete(sel[0])
                lb.insert(sel[0], t)
                lb.selection_set(sel[0])

        def delete():
            sel = lb.curselection()
            if sel:
                lb.delete(sel[0])
                text_var.set("")

        def done():
            quick_list[:] = list(lb.get(0, "end"))
            dlg.destroy()

        btns = tk.Frame(dlg, bg=style.BG)
        btns.pack(fill="x", padx=15, pady=10)
        style.make_button(btns, "Add", add, kind="secondary", width=8).pack(side="left", padx=(0, 5))
        style.make_button(btns, "Update", update, kind="secondary", width=8).pack(side="left", padx=5)
        style.make_button(btns, "Delete", delete, kind="secondary", width=8).pack(side="left", padx=5)
        style.make_button(btns, "OK", done, kind="primary", width=8).pack(side="right")
        dlg.grab_set()

    link = tk.Label(tab, text="Quick Messages Settings...", bg=style.BG, fg=style.ACCENT,
                    cursor="hand2", font=(style.FONT, 10, "underline"))
    link.pack(anchor="e", padx=40, pady=(2, 0))
    link.bind("<Button-1>", lambda e: open_quick_messages())

    # ----- Font size + live preview -----
    section(tab, "Font Size")
    fs = tk.Frame(tab, bg=style.BG)
    fs.pack(fill="x", padx=28, pady=2)
    left = tk.Frame(fs, bg=style.BG)
    left.pack(side="left", anchor="n")

    preview_holder = tk.Frame(fs, bg=style.INPUT_BG, highlightthickness=1,
                              highlightbackground=style.BORDER, width=190, height=80)
    preview = tk.Label(preview_holder, text="Text Sample", bg=style.INPUT_BG,
                       fg=style.WHITE, font=message_font(font_size.get()))

    def update_preview():
        preview.config(font=message_font(font_size.get()))

    for label, value in (("Normal", "Normal"), ("Large", "Large"),
                         ("Extra large", "Extra large")):
        rb = tk.Radiobutton(left, text=label, variable=font_size, value=value,
                            command=update_preview, bg=style.BG, fg=style.WHITE,
                            selectcolor=style.INPUT_BG, activebackground=style.BG,
                            activeforeground=style.WHITE, highlightthickness=0)
        rb.pack(anchor="w", pady=2)

    tk.Label(fs, text="Preview:", bg=style.BG, fg=style.WHITE).pack(
        side="left", anchor="n", padx=(40, 8))
    preview_holder.pack(side="left", anchor="n")
    preview_holder.pack_propagate(False)
    preview.pack(expand=True)

    refresh_message_options()

    # ------------------------------------------------------------------
    # Sound Events tab  ->  "Sound Events List" screen
    # ------------------------------------------------------------------
    tab = tabs["Sound Events"]
    heading(tab, "Sound Events List")
    sound_when = tk.StringVar(value=data["sound_when"])

    def refresh_sound_options():
        master = bool(vars_["sound_enabled"].get())
        for cb in (msg_cb, bc_cb, online_cb, file_cb, call_cb):
            cb.config(state="normal" if master else "disabled")
        tune_combo.config(state="readonly" if master else "disabled")
        timing = master and (vars_["sound_incoming_message"].get()
                             or vars_["sound_broadcast"].get())
        for rb in (when_any, when_bg, repeat_cb):
            rb.config(state="normal" if timing else "disabled")
        repeat_on = timing and vars_["repeat_sound"].get()
        repeat_entry.config(state="normal" if repeat_on else "disabled")

    def sound_changed():
        refresh_sound_options()

    check(tab, "Play sounds on", "sound_enabled", command=sound_changed)
    msg_cb = check(tab, "Incoming message", "sound_incoming_message",
                   padx=50, command=sound_changed)
    bc_cb = check(tab, "Incoming broadcast message", "sound_broadcast",
                  padx=50, command=sound_changed)
    when_any = radio(tab, "any time message comes in", sound_when, "always", padx=80)
    when_bg = radio(tab, "only when conversation window stays in background",
                    sound_when, "background", padx=80)

    repeat_row = tk.Frame(tab, bg=style.BG)
    repeat_row.pack(anchor="w", padx=80, pady=2)
    vars_["repeat_sound"] = tk.BooleanVar(value=bool(data["repeat_sound"]))
    repeat_cb = tk.Checkbutton(repeat_row, text="Repeat sound every",
                               variable=vars_["repeat_sound"], command=sound_changed,
                               bg=style.BG, fg=style.WHITE, selectcolor=style.INPUT_BG,
                               activebackground=style.BG, activeforeground=style.WHITE,
                               disabledforeground="#888888", highlightthickness=0)
    repeat_cb.pack(side="left")
    repeat_entry = style.make_entry(repeat_row, width=5, justify="center")
    repeat_entry.insert(0, str(data["repeat_seconds"]))
    repeat_entry.pack(side="left", padx=6, ipady=2)
    tk.Label(repeat_row, text="seconds", bg=style.BG, fg=style.WHITE).pack(side="left")
    tk.Label(tab, text="until message window is active", bg=style.BG,
             fg=style.WHITE).pack(anchor="w", padx=106)

    online_cb = check(tab, "User is online", "sound_user_online", padx=50)
    file_cb = check(tab, "Incoming file", "sound_incoming_file", padx=50)
    call_cb = check(tab, "Incoming audio/video call", "sound_incoming_call", padx=50)

    # ----- Notification tune (plays for incoming messages) -----
    section(tab, "Notification Tune")
    tune_var = tk.StringVar(
        value=data["sound_tune"] if data["sound_tune"] in TUNES else DEFAULT_TUNE)
    tune_row = tk.Frame(tab, bg=style.BG)
    tune_row.pack(anchor="w", padx=50, pady=4)
    tk.Label(tune_row, text="Message tune:", bg=style.BG,
             fg=style.WHITE).pack(side="left", padx=(0, 8))
    tune_combo = ttk.Combobox(tune_row, textvariable=tune_var, values=tune_names(),
                              state="readonly", width=22)
    tune_combo.pack(side="left")

    def preview_tune(_=None):
        if not play_tune(tune_var.get()):
            win.bell()

    tune_combo.bind("<<ComboboxSelected>>", preview_tune)   # plays when you pick
    style.make_button(tune_row, "▶ Play", preview_tune, kind="secondary",
                      width=8).pack(side="left", padx=8)
    refresh_sound_options()

    # Logging
    heading(tabs["Logging"], "Logging Settings")
    check(tabs["Logging"], "Enable application logging", "logging_enabled")

    # ------------------------------------------------------------------
    # Network tab: settings location, broadcasts, network tagging
    # ------------------------------------------------------------------
    tab = tabs["Network"]
    heading(tab, "Network Settings")

    net = netconfig.load_config()
    own = {                                  # values used in "system-defined" mode
        "broadcasts": list(net["broadcasts"]),
        "include_system": net["include_system"],
        "include_global": net["include_global"],
        "tag_enabled": net["tag_enabled"],
        "tag": net["tag"],
    }
    file_state = {"cfg": None, "path": net["file"]}
    start_note = ""
    if net["file"]:
        try:
            file_state["cfg"] = netconfig.read_settings_file(net["file"])
        except ValueError:
            if net["mode"] == "file":
                start_note = "The saved settings file could not be loaded."

    net_loc = tk.StringVar(
        value="file" if net["mode"] == "file" and file_state["cfg"] else "system")
    net_file = tk.StringVar(value=net["file"])
    inc_sys = tk.BooleanVar(value=own["include_system"])
    inc_glob = tk.BooleanVar(value=own["include_global"])

    # ----- Network Settings Location -----
    section(tab, "Network Settings Location")
    radio(tab, "System-defined location (change settings below)", net_loc, "system",
          command=lambda: on_location_changed())
    radio(tab, "Load network settings from file (read-only):", net_loc, "file",
          command=lambda: on_location_changed())

    file_row = tk.Frame(tab, bg=style.BG)
    file_row.pack(fill="x", padx=50, pady=(2, 0))
    net_entry = style.make_entry(
        file_row, textvariable=net_file, state="disabled",
        disabledbackground=style.INPUT_BG, disabledforeground=style.MUTED,
        readonlybackground=style.INPUT_BG)
    net_entry.pack(side="left", fill="x", expand=True, ipady=3)
    browse_btn = style.make_button(file_row, "...", lambda: browse_file(),
                                   kind="secondary", width=3, pady=3,
                                   font=style.SMALL_FONT)
    browse_btn.pack(side="left", padx=(6, 25))
    file_note = tk.Label(tab, text=start_note, bg=style.BG, fg=style.RED,
                         font=style.SMALL_FONT)
    if start_note:
        file_note.pack(anchor="w", padx=50, after=file_row)

    # ----- Connectivity -----
    section(tab, "Connectivity")
    tk.Label(tab, text="Broadcasts:", bg=style.BG, fg=style.WHITE).pack(
        anchor="w", padx=28)

    conn_row = tk.Frame(tab, bg=style.BG)
    conn_row.pack(fill="x", padx=28, pady=(2, 4))

    list_holder = tk.Frame(conn_row, bg=style.INPUT_BG, highlightthickness=1,
                           highlightbackground=style.BORDER, height=104)
    list_holder.pack(side="left", fill="x", expand=True)
    list_holder.pack_propagate(False)
    bc_list = tk.Listbox(list_holder, bg=style.INPUT_BG, fg=style.TEXT_INPUT, bd=0,
                         highlightthickness=0, selectbackground=style.ACCENT,
                         selectforeground=style.ON_ACCENT, activestyle="none",
                         exportselection=False, font=style.INPUT_FONT)
    bc_list.pack(fill="both", expand=True, padx=6, pady=4)
    bc_hint = tk.Label(list_holder, bg=style.INPUT_BG, fg=style.MUTED)

    btn_col = tk.Frame(conn_row, bg=style.BG)
    btn_col.pack(side="left", fill="y", padx=(10, 0))
    add_btn = style.make_button(btn_col, "Add...", lambda: add_broadcast(),
                                kind="secondary", width=9, pady=4)
    add_btn.pack(pady=(0, 6))
    del_btn = style.make_button(btn_col, "Delete", lambda: delete_broadcast(),
                                kind="secondary", width=9, pady=4)
    del_btn.pack()
    export_btn = style.make_button(btn_col, "Export...", lambda: export_network(),
                                   kind="secondary", width=9, pady=4)
    export_btn.pack(side="bottom")
    bc_list.bind("<Delete>", lambda e: delete_broadcast())

    def net_check(text, var):
        cb = tk.Checkbutton(tab, text=text, variable=var,
                            command=lambda: on_include_changed(),
                            bg=style.BG, fg=style.WHITE, selectcolor=style.INPUT_BG,
                            activebackground=style.BG, activeforeground=style.WHITE,
                            disabledforeground=style.MUTED, highlightthickness=0)
        cb.pack(anchor="w", padx=28, pady=1)
        return cb

    cb_sys = net_check("Include system-calculated broadcasts", inc_sys)
    cb_glob = net_check("Include network-wide broadcast", inc_glob)

    tag_row = tk.Frame(tab, bg=style.BG)
    tag_row.pack(anchor="w", padx=28, pady=(4, 0))
    tk.Label(tag_row, text="Network Tagging:", bg=style.BG,
             fg=style.WHITE).pack(side="left")
    tag_link = tk.Label(tag_row, text="Disabled", bg=style.BG, fg=style.ACCENT,
                        cursor="hand2", font=(style.FONT, 10, "underline"))
    tag_link.pack(side="left", padx=(6, 0))
    tag_link.bind("<Button-1>", lambda e: edit_tag())

    # ----- Chat port (kept from the old Network tab) -----
    tk.Frame(tab, bg=style.BORDER, height=1).pack(fill="x", padx=25, pady=(10, 0))
    port_row = tk.Frame(tab, bg=style.BG)
    port_row.pack(anchor="w", padx=28, pady=(8, 0))
    tk.Label(port_row, text="Listening port:", bg=style.BG,
             fg=style.WHITE).pack(side="left")
    port = style.make_entry(port_row, width=8, justify="center")
    port.insert(0, data["listening_port"])
    port.pack(side="left", padx=8, ipady=2)
    vars_["discover_peers"] = tk.BooleanVar(value=bool(data["discover_peers"]))
    tk.Checkbutton(port_row, text="Enable peer discovery",
                   variable=vars_["discover_peers"], bg=style.BG, fg=style.WHITE,
                   selectcolor=style.INPUT_BG, activebackground=style.BG,
                   activeforeground=style.WHITE, highlightthickness=0
                   ).pack(side="left", padx=(20, 0))

    # ----- Network tab behaviour -----
    def view_cfg():
        """(settings being shown, can the user edit them?)"""
        if net_loc.get() == "file" and file_state["cfg"] is not None:
            return file_state["cfg"], False
        return own, True

    def refresh_net_widgets():
        cfg, editable = view_cfg()

        net_entry.config(state="disabled" if editable else "readonly")
        browse_btn.config(state="disabled" if editable else "normal")

        bc_list.delete(0, "end")
        for address in cfg["broadcasts"]:
            bc_list.insert("end", address)

        if cfg["broadcasts"]:
            bc_hint.place_forget()
        else:
            if cfg["include_system"]:
                hint = "Using system broadcasts."
            elif cfg["include_global"]:
                hint = "Using the network-wide broadcast only."
            else:
                hint = "No broadcasts selected."
            bc_hint.config(text=hint)
            bc_hint.place(relx=0.5, rely=0.5, anchor="center")

        inc_sys.set(cfg["include_system"])
        inc_glob.set(cfg["include_global"])

        state = "normal" if editable else "disabled"
        for widget in (cb_sys, cb_glob, add_btn, del_btn):
            widget.config(state=state)

        if cfg["tag_enabled"] and cfg["tag"]:
            tag_link.config(text=f"Enabled ({cfg['tag']})")
        else:
            tag_link.config(text="Disabled")
        tag_link.config(fg=style.ACCENT if editable else style.MUTED,
                        cursor="hand2" if editable else "arrow")

    def set_note(text):
        file_note.config(text=text)
        if text:
            file_note.pack(anchor="w", padx=50, after=file_row)
        else:
            file_note.pack_forget()

    def load_settings_file(path):
        try:
            cfg = netconfig.read_settings_file(path)
        except ValueError as exc:
            messagebox.showerror("Network Settings File", str(exc), parent=win)
            return False
        file_state["cfg"] = cfg
        file_state["path"] = path
        net_file.set(path)
        set_note("")
        return True

    def browse_file():
        path = filedialog.askopenfilename(
            parent=win, title="Load network settings",
            filetypes=[("Network settings", "*.json"), ("All files", "*.*")])
        if not path or not load_settings_file(path):
            return False
        net_loc.set("file")
        refresh_net_widgets()
        return True

    def on_location_changed():
        if net_loc.get() == "file" and file_state["cfg"] is None:
            if not browse_file():
                net_loc.set("system")
        refresh_net_widgets()

    def on_include_changed():
        own["include_system"] = bool(inc_sys.get())
        own["include_global"] = bool(inc_glob.get())
        refresh_net_widgets()

    def make_dialog(title, width, height):
        dlg = tk.Toplevel(win)
        dlg.title(title)
        dlg.configure(bg=style.BG)
        dlg.transient(win)
        style.center_window(dlg, width, height)
        dlg.resizable(False, False)
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        return dlg

    def grab(dlg):
        try:
            dlg.grab_set()           # modal; skipped if the window is not shown yet
        except tk.TclError:
            pass

    def add_broadcast():
        if not view_cfg()[1]:
            return
        dlg = make_dialog("Add Broadcast", 440, 300)
        btns = tk.Frame(dlg, bg=style.BG)
        btns.pack(side="bottom", fill="x", padx=18, pady=14)

        tk.Label(dlg, text="Add Broadcast", font=style.ui_font(14, True),
                 bg=style.BG, fg=style.WHITE).pack(anchor="w", padx=18, pady=(14, 4))
        tk.Label(dlg, text="Enter a broadcast address (for example 192.168.1.255)\n"
                           "or a subnet (for example 192.168.1.0/24).",
                 justify="left", bg=style.BG, fg=style.MUTED).pack(anchor="w", padx=18)
        value = tk.StringVar()
        entry = style.make_entry(dlg, textvariable=value)
        entry.pack(fill="x", padx=18, pady=(12, 0), ipady=4)
        error = tk.Label(dlg, text="", bg=style.BG, fg=style.RED, justify="left",
                         wraplength=400)
        error.pack(anchor="w", padx=18, pady=(6, 0))
        entry.bind("<Key>", lambda e: error.config(text=""), add="+")

        def ok(_event=None):
            try:
                address = netconfig.parse_broadcast(value.get())
            except ValueError as exc:
                error.config(text=str(exc))
                return
            if address in own["broadcasts"]:
                error.config(text="That broadcast is already in the list.")
                return
            own["broadcasts"].append(address)
            dlg.destroy()
            refresh_net_widgets()
            bc_list.selection_set("end")
            bc_list.see("end")

        entry.bind("<Return>", ok)
        style.make_button(btns, "OK", ok, kind="primary", width=10).pack(side="right", padx=(6, 0))
        style.make_button(btns, "Cancel", dlg.destroy, kind="secondary",
                          width=10).pack(side="right")
        grab(dlg)
        entry.focus_set()

    def delete_broadcast():
        if not view_cfg()[1]:
            return
        selection = bc_list.curselection()
        if not selection:
            messagebox.showinfo("Delete", "Select a broadcast in the list first.",
                                parent=win)
            return
        del own["broadcasts"][selection[0]]
        refresh_net_widgets()

    def export_network():
        cfg, _editable = view_cfg()
        path = filedialog.asksaveasfilename(
            parent=win, title="Export network settings",
            defaultextension=".json", initialfile="network_settings.json",
            filetypes=[("Network settings", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            netconfig.export_settings_file(path, cfg)
        except OSError as exc:
            messagebox.showerror("Export Failed",
                                 f"Could not write the file:\n{exc.strerror or exc}",
                                 parent=win)
            return
        messagebox.showinfo("Exported", f"Network settings were saved to:\n{path}",
                            parent=win)

    def edit_tag():
        if not view_cfg()[1]:
            return
        dlg = make_dialog("Network Tagging", 470, 340)
        btns = tk.Frame(dlg, bg=style.BG)
        btns.pack(side="bottom", fill="x", padx=18, pady=14)

        tk.Label(dlg, text="Network Tagging", font=style.ui_font(14, True),
                 bg=style.BG, fg=style.WHITE).pack(anchor="w", padx=18, pady=(14, 4))
        tk.Label(dlg, text="Tagging splits one network into separate groups. Only "
                           "people who use the same tag can see each other, so "
                           "everyone in the group must enter exactly the same tag.",
                 justify="left", wraplength=430, bg=style.BG,
                 fg=style.MUTED).pack(anchor="w", padx=18)

        enabled = tk.BooleanVar(value=own["tag_enabled"])
        text = tk.StringVar(value=own["tag"])
        entry = style.make_entry(dlg, textvariable=text,
                                 disabledbackground=style.INPUT_BG,
                                 disabledforeground=style.MUTED)

        def sync():
            entry.config(state="normal" if enabled.get() else "disabled")

        tk.Checkbutton(dlg, text="Enable network tagging", variable=enabled,
                       command=sync, bg=style.BG, fg=style.WHITE,
                       selectcolor=style.INPUT_BG, activebackground=style.BG,
                       activeforeground=style.WHITE, highlightthickness=0
                       ).pack(anchor="w", padx=18, pady=(12, 4))
        tk.Label(dlg, text="Tag:", bg=style.BG, fg=style.WHITE).pack(anchor="w", padx=18)
        entry.pack(fill="x", padx=18, pady=(2, 0), ipady=4)
        error = tk.Label(dlg, text="", bg=style.BG, fg=style.RED, justify="left",
                         wraplength=430)
        error.pack(anchor="w", padx=18, pady=(6, 0))
        entry.bind("<Key>", lambda e: error.config(text=""), add="+")
        sync()

        def ok(_event=None):
            try:
                tag = netconfig.clean_tag(text.get())
            except ValueError as exc:
                error.config(text=str(exc))
                return
            if enabled.get() and not tag:
                error.config(text="Enter a tag, or untick 'Enable network tagging'.")
                return
            own["tag"] = tag
            own["tag_enabled"] = bool(enabled.get() and tag)
            dlg.destroy()
            refresh_net_widgets()

        entry.bind("<Return>", ok)
        style.make_button(btns, "OK", ok, kind="primary", width=10).pack(side="right", padx=(6, 0))
        style.make_button(btns, "Cancel", dlg.destroy, kind="secondary",
                          width=10).pack(side="right")
        grab(dlg)
        if enabled.get():
            entry.focus_set()

    refresh_net_widgets()

    # ------------------------------------------------------------------
    # File Transfer tab: file acceptance + incoming files location
    # ------------------------------------------------------------------
    tab = tabs["File Transfer"]
    heading(tab, "File Transfer")

    local_name = _local_user_name(user_email, discovery)

    def pick(value, allowed, fallback):
        return value if value in allowed else fallback

    ft_accept = tk.StringVar(value=pick(data["file_accept"], ("auto", "ask"), "auto"))
    ft_loc = tk.StringVar(value=pick(data["incoming_location"], ("system", "custom"), "system"))
    ft_mode = tk.StringVar(value=pick(data["save_mode"], ("per_transfer", "one_folder"), "per_transfer"))
    ft_exists = tk.StringVar(value=filestore.EXISTS_CHOICES.get(
        data["if_file_exists"], filestore.EXISTS_CHOICES["rename"]))
    folder = tk.StringVar(value=data["download_folder"])     # the saved custom folder
    shown = tk.StringVar()                                   # text in the folder box
    ft_busy = [False]

    # ----- File Acceptance -----
    section(tab, "File Acceptance")
    radio(tab, "Start downloading automatically", ft_accept, "auto")
    radio(tab, "Ask for permission first", ft_accept, "ask")
    check(tab, "Show previews of incoming images", "show_image_previews")

    # ----- Incoming Files Location (with the "i" help icon) -----
    loc_head = tk.Frame(tab, bg=style.BG)
    loc_head.pack(fill="x", padx=25, pady=(5, 2))
    tk.Label(loc_head, text="Incoming Files Location", bg=style.BG, fg=style.WHITE,
             font=style.ui_font(11, True)).pack(side="left")
    info_icon = tk.Label(loc_head, text="ⓘ", bg=style.BG, fg=style.ACCENT,
                         cursor="hand2", font=style.ui_font(14))
    info_icon.pack(side="right")
    tk.Frame(tab, bg=style.BORDER, height=1).pack(fill="x", padx=25, pady=4)

    radio(tab, "System-defined location", ft_loc, "system",
          command=lambda: ft_refresh())
    radio(tab, "Custom location:", ft_loc, "custom",
          command=lambda: ft_refresh())

    path_row = tk.Frame(tab, bg=style.BG)
    path_row.pack(fill="x", padx=50, pady=(2, 0))
    ft_entry = style.make_entry(
        path_row, textvariable=shown, state="disabled",
        disabledbackground=style.INPUT_BG, disabledforeground=style.MUTED)
    ft_entry.pack(side="left", fill="x", expand=True, ipady=3)
    ft_browse = style.make_button(path_row, "...", lambda: ft_browse_folder(),
                                  kind="secondary", width=3, pady=3,
                                  font=style.SMALL_FONT)
    ft_browse.pack(side="left", padx=(6, 25))
    cb_user = check(tab, f'Create "\\{local_name}" subfolder',
                    "custom_user_subfolder", padx=50, command=lambda: ft_refresh())

    radio(tab, "Create subfolder for each file transfer", ft_mode, "per_transfer",
          command=lambda: ft_refresh())
    radio(tab, "Save all incoming files to one folder", ft_mode, "one_folder",
          command=lambda: ft_refresh())
    cb_sender = check(tab, "Use individual subfolder for each sender",
                      "sender_subfolders", padx=50, command=lambda: ft_refresh())

    exists_row = tk.Frame(tab, bg=style.BG)
    exists_row.pack(anchor="w", padx=50, pady=(2, 0))
    tk.Label(exists_row, text="If file already exists:", bg=style.BG,
             fg=style.WHITE).pack(side="left")
    exists_combo = ttk.Combobox(exists_row, textvariable=ft_exists,
                                values=list(filestore.EXISTS_CHOICES.values()),
                                state="disabled", width=24)
    exists_combo.pack(side="left", padx=8)
    exists_combo.bind("<<ComboboxSelected>>", lambda e: ft_refresh())

    example = tk.Label(tab, text="", bg=style.BG, fg=style.MUTED, justify="left",
                       anchor="w", wraplength=740, font=style.SMALL_FONT)
    example.pack(fill="x", padx=28, pady=(8, 0))

    # ----- File Transfer tab behaviour -----
    def exists_key():
        for key, label in filestore.EXISTS_CHOICES.items():
            if label == ft_exists.get():
                return key
        return "rename"

    def ft_cfg():
        """The File Transfer settings as they are on screen right now."""
        return {
            "file_accept": ft_accept.get(),
            "show_image_previews": int(vars_["show_image_previews"].get()),
            "incoming_location": ft_loc.get(),
            "download_folder": folder.get().strip(),
            "custom_user_subfolder": int(vars_["custom_user_subfolder"].get()),
            "save_mode": ft_mode.get(),
            "sender_subfolders": int(vars_["sender_subfolders"].get()),
            "if_file_exists": exists_key(),
        }

    def example_path():
        return filestore.resolve(ft_cfg(), local_name, "Sara", "report.pdf",
                                 create=False, check_exists=False)

    def update_example():
        example.config(text="Example: the file report.pdf received from Sara "
                            f"is saved as\n{example_path()}")

    def on_shown_changed(*_):
        if ft_loc.get() == "custom" and not ft_busy[0]:
            folder.set(shown.get())          # typed by hand
            update_example()

    shown.trace_add("write", on_shown_changed)

    def ft_refresh():
        custom = ft_loc.get() == "custom"
        one = ft_mode.get() == "one_folder"

        ft_busy[0] = True
        if custom:
            if not folder.get().strip():
                folder.set(filestore.default_folder())
            shown.set(folder.get())
        else:
            shown.set(filestore.default_folder())
        ft_busy[0] = False

        ft_entry.config(state="normal" if custom else "disabled")
        ft_browse.config(state="normal" if custom else "disabled")
        cb_user.config(state="normal" if custom else "disabled")
        cb_sender.config(state="normal" if one else "disabled")
        exists_combo.config(state="readonly" if one else "disabled")
        update_example()

    def ft_browse_folder():
        start = filestore.expand(folder.get())
        if not os.path.isdir(start):
            start = os.path.dirname(start)
        if not os.path.isdir(start):
            start = os.path.expanduser("~")

        chosen = filedialog.askdirectory(
            parent=win, title="Choose where incoming files are saved",
            initialdir=start)
        if not chosen:
            return
        chosen = os.path.normpath(chosen)
        ft_busy[0] = True
        folder.set(chosen)
        shown.set(chosen)
        ft_busy[0] = False
        update_example()

    def show_location_help():
        messagebox.showinfo(
            "Incoming Files Location",
            "Choose where the files you receive are saved.\n\n"
            "System-defined location: Documents\\" + filestore.APP_FOLDER_NAME + "\n"
            "Custom location: a folder you choose (you can add a subfolder "
            "named after you).\n\n"
            "Then choose a new subfolder for each file transfer, or one folder "
            "for everything (optionally one subfolder per sender, and what to "
            "do when a file already exists).\n\n"
            "With your current choices, report.pdf received from Sara is saved as:\n"
            f"{example_path()}",
            parent=win)

    info_icon.bind("<Button-1>", lambda e: show_location_help())
    ft_refresh()

    tab = tabs["Hot Keys"]; heading(tab, "Keyboard Shortcuts")
    tk.Label(tab, text="Open Settings: Ctrl + ,\nSend Message: Enter\nClose Window: Alt + F4",
             justify="left", bg=style.BG, fg=style.WHITE).pack(anchor="w", padx=25)

    def save():
        p = port.get().strip()
        if not p.isdigit() or not 1 <= int(p) <= 65535:
            messagebox.showerror("Invalid Port", "Port must be between 1 and 65535.", parent=win)
            return
        minutes = minutes_entry.get().strip()
        if not minutes.isdigit() or not 1 <= int(minutes) <= 1440:
            messagebox.showerror("Invalid Time",
                "Enter the number of minutes as a whole number between 1 and 1440.",
                parent=win)
            return
        secs = repeat_entry.get().strip()
        if not secs.isdigit() or not 1 <= int(secs) <= 3600:
            messagebox.showerror("Invalid Time",
                "Repeat sound interval must be a whole number of seconds "
                "between 1 and 3600.", parent=win)
            return
        file_mode = net_loc.get() == "file"
        if file_mode and file_state["cfg"] is None:
            messagebox.showerror("Network Settings",
                "Choose a valid network settings file, or select the "
                "system-defined location.", parent=win)
            return
        if not file_mode and not (own["broadcasts"] or own["include_system"]
                                  or own["include_global"]):
            messagebox.showerror("No Broadcasts",
                "Add at least one broadcast, or tick one of the two 'Include' "
                "options. Without a broadcast the app cannot find other users.",
                parent=win)
            return
        if ft_loc.get() == "custom":
            custom = filestore.expand(folder.get())
            if not custom or not os.path.isabs(custom):
                messagebox.showerror("Custom Location",
                    "Enter the full path of a folder for incoming files, "
                    "for example C:\\Users\\You\\Documents\\Received, or use the "
                    "... button to choose one.", parent=win)
                return
            try:
                os.makedirs(custom, exist_ok=True)
                if not os.access(custom, os.W_OK):
                    raise PermissionError("The folder is read-only.")
            except OSError as exc:
                messagebox.showerror("Custom Location",
                    f"This folder cannot be used for incoming files:\n"
                    f"{custom}\n\n{exc.strerror or exc}", parent=win)
                return
        new = {k: int(v.get()) for k, v in vars_.items()}
        new["inactive_minutes"] = int(minutes)
        new.update(theme=theme.get(), language=language.get(),
                   listening_port=p, download_folder=folder.get().strip(),
                   file_accept=ft_accept.get(),
                   incoming_location=ft_loc.get(),
                   save_mode=ft_mode.get(),
                   if_file_exists=exists_key(),
                   message_mode=message_mode.get(),
                   incoming_behavior=incoming.get(),
                   font_size=font_size.get(),
                   quick_messages=json.dumps(quick_list),
                   sound_when=sound_when.get(),
                   sound_tune=tune_var.get(),
                   repeat_seconds=int(secs))
        try:
            save_settings(user_email, new)
        except Exception as exc:
            messagebox.showerror("Save Error", str(exc), parent=win)
            return
        try:
            netconfig.save_config({"mode": "file" if file_mode else "system",
                                   "file": file_state["path"], **own})
        except OSError as exc:
            messagebox.showerror("Save Error",
                f"Could not save the network settings:\n{exc.strerror or exc}",
                parent=win)
            return
        if on_save:
            on_save(new)

        # Apply the chosen theme live ("Auto" follows the operating system)
        style.apply_theme(main_window, theme.get())
        style.save_preference(theme.get())

        messagebox.showinfo("Saved", "Your settings have been saved.", parent=win)
        win.destroy()

    style.make_button(footer, "OK", save, kind="primary", width=12).pack(side="right", padx=5)
    style.make_button(footer, "Cancel", win.destroy, kind="secondary", width=12).pack(side="right", padx=5)
    return win