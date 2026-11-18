import hashlib
import hmac
import sqlite3
import tkinter as tk
from tkinter import messagebox

# PIL library load karne se JPEG/PNG images cleanly display hoti hain
from PIL import Image, ImageTk

import manual
import brand
import home
import register
import style

DB_NAME = style.data_path("lan_connect_project.db")

PANEL_WIDTH = 440
CARD_WIDTH = 340


def show_login():
    win = tk.Tk()
    win.title("Nexo Lan Messenger - Login")

    # ------------------------------------------------------------------
    # WINDOW TITLE BAR ICON SETTING (Red marked area)
    # ------------------------------------------------------------------
    try:
        # resource_path = file ke andar se (build ke baad .exe mein bhi chalta hai).
        # data_path .exe ke bahar wale folder mein dhoondta hai, isi liye
        # build ke baad icon nahi aata tha.
        icon_path = style.resource_path("logo.png")
        logo_img = Image.open(icon_path).convert("RGBA")
        icons = [
            ImageTk.PhotoImage(logo_img.resize((size, size), Image.LANCZOS))
            for size in (64, 32)
        ]
        win.iconphoto(True, *icons)      # True = aage khulne wali windows par bhi
        win._title_icons = icons         # reference rakhna zaroori hai
    except Exception as e:
        print("Title bar icon load nahi ho saka:", e)

    style.center_window(win)
    win.minsize(760, 560)
    win.configure(bg=style.BG)

    password_visible = {"value": False}

    # ------------------------------------------------------------------
    # Left side: brand panel (gradient, logo, features)
    # ------------------------------------------------------------------
    brand_frame = brand.build_brand_panel(win, PANEL_WIDTH)
    
    # ------------------------------------------------------------------
    # Right side: sign-in card
    # ------------------------------------------------------------------
    right_panel = tk.Frame(
        win,
        bg=style.CARD,
        highlightbackground=style.BORDER,
        highlightthickness=1,
    )
    right_panel.place(relx=1.0, rely=0, anchor="ne", relheight=1.0, width=PANEL_WIDTH)

    card = tk.Frame(right_panel, bg=style.CARD)
    card.place(relx=0.5, rely=0.5, anchor="center", width=CARD_WIDTH)

    tk.Frame(card, bg=style.ACCENT, height=4, width=48).pack(
        anchor="w", pady=(0, 18)
    )

    tk.Label(
        card,
        text="Welcome back",
        font=style.ui_font(24, True),
        bg=style.CARD,
        fg=style.TEXT,
    ).pack(anchor="w")

    tk.Label(
        card,
        text="Sign in to your account to continue",
        font=style.ui_font(10),
        bg=style.CARD,
        fg=style.MUTED,
    ).pack(anchor="w", pady=(4, 26))

    placeholder_state = {}

    def add_placeholder(entry, placeholder, secret=False):
        placeholder_state[entry] = True

        def current_mask():
            if secret and not password_visible["value"]:
                return "•"
            return ""

        def show_placeholder():
            entry.delete(0, tk.END)
            entry.insert(0, placeholder)
            entry.config(fg=style.PLACEHOLDER, show="")
            placeholder_state[entry] = True

        def on_focus_in(event):
            if placeholder_state[entry]:
                entry.delete(0, tk.END)
                entry.config(fg=style.TEXT_INPUT, show=current_mask())
                placeholder_state[entry] = False

        def on_focus_out(event):
            if not entry.get():
                show_placeholder()

        entry.bind("<FocusIn>", on_focus_in, add="+")
        entry.bind("<FocusOut>", on_focus_out, add="+")
        show_placeholder()

    def get_text(entry):
        if placeholder_state.get(entry):
            return ""
        return entry.get()

    def make_field(label_text, icon, show=None):
        tk.Label(
            card,
            text=label_text,
            font=style.ui_font(9, True),
            bg=style.CARD,
            fg=style.LABEL,
            anchor="w",
        ).pack(fill="x", pady=(0, 6))

        wrap = tk.Frame(
            card,
            bg=style.INPUT_BG,
            highlightbackground=style.BORDER,
            highlightcolor=style.ACCENT,
            highlightthickness=1,
        )
        wrap.pack(fill="x", pady=(0, 16))

        tk.Label(
            wrap,
            text=icon,
            font=("Segoe UI Emoji", 11),
            bg=style.INPUT_BG,
            fg=style.MUTED,
        ).pack(side="left", padx=(12, 0))

        entry = tk.Entry(
            wrap,
            font=style.INPUT_FONT,
            bg=style.INPUT_BG,
            fg=style.TEXT_INPUT,
            insertbackground=style.TEXT_INPUT,
            relief="flat",
            bd=0,
            show=show or "",
        )
        entry.pack(side="left", fill="x", expand=True, padx=(8, 4), ipady=10)
        style.focus_border(entry, wrap)
        return entry, wrap

    entry_email, _ = make_field("Email address", "✉")
    entry_password, password_wrap = make_field("Password", "🔒", show="•")

    add_placeholder(entry_email, "name@company.com")
    add_placeholder(entry_password, "Enter your password", secret=True)

    eye = tk.Label(
        password_wrap,
        text="👁",
        font=("Segoe UI Emoji", 11),
        bg=style.INPUT_BG,
        fg=style.MUTED,
        cursor="hand2",
    )
    eye.pack(side="right", padx=(0, 12))

    def toggle_password(event=None):
        password_visible["value"] = not password_visible["value"]
        eye.config(fg=style.ACCENT if password_visible["value"] else style.MUTED)

        if not placeholder_state.get(entry_password):
            entry_password.config(show="" if password_visible["value"] else "•")

    eye.bind("<Button-1>", toggle_password)

    error_label = tk.Label(
        card,
        text="",
        font=style.ui_font(9),
        bg=style.CARD,
        fg=style.RED,
        anchor="w",
        wraplength=CARD_WIDTH,
        justify="left",
    )
    error_label.pack(fill="x", pady=(0, 6))

    def show_error(message):
        error_label.config(text=f"⚠  {message}" if message else "")

    def verify_password(entered_password, stored_password):
        try:
            salt_hex, hash_hex = stored_password.split(":", 1)
            salt = bytes.fromhex(salt_hex)
            expected_hash = bytes.fromhex(hash_hex)

            actual_hash = hashlib.pbkdf2_hmac(
                "sha256",
                entered_password.encode("utf-8"),
                salt,
                200000,
            )

            return hmac.compare_digest(actual_hash, expected_hash)

        except (ValueError, TypeError):
            return False

    def check(event=None):
        email = get_text(entry_email).strip().lower()
        password = get_text(entry_password)

        if not email or not password:
            show_error("Please enter your email and password.")
            return

        authenticated = False
        conn = None

        try:
            conn = sqlite3.connect(DB_NAME, timeout=30)
            c = conn.cursor()
            c.execute("SELECT password FROM register WHERE email = ?", (email,))
            user = c.fetchone()
            c.close()

            authenticated = user is not None and verify_password(password, user[0])

        except sqlite3.Error as e:
            messagebox.showerror(
                "Database Error",
                f"Could not access the database:\n{e}",
                parent=win,
            )
            return

        finally:
            if conn is not None:
                conn.close()

        if authenticated:
            win.destroy()
            home.home_page(email)
        else:
            show_error("Incorrect email or password.")

    style.make_button(
        card, "Sign In", check, kind="primary", pady=11
    ).pack(fill="x", pady=(4, 0))

    divider = tk.Frame(card, bg=style.CARD)
    divider.pack(fill="x", pady=20)
    tk.Frame(divider, bg=style.BORDER, height=1).pack(
        side="left", fill="x", expand=True, pady=6
    )
    tk.Label(
        divider,
        text="  or  ",
        font=style.ui_font(9),
        bg=style.CARD,
        fg=style.MUTED,
    ).pack(side="left")
    tk.Frame(divider, bg=style.BORDER, height=1).pack(
        side="left", fill="x", expand=True, pady=6
    )

    footer = tk.Frame(card, bg=style.CARD)
    footer.pack()

    tk.Label(
        footer,
        text="Don't have an account?",
        font=style.ui_font(10),
        bg=style.CARD,
        fg=style.MUTED,
    ).pack(side="left")

    register_link = tk.Label(
        footer,
        text=" Create one",
        font=style.ui_font(10, True),
        bg=style.CARD,
        fg=style.ACCENT,
        cursor="hand2",
    )
    register_link.pack(side="left")
    register_link.bind("<Button-1>", lambda e: register.open_register())
    register_link.bind(
        "<Enter>",
        lambda e: register_link.config(fg=style.ACCENT_HOVER),
    )
    register_link.bind(
        "<Leave>",
        lambda e: register_link.config(fg=style.ACCENT),
    )

    help_row = tk.Frame(right_panel, bg=style.CARD)
    help_row.place(relx=0.5, rely=1.0, anchor="s", y=-20)

    help_link = tk.Label(
        help_row,
        text="Need help?",
        font=style.ui_font(9, True),
        bg=style.CARD,
        fg=style.ACCENT,
        cursor="hand2",
    )
    help_link.pack(side="left")
    help_link.bind("<Button-1>", lambda e: manual.open_manual(win))
    help_link.bind("<Enter>", lambda e: help_link.config(fg=style.ACCENT_HOVER))
    help_link.bind("<Leave>", lambda e: help_link.config(fg=style.ACCENT))

    entry_email.bind("<Return>", lambda e: entry_password.focus_set(), add="+")
    entry_password.bind("<Return>", check, add="+")
    entry_email.bind("<Key>", lambda e: show_error(""), add="+")
    entry_password.bind("<Key>", lambda e: show_error(""), add="+")

    win.focus_set()
    win.mainloop()


if __name__ == "__main__":
    show_login()