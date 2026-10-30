import json
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

# ------------------------------------------------------------------ fonts
FONT = "Segoe UI"

TITLE_FONT = (FONT, 22, "bold")
SUBTITLE_FONT = (FONT, 10)
LABEL_FONT = (FONT, 10, "bold")
INPUT_FONT = (FONT, 11)
BUTTON_FONT = (FONT, 11, "bold")
SMALL_FONT = (FONT, 9)

# ------------------------------------------------------------ window sizes
WINDOW_SIZE = "950x650"
SETTING_WINDOW_SIZE = "450x550"

CARD_PADDING_X = 38
CARD_PADDING_Y = 28

# ----------------------------------------------------------------- palettes
THEMES = {
    "Light": {
        "BG": "#F1F5F9",            # window background
        "CARD": "#FFFFFF",          # panels, cards, menu bars
        "INPUT_BG": "#F8FAFC",      # entry / text boxes
        "TEXT": "#0F172A",          # main text
        "TEXT_INPUT": "#1E293B",    # text typed inside inputs
        "MUTED": "#64748B",         # secondary text
        "PLACEHOLDER": "#94A3B8",   # placeholder text
        "LABEL": "#334155",
        "BORDER": "#CBD5E1",
        "HOVER": "#E2E8F0",         # hover / secondary button
        "ACCENT": "#0284C7",
        "ACCENT_HOVER": "#0369A1",
        "ON_ACCENT": "#F0F9FF",     # text on accent buttons
        "RED": "#DC2626",
        "BLUE": "#2563EB",
        "GREEN": "#16A34A",
    },
    "Dark": {
        "BG": "#0B1120",
        "CARD": "#111B2E",
        "INPUT_BG": "#1E293B",
        "TEXT": "#F8FAFC",
        "TEXT_INPUT": "#E2E8F0",
        "MUTED": "#94A3B8",
        "PLACEHOLDER": "#64748B",
        "LABEL": "#CBD5E1",
        "BORDER": "#334155",
        "HOVER": "#1A2740",
        "ACCENT": "#38BDF8",
        "ACCENT_HOVER": "#7DD3FC",
        "ON_ACCENT": "#04121F",
        "RED": "#F87171",
        "BLUE": "#60A5FA",
        "GREEN": "#4ADE80",
    },
}

# Old names used by the existing code -> new tokens.
_ALIASES = {
    "WHITE": "TEXT",          # main text colour
    "BLACK": "TEXT_INPUT",    # text typed inside inputs
}

# Status colours (same in every theme on purpose)
STATUS_ONLINE = "#22C55E"
STATUS_INACTIVE = "#F59E0B"
STATUS_OFFLINE = "#9CA3AF"

PREF_FILE = Path(__file__).resolve().parent / "theme_pref.json"

CURRENT_THEME = "Light"


# ------------------------------------------------------- sanity check (dev)
def _check_palettes():
    for name, palette in THEMES.items():
        values = [v.lower() for v in palette.values()]
        if len(values) != len(set(values)):
            raise ValueError(
                f"Theme '{name}' has duplicate colour values; "
                "live theme switching needs every colour to be unique."
            )


_check_palettes()


# ------------------------------------------------------------ system theme
def detect_system_theme():
    """Return 'Light' or 'Dark' following the operating system setting."""
    try:
        if sys.platform.startswith("win"):
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            try:
                value = winreg.QueryValueEx(key, "AppsUseLightTheme")[0]
            finally:
                winreg.CloseKey(key)
            return "Light" if value else "Dark"

        if sys.platform == "darwin":
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            return "Dark" if "Dark" in result.stdout else "Light"
    except Exception:
        pass
    return "Light"


def resolve_theme(theme_name):
    """'Auto' -> detected system theme; unknown names -> Light."""
    if theme_name == "Auto":
        return detect_system_theme()
    return theme_name if theme_name in THEMES else "Light"


# --------------------------------------------------------- saved preference
def load_preference():
    try:
        data = json.loads(PREF_FILE.read_text(encoding="utf-8"))
        theme = data.get("theme", "Auto")
        return theme if theme in ("Auto", "Light", "Dark") else "Auto"
    except (OSError, ValueError, AttributeError):
        return "Auto"


def save_preference(theme_name):
    try:
        PREF_FILE.write_text(
            json.dumps({"theme": theme_name}), encoding="utf-8"
        )
    except OSError:
        pass


# ------------------------------------------------------------- core switch
def set_theme(theme_name="Auto"):
    """Make `theme_name` the active palette (affects widgets created later)."""
    global CURRENT_THEME

    resolved = resolve_theme(theme_name)
    CURRENT_THEME = resolved
    palette = THEMES[resolved]

    globals().update(palette)
    for alias, token in _ALIASES.items():
        globals()[alias] = palette[token]

    return resolved


_COLOR_OPTIONS = (
    "bg",
    "fg",
    "activebackground",
    "activeforeground",
    "highlightbackground",
    "highlightcolor",
    "selectcolor",
    "insertbackground",
    "disabledforeground",
    "troughcolor",
    "readonlybackground",
    "selectbackground",
    "selectforeground",
)


def _remap_widget(widget, old_lookup, new_palette):
    for option in _COLOR_OPTIONS:
        try:
            current = str(widget.cget(option)).lower()
        except tk.TclError:
            continue

        token = old_lookup.get(current)
        if token:
            try:
                widget.configure(**{option: new_palette[token]})
            except tk.TclError:
                pass

    if widget.winfo_class() in ("Entry", "Text"):
        try:
            widget.configure(insertbackground=new_palette["TEXT_INPUT"])
        except tk.TclError:
            pass

    for child in widget.winfo_children():
        _remap_widget(child, old_lookup, new_palette)


def apply_theme(root=None, theme_name="Auto"):
    """Switch theme live for `root` and every window/widget inside it."""
    previous = CURRENT_THEME
    old_palette = THEMES[previous]
    new_name = set_theme(theme_name)

    root = root or getattr(tk, "_default_root", None)
    if root is None:
        return new_name

    setup_ttk(root)

    if new_name != previous:
        old_lookup = {v.lower(): k for k, v in old_palette.items()}
        _remap_widget(root, old_lookup, THEMES[new_name])

    return new_name


def toggle_theme(root=None):
    """Quick Light <-> Dark switch. Returns the new theme name."""
    new_name = "Dark" if CURRENT_THEME == "Light" else "Light"
    apply_theme(root, new_name)
    save_preference(new_name)
    return new_name


# ---------------------------------------------------------------- ttk theme
def setup_ttk(root=None):
    """Style ttk widgets (Notebook, Combobox, Scrollbar) for the active theme."""
    root = root or getattr(tk, "_default_root", None)
    c = THEMES[CURRENT_THEME]

    try:
        s = ttk.Style(root)
        try:
            s.theme_use("clam")  # 'clam' respects custom colours everywhere
        except tk.TclError:
            pass

        s.configure(
            ".",
            background=c["CARD"],
            foreground=c["TEXT"],
            fieldbackground=c["INPUT_BG"],
            bordercolor=c["BORDER"],
            lightcolor=c["CARD"],
            darkcolor=c["CARD"],
            troughcolor=c["BG"],
            font=(FONT, 10),
        )
        s.configure("TFrame", background=c["CARD"])
        s.configure("TLabel", background=c["CARD"], foreground=c["TEXT"])
        s.configure("TCheckbutton", background=c["CARD"], foreground=c["TEXT"])

        s.configure("TNotebook", background=c["BG"], borderwidth=0)
        s.configure(
            "TNotebook.Tab",
            background=c["CARD"],
            foreground=c["MUTED"],
            padding=(14, 8),
            borderwidth=0,
        )
        s.map(
            "TNotebook.Tab",
            background=[("selected", c["BG"]), ("active", c["HOVER"])],
            foreground=[("selected", c["ACCENT"]), ("active", c["TEXT"])],
        )

        s.configure(
            "TCombobox",
            fieldbackground=c["INPUT_BG"],
            background=c["CARD"],
            foreground=c["TEXT_INPUT"],
            arrowcolor=c["TEXT"],
            bordercolor=c["BORDER"],
            padding=4,
        )
        s.map(
            "TCombobox",
            fieldbackground=[("readonly", c["INPUT_BG"])],
            foreground=[("readonly", c["TEXT_INPUT"])],
            selectbackground=[("readonly", c["INPUT_BG"])],
            selectforeground=[("readonly", c["TEXT_INPUT"])],
        )

        s.configure(
            "TScrollbar",
            background=c["HOVER"],
            troughcolor=c["BG"],
            bordercolor=c["BORDER"],
            arrowcolor=c["TEXT"],
        )

        if root is not None:
            root.option_add("*TCombobox*Listbox.background", c["INPUT_BG"])
            root.option_add("*TCombobox*Listbox.foreground", c["TEXT_INPUT"])
            root.option_add("*TCombobox*Listbox.selectBackground", c["ACCENT"])
            root.option_add("*TCombobox*Listbox.selectForeground", c["ON_ACCENT"])
    except tk.TclError:
        pass


# ---------------------------------------------------------- widget helpers
def make_button(parent, text, command=None, kind="primary", **options):
    """Text-only button: no background, bold text.

    Text is white in the Dark theme and black in Light/Auto-light
    (the theme's TEXT colour). On hover only the text turns accent colour.
    `kind` is kept for compatibility; all buttons look the same.
    """
    c = THEMES[CURRENT_THEME]

    # Button background = parent's background, so it looks transparent.
    try:
        parent_bg = str(parent.cget("bg"))
    except (tk.TclError, AttributeError):
        parent_bg = c["CARD"]

    config = dict(
        text=text,
        command=command,
        font=BUTTON_FONT,
        bg=parent_bg,
        fg=c["TEXT"],
        activebackground=parent_bg,
        activeforeground=c["ACCENT"],
        relief="flat",
        bd=0,
        highlightthickness=0,
        cursor="hand2",
        padx=14,
        pady=6,
    )
    config.update(options)
    button = tk.Button(parent, **config)

    button.bind(
        "<Enter>",
        lambda e: button.configure(fg=THEMES[CURRENT_THEME]["ACCENT"]),
    )
    button.bind(
        "<Leave>",
        lambda e: button.configure(fg=THEMES[CURRENT_THEME]["TEXT"]),
    )
    return button


def make_entry(parent, **options):
    """Themed single-line input with a border that highlights on focus."""
    c = THEMES[CURRENT_THEME]
    config = dict(
        font=INPUT_FONT,
        bg=c["INPUT_BG"],
        fg=c["TEXT_INPUT"],
        insertbackground=c["TEXT_INPUT"],
        relief="flat",
        highlightthickness=1,
        highlightbackground=c["BORDER"],
        highlightcolor=c["ACCENT"],
    )
    config.update(options)
    return tk.Entry(parent, **config)


# Initialise with the user's last saved choice (Auto by default).
set_theme(load_preference())