import json
import sqlite3
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from contextlib import contextmanager
import style

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
        tk.Label(tab, text=title, font=(style.FONT, 16, "bold"), bg=style.BG,
                 fg=style.WHITE).pack(anchor="w", padx=22, pady=(10, 6))

    def section(tab, title):
        tk.Label(tab, text=title, bg=style.BG, fg=style.WHITE,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=25, pady=(5, 2))
        tk.Frame(tab, bg=style.BORDER, height=1).pack(fill="x", padx=25, pady=4)

    vars_ = {}
    def check(tab, label, key, padx=28, pady=2):
        vars_[key] = tk.BooleanVar(value=bool(data[key]))
        cb = tk.Checkbutton(tab, text=label, variable=vars_[key], bg=style.BG,
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
             font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=25, pady=(5, 2))
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
             font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=25, pady=(5, 2))
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

        tk.Label(dlg, text="Quick Messages", font=(style.FONT, 14, "bold"),
                 bg=style.BG, fg=style.WHITE).pack(anchor="w", padx=15, pady=(12, 4))
        tk.Label(dlg, text="Ready-made replies you can send with one click.",
                 bg=style.BG, fg=style.WHITE).pack(anchor="w", padx=15)

        lb = tk.Listbox(dlg, height=10, bg=style.INPUT_BG, fg=style.WHITE,
                        highlightthickness=1, highlightbackground=style.BORDER,
                        selectbackground="#2f6fed", selectforeground="white",
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

    link = tk.Label(tab, text="Quick Messages Settings...", bg=style.BG, fg="#4da3ff",
                    cursor="hand2", font=("Segoe UI", 9, "underline"))
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

    # Sound and logging
    for tab_name, key, label in [
        ("Sound Events", "sound_enabled", "Enable sound events"),
        ("Logging", "logging_enabled", "Enable application logging")
    ]:
        heading(tabs[tab_name], tab_name + " Settings")
        check(tabs[tab_name], label, key)

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
        new = {k: int(v.get()) for k, v in vars_.items()}
        new["inactive_minutes"] = int(minutes)
        new.update(theme=theme.get(), language=language.get(),
                   listening_port=p, download_folder=folder.get().strip(),
                   message_mode=message_mode.get(),
                   incoming_behavior=incoming.get(),
                   font_size=font_size.get(),
                   quick_messages=json.dumps(quick_list))
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