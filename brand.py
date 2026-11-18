"""Left-hand brand panel shared by the Login and Register screens.

Draws a blue gradient with the logo, product name and a short feature list.
The panel keeps the same blue brand colours in Light and Dark theme.
"""
import tkinter as tk
from datetime import datetime

from PIL import Image, ImageDraw, ImageTk

import style

LOGO_PATH = style.resource_path("pmd_logo.png")

GRADIENT_TOP = (29, 78, 216)       # #1D4ED8
GRADIENT_BOTTOM = (23, 37, 84)     # #172554

WHITE = "#FFFFFF"
SOFT_TEXT = "#C7D7FE"
FEATURE_TEXT = "#E0E9FF"
CHECK_COLOR = "#7DD3FC"
CIRCLE_COLOR = "#3A68EE"
FOOTER_TEXT = "#9DB6F5"

FEATURES = (
    "Instant chat with colleagues",
    "Secure file sharing",
    "Works on your local network",
)


def _hex(rgb):
    return "#%02x%02x%02x" % rgb


def _blend(t):
    return _hex(tuple(
        int(a + (b - a) * t) for a, b in zip(GRADIENT_TOP, GRADIENT_BOTTOM)
    ))


LOGO_DIAMETER = 150     # size of the round logo badge
LOGO_PADDING = 0.16     # empty space between circle edge and logo (fraction)


def _circle_logo_image(diameter=LOGO_DIAMETER):
    """Logo centred on a white circle (smooth edges). None if no logo file."""
    try:
        logo = Image.open(LOGO_PATH).convert("RGBA")
    except Exception:
        return None

    scale = 4                                   # draw big, shrink = smooth edge
    big = diameter * scale

    badge = Image.new("RGBA", (big, big), (255, 255, 255, 255))

    inner = int(big * (1 - 2 * LOGO_PADDING))
    ratio = min(inner / logo.width, inner / logo.height)
    logo = logo.resize(
        (max(1, int(logo.width * ratio)), max(1, int(logo.height * ratio))),
        Image.LANCZOS,
    )
    badge.paste(
        logo,
        ((big - logo.width) // 2, (big - logo.height) // 2),
        logo,
    )

    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, big - 1, big - 1), fill=255)
    badge.putalpha(mask)

    return badge.resize((diameter, diameter), Image.LANCZOS)


def _load_logo():
    try:
        img = _circle_logo_image()
        return ImageTk.PhotoImage(img) if img is not None else None
    except Exception:
        return None


def build_brand_panel(parent, panel_width):
    """Places the brand panel on the left of `parent` (right panel excluded)."""
    canvas = tk.Canvas(
        parent, highlightthickness=0, bd=0, bg=_hex(GRADIENT_TOP)
    )
    canvas.place(x=0, y=0, relwidth=1, relheight=1, width=-panel_width)

    logo = _load_logo()
    canvas.logo_ref = logo          # keep a reference so it is not garbage collected

    def draw(_event=None):
        w, h = canvas.winfo_width(), canvas.winfo_height()
        if w < 50 or h < 50:
            return

        canvas.delete("all")

        # --- gradient background
        step = 4
        for y in range(0, h, step):
            canvas.create_rectangle(
                0, y, w, y + step, fill=_blend(y / h), outline=""
            )

        # --- soft decorative circles
        canvas.create_oval(w - 190, -130, w + 130, 190,
                           outline=CIRCLE_COLOR, width=2)
        canvas.create_oval(w - 130, -70, w + 70, 130,
                           outline=CIRCLE_COLOR, width=1)
        canvas.create_oval(-150, h - 170, 170, h + 150,
                           outline=CIRCLE_COLOR, width=2)

        cx, cy = w // 2, h // 2
        y = max(24, cy - 190)

        # --- round logo badge (or text badge if the logo file is missing)
        d = LOGO_DIAMETER
        y = max(24, cy - 215)

        # soft ring around the circle
        canvas.create_oval(cx - d // 2 - 8, y - 8, cx + d // 2 + 8, y + d + 8,
                           outline=CIRCLE_COLOR, width=2)
        if logo:
            canvas.create_image(cx, y + d // 2, image=logo)
        else:
            canvas.create_oval(cx - d // 2, y, cx + d // 2, y + d,
                               fill=WHITE, outline="")
            canvas.create_text(cx, y + d // 2, text="PMD",
                               font=style.ui_font(28, True),
                               fill=_hex(GRADIENT_TOP))
        y += d + 8

        # --- title and tagline
        y += 26
        canvas.create_text(cx, y, text="Nexo Lan Messenger", anchor="n",
                           font=style.ui_font(28, True), fill=WHITE)
        y += 48
        canvas.create_text(
            cx, y, text="Chat and share files on your local network",
            anchor="n", width=max(w - 80, 200), justify="center",
            font=style.ui_font(11), fill=SOFT_TEXT
        )
        y += 46

        canvas.create_line(cx - 28, y, cx + 28, y, fill=CHECK_COLOR, width=3)
        y += 30

        # --- feature list
        x0 = cx - 122
        for item in FEATURES:
            canvas.create_text(x0, y, text="✓", anchor="w",
                               font=style.ui_font(12, True), fill=CHECK_COLOR)
            canvas.create_text(x0 + 26, y, text=item, anchor="w",
                               font=style.ui_font(11), fill=FEATURE_TEXT)
            y += 32

        # --- footer
        canvas.create_text(
            cx, h - 22, text=f"© {datetime.now().year}  PMD  ·  NEXO LAN Messenger",
            font=style.ui_font(9), fill=FOOTER_TEXT
        )

    canvas.bind("<Configure>", draw)
    return canvas