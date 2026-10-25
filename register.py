import sqlite3
import hashlib
import secrets
import tkinter as tk
from tkinter import messagebox
import style
import home

DB_NAME = "lan_connect_project.db"


# Create database and table if they do not exist
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

# Hash password before saving it
def hash_password(password):
    salt = secrets.token_bytes(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, 200000
    )

    return salt.hex() + ":" + password_hash.hex()

def open_register():
    # Ensure database and table exist
    try:
        create_database()
    except sqlite3.Error as e:
        messagebox.showerror("Database Error", f"Could not initialize database:\n{e}")
        return

    win = tk.Toplevel()
    win.title("Register Screen")
    win.geometry(style.WINDOW_SIZE)
    win.configure(bg=style.BG)

    card = tk.Frame(
        win,
        bg=style.CARD,
        padx=38,
        pady=28,
        highlightbackground=style.BORDER,
        highlightthickness=1,
    )
    card.pack(pady=25)

    heading = tk.Label(
        card,
        text="Create an Account",
        font=style.TITLE_FONT,
        fg=style.WHITE,
        bg=style.CARD,
    )
    heading.pack(pady=(0, 15))

    # Create labels and input fields
    def create_input_fields(label_text, show=None):
        label = tk.Label(
            card,
            text=label_text,
            font=style.LABEL_FONT,
            fg=style.WHITE,
            bg=style.CARD,
            anchor="w",
            justify="left",
        )
        label.pack(fill="x", pady=(5, 3))

        entry = tk.Entry(
            card,
            font=style.INPUT_FONT,
            bg=style.INPUT_BG,
            fg=style.BLACK,
            relief="flat",
            show=show,
        )
        entry.pack(fill="x", ipady=6)

        return entry

    # Reusable placeholder function
    def add_placeholder(entry, placeholder, is_password=False):
        entry.insert(0, placeholder)
        entry.config(fg="gray")

        def on_focus_in(event):
            if entry.get() == placeholder:
                entry.delete(0, tk.END)
                entry.config(fg=style.BLACK)

                if is_password:
                    entry.config(show="*")

        def on_focus_out(event):
            if not entry.get().strip():
                entry.delete(0, tk.END)
                entry.insert(0, placeholder)
                entry.config(fg="gray")

                if is_password:
                    entry.config(show="")

        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)

    # Form fields
    first_name = create_input_fields("First Name")
    add_placeholder(first_name, "Enter First Name")

    last_name = create_input_fields("Last Name")
    add_placeholder(last_name, "Enter Last Name")

    department = create_input_fields("Department")
    add_placeholder(department, "Enter Department")

    job_title = create_input_fields("Job Title")
    add_placeholder(job_title, "Enter Job Title")

    email = create_input_fields("Email")
    add_placeholder(email, "Enter Email")

    password = create_input_fields("Password")
    add_placeholder(password, "Enter Password", is_password=True)

    # Register button action
    def register_user():
        first = first_name.get().strip()
        last = last_name.get().strip()
        dept = department.get().strip()
        job = job_title.get().strip()
        mail = email.get().strip()
        user_pass = password.get()

        # Check empty fields and placeholders
        values = [
            (first, "Enter First Name"),
            (last, "Enter Last Name"),
            (dept, "Enter Department"),
            (job, "Enter Job Title"),
            (mail, "Enter Email"),
            (user_pass, "Enter Password"),
        ]

        if any(not value or value == placeholder for value, placeholder in values):
            messagebox.showwarning(
                "Missing Information", "Please fill in all fields.", parent=win
            )
            return

        # Basic email validation
        if (
            mail.count("@") != 1
            or mail.startswith("@")
            or "." not in mail.split("@")[1]
            or mail.endswith(".")
        ):
            messagebox.showwarning(
                "Invalid Email", "Please enter a valid email address.", parent=win
            )
            return

        if len(user_pass) < 8:
            messagebox.showwarning(
                "Weak Password",
                "Password must be at least 8 characters long.",
                parent=win,
            )
            return

        # Save user in database
        conn = None

        try:
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()

            hashed_password = hash_password(user_pass)

            c.execute(
                """
                INSERT INTO register
                (firstname, lastname, department, jobtitle, email, password)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (first, last, dept, job, mail.lower(), hashed_password),
            )

            conn.commit()

            messagebox.showinfo(
                "Registration Successful",
                "Your account has been created successfully!",
                parent=win,
            )

            # Clear form after successful registration
            for entry, placeholder in [
                (first_name, "Enter First Name"),
                (last_name, "Enter Last Name"),
                (department, "Enter Department"),
                (job_title, "Enter Job Title"),
                (email, "Enter Email"),
                (password, "Enter Password"),
            ]:
                entry.delete(0, tk.END)
                entry.config(fg="gray", show="")
                entry.insert(0, placeholder)

        except sqlite3.IntegrityError:
            messagebox.showwarning(
                "Email Already Registered",
                "An account with this email already exists.",
                parent=win,
            )

        except sqlite3.Error as e:
            messagebox.showerror(
                "Database Error", f"Could not save your account:\n{e}", parent=win
            )

        finally:
            if conn is not None:
                conn.close()

    register_button = tk.Button(
        card,
        text="Register",
        font=style.BUTTON_FONT,
        bg=style.ACCENT,
        fg=style.BG,
        activebackground=style.ACCENT_HOVER,
        relief="flat",
        cursor="hand2",
        command=register_user,
    )
    register_button.pack(fill="x", pady=(18, 8), ipady=5)
