import json
import os
import subprocess
import sys
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import ttk


# ------------------------------------------------------------------ fonts
def _installed_families():
    """Names of the fonts installed on this computer (lower case -> real name)."""
    try:
        probe = tk.Tk()
        probe.withdraw()
        try:
            return {name.lower(): name for name in tkfont.families(probe)}
        finally:
            probe.destroy()
    except Exception:
        return {}


_FAMILIES = _installed_families()


def _pick(candidates, fallback):
    """First installed font from `candidates`, otherwise `fallback`."""
    for name in candidates:
        if name.lower() in _FAMILIES:
            return _FAMILIES[name.lower()]
    return fallback


# Best clean UI font available on the computer
# (Windows: Segoe UI, macOS: SF / Helvetica Neue, Linux: Noto / Ubuntu / DejaVu)
FONT = _pick(
    ["Segoe UI", "SF Pro Text", "Helvetica Neue", "Noto Sans",
     "Ubuntu", "DejaVu Sans", "Arial"],
    "Segoe UI",
)

# "Segoe UI Semibold" is a refined heading weight (nicer than plain bold)
_SEMIBOLD = (
    _pick(["Segoe UI Semibold"], None)
    if FONT.lower().startswith("segoe") else None
)


def ui_font(size, bold=False):
    """Font tuple for the whole app: ui_font(11) or ui_font(15, True)."""
    if bold:
        return (_SEMIBOLD, size) if _SEMIBOLD else (FONT, size, "bold")
    return (FONT, size)


# Type scale (use these instead of writing font tuples by hand)
TITLE_FONT = ui_font(24, True)       # screen titles
HEADING_FONT = ui_font(15, True)     # section / chat headings
SUBTITLE_FONT = ui_font(11)
LABEL_FONT = ui_font(10, True)
INPUT_FONT = ui_font(11)
BUTTON_FONT = ui_font(11, True)
BODY_FONT = ui_font(10)
SMALL_FONT = ui_font(9)

# ------------------------------------------------------------ window sizes
WINDOW_SIZE = "950x650"
SETTING_WINDOW_SIZE = "450x550"

CARD_PADDING_X = 38
CARD_PADDING_Y = 28

# ----------------------------------------------------------------- palettes
# NOTE: every colour inside one theme must be unique (live theme switching
# finds colours by value). _check_palettes() below enforces this.
THEMES = {
    "Light": {
        "BG": "#F4F6FA",            # window background
        "CARD": "#FFFFFF",          # panels, cards, menu bars
        "INPUT_BG": "#F1F4F9",      # entry / text boxes
        "TEXT": "#111827",          # main text
        "TEXT_INPUT": "#1F2937",    # text typed inside inputs
        "MUTED": "#6B7280",         # secondary text
        "PLACEHOLDER": "#9CA3AF",   # placeholder text
        "LABEL": "#374151",
        "BORDER": "#D9DEE7",
        "HOVER": "#E8ECF3",         # hover / secondary button
        "ACCENT": "#2563EB",
        "ACCENT_HOVER": "#1D4ED8",
        "ON_ACCENT": "#F8FAFF",     # text on accent buttons
        "RED": "#DC2626",
        "BLUE": "#3B82F6",
        "GREEN": "#16A34A",
    },
    "Dark": {
        "BG": "#0F1420",
        "CARD": "#171E2E",
        "INPUT_BG": "#1F2840",
        "TEXT": "#F3F4F6",
        "TEXT_INPUT": "#E5E7EB",
        "MUTED": "#9CA3AF",
        "PLACEHOLDER": "#6B7280",
        "LABEL": "#D1D5DB",
        "BORDER": "#2D374D",
        "HOVER": "#222C42",
        "ACCENT": "#4F8CFF",
        "ACCENT_HOVER": "#7AA7FF",
        "ON_ACCENT": "#FFFFFF",
        "RED": "#F87171",
        "BLUE": "#60A5FA",
        "GREEN": "#4ADE80",
    },
}

EXTRA_THEMES = {
    "Ocean Blue": {
        "BG": "#EAF3FB", "CARD": "#FFFFFF", "INPUT_BG": "#F0F6FC",
        "TEXT": "#0F2A43", "TEXT_INPUT": "#1B3A57", "MUTED": "#5B7A94",
        "PLACEHOLDER": "#94AEC4", "LABEL": "#2E4E6B", "BORDER": "#C5D9EC",
        "HOVER": "#DCE9F5", "ACCENT": "#1E78C8", "ACCENT_HOVER": "#1763A8",
        "ON_ACCENT": "#F7FBFF", "RED": "#DC2626", "BLUE": "#3B82F6",
        "GREEN": "#16A34A",
    },
    "Mint Green": {
        "BG": "#E9F7EF", "CARD": "#FFFFFF", "INPUT_BG": "#F1FAF5",
        "TEXT": "#12382A", "TEXT_INPUT": "#1E4A38", "MUTED": "#5F8672",
        "PLACEHOLDER": "#9BBBA9", "LABEL": "#2F5C47", "BORDER": "#C3E3D1",
        "HOVER": "#D8EEE2", "ACCENT": "#1F9D68", "ACCENT_HOVER": "#17825A",
        "ON_ACCENT": "#F6FFFA", "RED": "#DC2626", "BLUE": "#3B82F6",
        "GREEN": "#16A34A",
    },
    "Teal Breeze": {
        "BG": "#E6F5F5", "CARD": "#FFFFFF", "INPUT_BG": "#EFF9F9",
        "TEXT": "#12363A", "TEXT_INPUT": "#1C4A4F", "MUTED": "#5A8587",
        "PLACEHOLDER": "#98BDBF", "LABEL": "#2B5B5F", "BORDER": "#BFE0E0",
        "HOVER": "#D5ECEC", "ACCENT": "#0E8C93", "ACCENT_HOVER": "#0B7479",
        "ON_ACCENT": "#F5FFFF", "RED": "#DC2626", "BLUE": "#3B82F6",
        "GREEN": "#16A34A",
    },
    "Lavender": {
        "BG": "#F1EEFA", "CARD": "#FFFFFF", "INPUT_BG": "#F7F5FD",
        "TEXT": "#261F45", "TEXT_INPUT": "#352C5E", "MUTED": "#7A72A0",
        "PLACEHOLDER": "#B0AACB", "LABEL": "#4A4075", "BORDER": "#D9D2EF",
        "HOVER": "#E6E0F6", "ACCENT": "#6C55C9", "ACCENT_HOVER": "#5841AE",
        "ON_ACCENT": "#FAF8FF", "RED": "#DC2626", "BLUE": "#3B82F6",
        "GREEN": "#16A34A",
    },
    "Slate Pro": {
        "BG": "#EEF1F5", "CARD": "#FFFFFF", "INPUT_BG": "#F5F7FA",
        "TEXT": "#1B2633", "TEXT_INPUT": "#2A3747", "MUTED": "#667385",
        "PLACEHOLDER": "#9AA5B4", "LABEL": "#3E4C5E", "BORDER": "#D2D8E0",
        "HOVER": "#E1E6ED", "ACCENT": "#334E68", "ACCENT_HOVER": "#243B52",
        "ON_ACCENT": "#F7F9FC", "RED": "#DC2626", "BLUE": "#3B82F6",
        "GREEN": "#16A34A",
    },
    "Midnight Blue": {
        "BG": "#0C1627", "CARD": "#14233A", "INPUT_BG": "#1B2E4A",
        "TEXT": "#E6EDF7", "TEXT_INPUT": "#D5E0F0", "MUTED": "#8AA0BD",
        "PLACEHOLDER": "#5F7694", "LABEL": "#B8C7DC", "BORDER": "#263B58",
        "HOVER": "#1E3250", "ACCENT": "#4AA3FF", "ACCENT_HOVER": "#75BBFF",
        "ON_ACCENT": "#06121F", "RED": "#F87171", "BLUE": "#60A5FA",
        "GREEN": "#4ADE80",
    },
    "Emerald Night": {
        "BG": "#0D1A16", "CARD": "#14261F", "INPUT_BG": "#1B3329",
        "TEXT": "#E4F3EC", "TEXT_INPUT": "#D2E8DD", "MUTED": "#86A89A",
        "PLACEHOLDER": "#5E8272", "LABEL": "#B4D1C3", "BORDER": "#284539",
        "HOVER": "#1F382D", "ACCENT": "#34D399", "ACCENT_HOVER": "#6EE7B7",
        "ON_ACCENT": "#05150E", "RED": "#F87171", "BLUE": "#60A5FA",
        "GREEN": "#4ADE80",
    },
}
THEMES.update(EXTRA_THEMES)

# Order shown in the Theme dropdowns
THEME_NAMES = ["Auto", "Light", "Dark"] + list(EXTRA_THEMES)

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
        return theme if theme == "Auto" or theme in THEMES else "Auto"
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


# ------------------------------------------------------ default font setup
def apply_default_fonts(root=None):
    """Every widget without its own font (checkboxes, radio buttons, menus,
    list boxes ...) now uses the app font instead of the plain system one."""
    for name, size in (
        ("TkDefaultFont", 10),
        ("TkTextFont", 10),
        ("TkMenuFont", 10),
        ("TkHeadingFont", 10),
        ("TkIconFont", 10),
    ):
        try:
            try:
                named = tkfont.nametofont(name, root=root)
            except TypeError:               # older Python versions
                named = tkfont.nametofont(name)
            named.configure(family=FONT, size=size)
        except tk.TclError:
            pass


# ---------------------------------------------------------------- ttk theme
def setup_ttk(root=None):
    """Style ttk widgets (Notebook, Combobox, Scrollbar) for the active theme."""
    root = root or getattr(tk, "_default_root", None)
    c = THEMES[CURRENT_THEME]

    apply_default_fonts(root)

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
            font=BODY_FONT,
        )
        s.configure("TFrame", background=c["CARD"])
        s.configure("TLabel", background=c["CARD"], foreground=c["TEXT"])
        s.configure("TCheckbutton", background=c["CARD"], foreground=c["TEXT"])

        s.configure(
            "TNotebook",
            background=c["BG"],
            borderwidth=0,
            tabmargins=(8, 6, 8, 0),
        )
        s.configure(
            "TNotebook.Tab",
            background=c["CARD"],
            foreground=c["MUTED"],
            padding=(18, 10),
            borderwidth=0,
            font=ui_font(10, True),
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
            padding=5,
        )
        s.map(
            "TCombobox",
            fieldbackground=[("readonly", c["INPUT_BG"])],
            foreground=[("readonly", c["TEXT_INPUT"])],
            selectbackground=[("readonly", c["INPUT_BG"])],
            selectforeground=[("readonly", c["TEXT_INPUT"])],
            bordercolor=[("focus", c["ACCENT"])],
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
            root.option_add("*TCombobox*Listbox.font", BODY_FONT)
    except tk.TclError:
        pass


# ---------------------------------------------------------- widget helpers
def make_button(parent, text, command=None, kind="primary", **options):
    """Themed button.

    kind="primary"   -> filled accent button (main action)
    kind="secondary" -> soft grey button (cancel / close / small actions)
    Both get a smooth hover colour.
    """
    c = THEMES[CURRENT_THEME]

    if kind == "secondary":
        base, hover = "HOVER", "BORDER"
        fg_token = "TEXT"
    else:
        base, hover = "ACCENT", "ACCENT_HOVER"
        fg_token = "ON_ACCENT"

    config = dict(
        text=text,
        command=command,
        font=BUTTON_FONT,
        bg=c[base],
        fg=c[fg_token],
        activebackground=c[hover],
        activeforeground=c[fg_token],
        relief="flat",
        bd=0,
        highlightthickness=0,
        cursor="hand2",
        padx=16,
        pady=8,
        disabledforeground=c["MUTED"],
    )
    config.update(options)
    button = tk.Button(parent, **config)

    def on_enter(_e):
        try:
            if str(button.cget("state")) == "disabled":
                return
            button.configure(bg=THEMES[CURRENT_THEME][hover])
        except tk.TclError:
            pass

    def on_leave(_e):
        try:
            button.configure(bg=THEMES[CURRENT_THEME][base])
        except tk.TclError:
            pass

    button.bind("<Enter>", on_enter)
    button.bind("<Leave>", on_leave)
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


def focus_border(entry, wrap):
    """Makes the border of `wrap` turn accent coloured while `entry` has focus."""
    entry.bind(
        "<FocusIn>",
        lambda e: wrap.configure(highlightbackground=THEMES[CURRENT_THEME]["ACCENT"]),
        add="+",
    )
    entry.bind(
        "<FocusOut>",
        lambda e: wrap.configure(highlightbackground=THEMES[CURRENT_THEME]["BORDER"]),
        add="+",
    )


def hover_text(widget, normal_token="TEXT", hover_token="ACCENT"):
    """Text colour changes to accent while the mouse is over `widget`."""
    widget.bind(
        "<Enter>",
        lambda e: widget.configure(fg=THEMES[CURRENT_THEME][hover_token]),
        add="+",
    )
    widget.bind(
        "<Leave>",
        lambda e: widget.configure(fg=THEMES[CURRENT_THEME][normal_token]),
        add="+",
    )


# Initialise with the user's last saved choice (Auto by default).
set_theme(load_preference())


def center_window(win, width=None, height=None):
    win.update_idletasks()

    if width is None or height is None:
        try:
            width, height = map(int, WINDOW_SIZE.split("+")[0].split("x"))
        except (ValueError, AttributeError):
            width, height = win.winfo_reqwidth(), win.winfo_reqheight()

    screen_w = win.winfo_screenwidth()
    screen_h = win.winfo_screenheight()

    width = min(width, screen_w)
    height = min(height, screen_h - 80)

    x = max((screen_w - width) // 2, 0)
    y = max((screen_h - height) // 2 - 20, 0)

    win.geometry(f"{width}x{height}+{x}+{y}")


def set_app_icon(win):
    """Window / taskbar icon made from logo.png (skipped if it is missing)."""
    try:
        from PIL import Image, ImageTk
        logo = Image.open(resource_path("logo.png")).convert("RGBA")
        photos = [
            ImageTk.PhotoImage(logo.resize((size, size), Image.LANCZOS))
            for size in (64, 32)
        ]
        win.iconphoto(True, *photos)        # also used by windows opened later
        win._app_icons = photos             # keep references
    except Exception:
        pass


def resource_path(filename):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, filename)


def data_path(filename):
    if getattr(sys, "frozen", False):
        folder = os.path.dirname(sys.executable)
    else:
        folder = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(folder, filename)