import os
from tkinter import messagebox
import tkinter as tk
import sqlite3
import hashlib
import hmac

from PIL import Image, ImageTk

import style
import register
import home

DB_NAME = "lan_connect_project.db"

LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pmd_logo.png")
PLACEHOLDER_COLOR = "#8A94A6"
PANEL_WIDTH = 440

def load_logo(max_height=220):
    try:
        img = Image.open(LOGO_PATH).convert("RGBA")
        ratio = max_height / img.height
        img = img.resize((int(img.width * ratio), max_height), Image.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception:
        return None

def show_login():
    win = tk.Tk()
    win.title("LAN Connect - Login")
    style.center_window(win)
    win.minsize(760, 520)
    win.configure(bg=style.BG)

    password_visible = {"value": False}

    left_side = tk.Frame(win, bg=style.BG)
    left_side.place(x=0, y=0, relwidth=1, relheight=1, width=-PANEL_WIDTH)

    brand = tk.Frame(left_side, bg=style.BG)
    brand.place(relx=0.5, rely=0.5, anchor="center")

    logo_image = load_logo()
    if logo_image:
        logo_holder = tk.Frame(brand, bg="#FFFFFF", padx=20, pady=20)
        logo_holder.pack()

        logo_label = tk.Label(logo_holder, image=logo_image, bg="#FFFFFF")
        logo_label.image = logo_image
        logo_label.pack()
    else:
        tk.Label(
            brand,
            text="PMD",
            font=("Segoe UI", 56, "bold"),
            bg=style.BG,
            fg=style.ACCENT,
        ).pack()

    tk.Label(
        brand,
        text="LAN Connect",
        font=("Segoe UI", 28, "bold"),
        bg=style.BG,
        fg=style.WHITE,
    ).pack(pady=(16, 0))

    tk.Label(
        brand,
        text="Chat and share files on your local network",
        font=("Segoe UI", 11),
        bg=style.BG,
        fg=style.MUTED,
    ).pack(pady=(6, 0))

    right_panel = tk.Frame(
        win,
        bg=style.CARD,
        highlightbackground=style.BORDER,
        highlightthickness=1,
    )
    right_panel.place(relx=1.0, rely=0, anchor="ne", relheight=1.0, width=PANEL_WIDTH)

    card = tk.Frame(right_panel, bg=style.CARD)
    card.place(relx=0.5, rely=0.5, anchor="center", width=340)

    tk.Label(
        card,
        text="Welcome Back",
        font=("Segoe UI", 22, "bold"),
        bg=style.CARD,
        fg=style.WHITE,
    ).pack(anchor="w")

    tk.Label(
        card,
        text="Sign in to continue",
        font=("Segoe UI", 10),
        bg=style.CARD,
        fg=style.MUTED,
    ).pack(anchor="w", pady=(2, 24))

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
            entry.config(fg=PLACEHOLDER_COLOR, show="")
            placeholder_state[entry] = True

        def on_focus_in(event):
            if placeholder_state[entry]:
                entry.delete(0, tk.END)
                entry.config(fg=style.BLACK, show=current_mask())
                placeholder_state[entry] = False

        def on_focus_out(event):
            if not entry.get():
                show_placeholder()

        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)
        show_placeholder()

    def get_text(entry):
        if placeholder_state.get(entry):
            return ""
        return entry.get()

    def make_field(label_text, show=None):
        tk.Label(
            card,
            text=label_text,
            font=("Segoe UI", 9, "bold"),
            bg=style.CARD,
            fg=style.WHITE,
            anchor="w",
        ).pack(fill="x", pady=(0, 5))

        wrap = tk.Frame(
            card,
            bg=style.INPUT_BG,
            highlightbackground=style.BORDER,
            highlightcolor=style.ACCENT,
            highlightthickness=1,
        )
        wrap.pack(fill="x", pady=(0, 14))

        entry = tk.Entry(
            wrap,
            font=("Segoe UI", 11),
            bg=style.INPUT_BG,
            fg=style.BLACK,
            insertbackground=style.BLACK,
            relief="flat",
            bd=0,
            show=show or "",
        )
        entry.pack(side="left", fill="x", expand=True, padx=(10, 4), ipady=8)
        return entry, wrap

    entry_email, _ = make_field("Email")
    entry_password, password_wrap = make_field("Password", show="•")

    add_placeholder(entry_email, "Email")
    add_placeholder(entry_password, "Password", secret=True)

    eye = tk.Label(
        password_wrap,
        text="👁",
        font=("Segoe UI Emoji", 11),
        bg=style.INPUT_BG,
        fg=style.MUTED,
        cursor="hand2",
    )
    eye.pack(side="right", padx=(0, 10))

    def toggle_password(event=None):
        password_visible["value"] = not password_visible["value"]
        eye.config(fg=style.ACCENT if password_visible["value"] else style.MUTED)

        if not placeholder_state.get(entry_password):
            entry_password.config(show="" if password_visible["value"] else "•")

    eye.bind("<Button-1>", toggle_password)

    error_label = tk.Label(
        card,
        text="",
        font=("Segoe UI", 9),
        bg=style.CARD,
        fg="#ef4444",
        anchor="w",
        wraplength=340,
        justify="left",
    )
    error_label.pack(fill="x", pady=(0, 6))

    def show_error(message):
        error_label.config(text=message)

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

    style.make_button(card, "Login", check, kind="primary").pack(
        fill="x", pady=(4, 0)
    )

    divider = tk.Frame(card, bg=style.CARD)
    divider.pack(fill="x", pady=18)
    tk.Frame(divider, bg=style.BORDER, height=1).pack(
        side="left", fill="x", expand=True, pady=6
    )
    tk.Label(
        divider,
        text="  or  ",
        font=("Segoe UI", 9),
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
        font=("Segoe UI", 10),
        bg=style.CARD,
        fg=style.MUTED,
    ).pack(side="left")

    register_link = tk.Label(
        footer,
        text=" Register",
        font=("Segoe UI", 10, "bold"),
        bg=style.CARD,
        fg=style.ACCENT,
        cursor="hand2",
    )
    register_link.pack(side="left")
    register_link.bind("<Button-1>", lambda e: register.open_register())
    register_link.bind("<Enter>", lambda e: register_link.config(font=("Segoe UI", 10, "bold underline")))
    register_link.bind("<Leave>", lambda e: register_link.config(font=("Segoe UI", 10, "bold")))

    entry_email.bind("<Return>", lambda e: entry_password.focus_set())
    entry_password.bind("<Return>", check)
    entry_email.bind("<Key>", lambda e: show_error(""))
    entry_password.bind("<Key>", lambda e: show_error(""))

    win.focus_set()
    win.mainloop()

if __name__ == "__main__":
    show_login()