import os
import sqlite3
import hashlib
import secrets
import tkinter as tk

from tkinter import messagebox
from PIL import Image, ImageTk

import style

DB_NAME = style.data_path("lan_connect_project.db")

LOGO_PATH = style.resource_path("pmd_logo.png")
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


def create_database():
    conn = sqlite3.connect(DB_NAME)

    try:
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS register (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                firstname TEXT NOT NULL,
                lastname TEXT NOT NULL,
                department TEXT NOT NULL,
                jobtitle TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL
            )
        """)

        conn.commit()
    finally:
        conn.close()


def hash_password(password):
    salt = secrets.token_bytes(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, 200000
    )

    return salt.hex() + ":" + password_hash.hex()


def open_register():
    try:
        create_database()
    except sqlite3.Error as e:
        messagebox.showerror("Database Error", f"Could not initialize database:\n{e}")
        return

    win = tk.Toplevel()
    win.title("LAN Connect - Register")
    style.center_window(win)
    win.minsize(760, 640)
    win.configure(bg=style.BG)

    password_visible = {"value": False}
    placeholder_state = {}

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
    card.place(relx=0.5, rely=0.5, anchor="center", width=380)

    tk.Label(
        card,
        text="Create Account",
        font=("Segoe UI", 22, "bold"),
        bg=style.CARD,
        fg=style.WHITE,
    ).pack(anchor="w")

    tk.Label(
        card,
        text="Fill in your details to get started",
        font=("Segoe UI", 10),
        bg=style.CARD,
        fg=style.MUTED,
    ).pack(anchor="w", pady=(2, 18))

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
        entry.reset_placeholder = show_placeholder
        show_placeholder()

    def get_text(entry):
        if placeholder_state.get(entry):
            return ""
        return entry.get()

    def make_field(parent, label_text, placeholder, secret=False):
        tk.Label(
            parent,
            text=label_text,
            font=("Segoe UI", 9, "bold"),
            bg=style.CARD,
            fg=style.WHITE,
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

        wrap = tk.Frame(
            parent,
            bg=style.INPUT_BG,
            highlightbackground=style.BORDER,
            highlightcolor=style.ACCENT,
            highlightthickness=1,
        )
        wrap.pack(fill="x", pady=(0, 12))

        entry = tk.Entry(
            wrap,
            font=("Segoe UI", 11),
            bg=style.INPUT_BG,
            fg=style.BLACK,
            insertbackground=style.BLACK,
            relief="flat",
            bd=0,
            show="•" if secret else "",
        )
        entry.pack(side="left", fill="x", expand=True, padx=(10, 4), ipady=7)

        add_placeholder(entry, placeholder, secret=secret)
        return entry, wrap

    def make_row():
        row = tk.Frame(card, bg=style.CARD)
        row.pack(fill="x")

        left = tk.Frame(row, bg=style.CARD)
        left.pack(side="left", fill="x", expand=True, padx=(0, 6))

        right = tk.Frame(row, bg=style.CARD)
        right.pack(side="left", fill="x", expand=True, padx=(6, 0))

        return left, right

    name_left, name_right = make_row()
    first_name, _ = make_field(name_left, "First Name", "First name")
    last_name, _ = make_field(name_right, "Last Name", "Last name")

    job_left, job_right = make_row()
    department, _ = make_field(job_left, "Department", "Department")
    job_title, _ = make_field(job_right, "Job Title", "Job title")

    email, _ = make_field(card, "Email", "Enter your email")
    password, password_wrap = make_field(
        card, "Password", "At least 8 characters", secret=True
    )

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

        if not placeholder_state.get(password):
            password.config(show="" if password_visible["value"] else "•")

    eye.bind("<Button-1>", toggle_password)

    error_label = tk.Label(
        card,
        text="",
        font=("Segoe UI", 9),
        bg=style.CARD,
        fg="#ef4444",
        anchor="w",
        wraplength=380,
        justify="left",
    )
    error_label.pack(fill="x", pady=(0, 6))

    def show_error(message):
        error_label.config(text=message)

    def register_user(event=None):
        first = get_text(first_name).strip()
        last = get_text(last_name).strip()
        dept = get_text(department).strip()
        job = get_text(job_title).strip()
        mail = get_text(email).strip()
        user_pass = get_text(password)

        if not all([first, last, dept, job, mail, user_pass]):
            show_error("Please fill in all fields.")
            return

        if (
            mail.count("@") != 1
            or mail.startswith("@")
            or "." not in mail.split("@")[1]
            or mail.endswith(".")
        ):
            show_error("Please enter a valid email address.")
            return

        if len(user_pass) < 8:
            show_error("Password must be at least 8 characters long.")
            return

        conn = None
        success = False

        try:
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()

            c.execute(
                """
                INSERT INTO register
                (firstname, lastname, department, jobtitle, email, password)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (first, last, dept, job, mail.lower(), hash_password(user_pass)),
            )

            conn.commit()
            success = True

        except sqlite3.IntegrityError:
            show_error("An account with this email already exists.")

        except sqlite3.Error as e:
            messagebox.showerror(
                "Database Error", f"Could not save your account:\n{e}", parent=win
            )

        finally:
            if conn is not None:
                conn.close()

        if success:
            messagebox.showinfo(
                "Registration Successful",
                "Your account has been created successfully!",
                parent=win,
            )
            win.destroy()

    style.make_button(card, "Register", register_user, kind="primary").pack(
        fill="x", pady=(4, 0)
    )

    footer = tk.Frame(card, bg=style.CARD)
    footer.pack(pady=(18, 0))

    tk.Label(
        footer,
        text="Already have an account?",
        font=("Segoe UI", 10),
        bg=style.CARD,
        fg=style.MUTED,
    ).pack(side="left")

    login_link = tk.Label(
        footer,
        text=" Login",
        font=("Segoe UI", 10, "bold"),
        bg=style.CARD,
        fg=style.ACCENT,
        cursor="hand2",
    )
    login_link.pack(side="left")
    login_link.bind("<Button-1>", lambda e: win.destroy())
    login_link.bind("<Enter>", lambda e: login_link.config(font=("Segoe UI", 10, "bold underline")))
    login_link.bind("<Leave>", lambda e: login_link.config(font=("Segoe UI", 10, "bold")))

    fields = [first_name, last_name, department, job_title, email, password]

    for index, entry in enumerate(fields):
        entry.bind("<Key>", lambda e: show_error(""), add="+")

        if index < len(fields) - 1:
            next_entry = fields[index + 1]
            entry.bind("<Return>", lambda e, nxt=next_entry: nxt.focus_set())
        else:
            entry.bind("<Return>", register_user)

    win.focus_set()