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
            row = cur.fetchone()
            cols = [d[0] for d in cur.description]
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

    # Network
    tab = tabs["Network"]; heading(tab, "Network Settings")
    tk.Label(tab, text="Listening Port", bg=style.BG, fg=style.WHITE).pack(anchor="w", padx=25)
    port = style.make_entry(tab); port.insert(0, data["listening_port"])
    port.pack(anchor="w", padx=25, pady=7, ipady=3)
    check(tab, "Enable peer discovery", "discover_peers")

    # File transfer
    tab = tabs["File Transfer"]; heading(tab, "File Transfer Settings")
    folder = tk.StringVar(value=data["download_folder"])
    tk.Label(tab, text="Download Folder", bg=style.BG, fg=style.WHITE).pack(anchor="w", padx=25)
    f = tk.Frame(tab, bg=style.BG); f.pack(fill="x", padx=25, pady=8)
    style.make_entry(f, textvariable=folder).pack(side="left", fill="x", expand=True, ipady=3)
    style.make_button(f, "Browse", lambda: folder.set(
        filedialog.askdirectory(parent=win) or folder.get()),
        kind="secondary", font=style.SMALL_FONT).pack(side="left", padx=5)

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
        new = {k: int(v.get()) for k, v in vars_.items()}
        new["inactive_minutes"] = int(minutes)
        new.update(theme=theme.get(), language=language.get(),
                   listening_port=p, download_folder=folder.get().strip(),
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