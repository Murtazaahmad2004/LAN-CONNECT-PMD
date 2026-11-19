import os
import subprocess
import sys
import tkinter as tk
import webbrowser
from datetime import datetime

import style

try:
    from PIL import Image, ImageTk
except Exception:
    Image = ImageTk = None


def get_version():
    """Real version: VERSION file first, git tag as dev fallback."""
    # 1. VERSION file (works in dev and in the packaged exe)
    try:
        with open(style.resource_path("VERSION.txt"), encoding="utf-8") as f:
            version = f.read().strip()
            if version:
                return version
    except OSError:
        pass

    # 2. git tag (development only, not in a frozen exe)
    if not getattr(sys, "frozen", False):
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            out = subprocess.check_output(
                ["git", "describe", "--tags", "--always", "--dirty"],
                cwd=os.path.dirname(os.path.abspath(__file__)),
                stderr=subprocess.DEVNULL, text=True, timeout=2,
                creationflags=flags,
            ).strip()
            if out:
                return out.lstrip("v")
        except Exception:
            pass

    return "unknown"


# ---- edit these values --------------------------------------------------
APP_NAME = "Nexo Lan Messenger"
APP_VERSION = get_version()          # <- no longer hardcoded
START_YEAR = 2026                    # fix rahega, kabhi mat badlo

def get_copyright():
    """2026 -> '2026', 2027 onwards -> '2026 - 2027' (khud update hota hai)."""
    current = datetime.now().year
    years = str(START_YEAR) if current <= START_YEAR else f"{START_YEAR} - {current}"
    return f"Copyright © {years} NEXO"

LINKS = [
    # (label, text shown, address that opens when clicked)
    ("Technical support:", "rndpakmet@gmail.com", "mailto:rndpakmet@gmail.com"),
    (f"{APP_NAME}:", "https://weather.gov.pk/rnd", "https://weather.gov.pk/rnd"),
]
# --------------------------------------------------------------------------

_window = None


def _load_logo(max_w=280, max_h=100):
    """Logo from logo.ico (the same file the tray icon uses), or None."""
    if Image is None:
        return None
    try:
        picture = Image.open(style.resource_path("logo.ico")).convert("RGBA")
        picture.thumbnail((max_w, max_h), Image.LANCZOS)
        return ImageTk.PhotoImage(picture)
    except Exception as error:
        print("[ABOUT] Logo not loaded:", error)
        return None


def open_about(parent):
    global _window
    try:
        if _window is not None and _window.winfo_exists():
            _window.deiconify()
            _window.lift()
            _window.focus_force()
            return _window
    except tk.TclError:
        pass

    top = tk.Toplevel(parent)
    _window = top
    top.title(f"About {APP_NAME}")
    top.configure(bg=style.BG)
    top.resizable(False, False)
    top.transient(parent)
    try:
        style.set_app_icon(top)
    except Exception:
        pass

    body = tk.Frame(top, bg=style.BG)
    body.pack(fill="both", expand=True, padx=28, pady=(22, 8))

    # ---- logo
    logo = _load_logo()
    if logo is not None:
        label = tk.Label(body, image=logo, bg=style.BG)
        label.image = logo                      # keep a reference
        label.pack(anchor="w")
    else:
        tk.Label(body, text=APP_NAME, font=style.ui_font(20, True),
                 bg=style.BG, fg=style.ACCENT).pack(anchor="w")

    # ---- name, version, copyright
    tk.Label(body, text=f"{APP_NAME} v{APP_VERSION}", font=style.ui_font(11, True),
             bg=style.BG, fg=style.WHITE).pack(anchor="w", pady=(14, 0))
    tk.Label(body, text=get_copyright(), font=style.ui_font(10),
             bg=style.BG, fg=style.WHITE).pack(anchor="w", pady=(2, 12))
    # ---- contact rows:  label (right aligned)   link (blue)
    grid = tk.Frame(body, bg=style.BG)
    grid.pack(anchor="w")
    for row, (name, text, address) in enumerate(LINKS):
        tk.Label(grid, text=name, font=style.ui_font(10), bg=style.BG,
                 fg=style.WHITE, anchor="e").grid(row=row, column=0, sticky="e",
                                                  pady=2)
        link = tk.Label(grid, text=text, font=(style.FONT, 10, "underline"),
                        bg=style.BG, fg=style.ACCENT, cursor="hand2", anchor="w")
        link.grid(row=row, column=1, sticky="w", padx=(8, 0), pady=2)
        link.bind("<Button-1>", lambda e, a=address: webbrowser.open(a))

    # ---- footer with the OK button
    tk.Frame(top, bg=style.BORDER, height=1).pack(fill="x", pady=(18, 0))
    footer = tk.Frame(top, bg=style.BG)
    footer.pack(fill="x", padx=16, pady=12)
    style.make_button(footer, "OK", top.destroy, kind="secondary",
                      width=10).pack(side="right")

    top.bind("<Return>", lambda e: top.destroy())
    top.bind("<Escape>", lambda e: top.destroy())

    try:
        top.update_idletasks()
        style.center_window(top, max(420, top.winfo_reqwidth()), top.winfo_reqheight())
    except Exception:
        pass
    top.focus_force()
    return top