import math

try:
    from PIL import Image, ImageDraw
except Exception:              # Pillow missing: the caller uses a text symbol
    Image = ImageDraw = None

try:
    from PIL import ImageTk
except Exception:
    ImageTk = None

SCALE = 4
WHITE = (255, 255, 255, 255)

COLORS = {
    "settings": (100, 116, 139, 255),
    "received": (14, 165, 233, 255),
    "history":  (139, 92, 246, 255),
    "shared":   (16, 185, 129, 255),
    "help":     (245, 158, 11, 255),
    "about":    (59, 130, 246, 255),
    "logout":   (239, 68, 68, 255),
    "theme":    (217, 119, 6, 255),
    # Shared Files window
    "upload":   (16, 185, 129, 255),
    "download": (14, 165, 233, 255),
    "refresh":  (139, 92, 246, 255),
    "delete":   (239, 68, 68, 255),
    "search":   (100, 116, 139, 255),
    "close":    (100, 116, 139, 255),
}

_cache = {}


# --------------------------------------------------------------------------
# Drawing (all coordinates are on a 20 x 20 grid)
# --------------------------------------------------------------------------
def _gear(d, u, c):
    cx = cy = 10 * u
    for k in range(8):
        a = math.radians(k * 45)
        ca, sa = math.cos(a), math.sin(a)
        pts = []
        for r, w in ((4.5, 1.7), (8.6, 1.35), (8.6, -1.35), (4.5, -1.7)):
            # point at distance r along the tooth axis, w to the side
            x = cx + (r * ca - w * sa) * u
            y = cy + (r * sa + w * ca) * u
            pts.append((x, y))
        d.polygon(pts, fill=c)
    d.ellipse((cx - 6.3 * u, cy - 6.3 * u, cx + 6.3 * u, cy + 6.3 * u), fill=c)
    d.ellipse((cx - 2.6 * u, cy - 2.6 * u, cx + 2.6 * u, cy + 2.6 * u),
              fill=(0, 0, 0, 0))


def _received(d, u, c):
    d.line([(3 * u, 11.5 * u), (3 * u, 16 * u), (17 * u, 16 * u),
            (17 * u, 11.5 * u)], fill=c, width=int(2.2 * u), joint="curve")
    d.rectangle((8.9 * u, 2.5 * u, 11.1 * u, 10 * u), fill=c)
    d.polygon([(5.3 * u, 8.2 * u), (14.7 * u, 8.2 * u), (10 * u, 13.4 * u)], fill=c)


def _history(d, u, c):
    d.ellipse((2.2 * u, 2.2 * u, 17.8 * u, 17.8 * u), outline=c, width=int(2.2 * u))
    d.line([(10 * u, 5.8 * u), (10 * u, 10 * u), (13.4 * u, 12 * u)],
           fill=c, width=int(2 * u), joint="curve")
    r = 1 * u
    for x, y in ((10, 5.8), (13.4, 12)):
        d.ellipse((x * u - r, y * u - r, x * u + r, y * u + r), fill=c)


def _shared(d, u, c):
    d.rounded_rectangle((1.5 * u, 3.5 * u, 8.5 * u, 8 * u), radius=1.3 * u, fill=c)
    d.rounded_rectangle((1.5 * u, 6 * u, 18.5 * u, 16.5 * u), radius=1.6 * u, fill=c)
    d.ellipse((8.5 * u, 8.2 * u, 11.5 * u, 11.2 * u), fill=WHITE)
    d.pieslice((6.8 * u, 11.8 * u, 13.2 * u, 18 * u), 180, 360, fill=WHITE)


def _help(d, u, c):
    d.ellipse((1.2 * u, 1.2 * u, 18.8 * u, 18.8 * u), fill=c)
    d.arc((6.6 * u, 4.6 * u, 13.4 * u, 11.4 * u), 180, 60, fill=WHITE,
          width=int(2.1 * u))
    d.line([(10 * u, 10.8 * u), (10 * u, 12.6 * u)], fill=WHITE, width=int(2.1 * u))
    d.ellipse((8.9 * u, 13.9 * u, 11.1 * u, 16.1 * u), fill=WHITE)


def _about(d, u, c):
    d.ellipse((1.2 * u, 1.2 * u, 18.8 * u, 18.8 * u), fill=c)
    d.ellipse((8.8 * u, 4.4 * u, 11.2 * u, 6.8 * u), fill=WHITE)
    d.rounded_rectangle((8.9 * u, 8.3 * u, 11.1 * u, 15.4 * u),
                        radius=0.9 * u, fill=WHITE)


def _logout(d, u, c):
    d.line([(9 * u, 3 * u), (3 * u, 3 * u), (3 * u, 17 * u), (9 * u, 17 * u)],
           fill=c, width=int(2.2 * u), joint="curve")
    d.rectangle((7.5 * u, 8.9 * u, 14 * u, 11.1 * u), fill=c)
    d.polygon([(12.6 * u, 5.4 * u), (18 * u, 10 * u), (12.6 * u, 14.6 * u)], fill=c)


def _theme(d, u, c):
    box = (2 * u, 2 * u, 18 * u, 18 * u)
    d.ellipse(box, outline=c, width=int(2.2 * u))
    d.pieslice(box, 90, 270, fill=c)


def _upload(d, u, c):
    d.line([(3 * u, 11.5 * u), (3 * u, 16 * u), (17 * u, 16 * u),
            (17 * u, 11.5 * u)], fill=c, width=int(2.2 * u), joint="curve")
    d.rectangle((8.9 * u, 7 * u, 11.1 * u, 14 * u), fill=c)
    d.polygon([(5.3 * u, 8.2 * u), (14.7 * u, 8.2 * u), (10 * u, 2.8 * u)], fill=c)


def _arrow_head(d, u, c, angle, r=6.5, size=3.0):
    """Arrow head at `angle` (degrees, clockwise) on the circle used by refresh."""
    a = math.radians(angle)
    px, py = 10 + r * math.cos(a), 10 + r * math.sin(a)
    tx, ty = -math.sin(a), math.cos(a)          # direction of travel
    nx, ny = math.cos(a), math.sin(a)           # points away from the centre
    d.polygon([
        ((px + tx * size) * u, (py + ty * size) * u),
        ((px + nx * size * 0.95) * u, (py + ny * size * 0.95) * u),
        ((px - nx * size * 0.95) * u, (py - ny * size * 0.95) * u),
    ], fill=c)


def _refresh(d, u, c):
    box = (3.5 * u, 3.5 * u, 16.5 * u, 16.5 * u)
    d.arc(box, 205, 335, fill=c, width=int(2.2 * u))
    d.arc(box, 25, 155, fill=c, width=int(2.2 * u))
    _arrow_head(d, u, c, 338)
    _arrow_head(d, u, c, 158)


def _delete(d, u, c):
    d.rounded_rectangle((3 * u, 4.3 * u, 17 * u, 6.4 * u), radius=1 * u, fill=c)
    d.rounded_rectangle((7.4 * u, 2 * u, 12.6 * u, 4.8 * u), radius=1 * u, fill=c)
    d.polygon([(4.7 * u, 7.6 * u), (15.3 * u, 7.6 * u),
               (14.3 * u, 17.6 * u), (5.7 * u, 17.6 * u)], fill=c)
    for x in (8, 10, 12):
        d.line([(x * u, 9.6 * u), (x * u, 15.4 * u)], fill=WHITE, width=int(1.4 * u))


def _search(d, u, c):
    d.ellipse((2.4 * u, 2.4 * u, 12.8 * u, 12.8 * u), outline=c, width=int(2.4 * u))
    d.line([(11.2 * u, 11.2 * u), (16.8 * u, 16.8 * u)], fill=c, width=int(2.6 * u))
    r = 1.3 * u
    d.ellipse((16.8 * u - r, 16.8 * u - r, 16.8 * u + r, 16.8 * u + r), fill=c)


def _close(d, u, c):
    w = int(2.4 * u)
    d.line([(5 * u, 5 * u), (15 * u, 15 * u)], fill=c, width=w)
    d.line([(15 * u, 5 * u), (5 * u, 15 * u)], fill=c, width=w)
    r = 1.2 * u
    for x, y in ((5, 5), (15, 15), (15, 5), (5, 15)):
        d.ellipse((x * u - r, y * u - r, x * u + r, y * u + r), fill=c)


_DRAW = {
    "upload": _upload, "download": _received, "refresh": _refresh,
    "delete": _delete, "search": _search, "close": _close,
    "settings": _gear, "received": _received, "history": _history,
    "shared": _shared, "help": _help, "about": _about,
    "logout": _logout, "theme": _theme,
}


def _rgba(color):
    """'#RRGGBB' or an (r, g, b[, a]) tuple -> (r, g, b, a)."""
    if isinstance(color, str):
        color = color.lstrip("#")
        return (int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16), 255)
    return tuple(color) + (255,) * (4 - len(color))


def render(name, size=20, color=None):
    """The icon as a Pillow RGBA image (size x size pixels), or None.
    color: optional '#RRGGBB' to use instead of the icon's own colour."""
    if Image is None or name not in _DRAW:
        return None
    big = size * SCALE
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    _DRAW[name](ImageDraw.Draw(image), big / 20.0,
                _rgba(color) if color else COLORS[name])
    return image.resize((size, size), Image.LANCZOS)


def get(name, size=20, color=None):
    """The icon as a tk PhotoImage (cached), or None if it cannot be made.
    Needs a Tk window to exist already."""
    key = (name, size, color)
    if key not in _cache:
        try:
            image = render(name, size, color)
            _cache[key] = ImageTk.PhotoImage(image) if image is not None else None
        except Exception as error:
            print("[ICONS] Could not make icon", name, ":", error)
            _cache[key] = None
    return _cache[key]