from ast import Lambda
from tkinter import messagebox
import tkinter as tk
import style
import register
import sqlite3
import hashlib
import hmac
import home

win = tk.Tk()
win.title("Login Screen")
win.configure(bg=style.BG)

# Login Card
card = tk.Frame(
    win,
    bg=style.CARD,
    padx=38,
    pady=28,
    highlightbackground=style.BORDER,
    highlightthickness=1
)

card.pack(pady=20)

heading = tk.Label(
    card,
    text="Login",
    font=style.TITLE_FONT,
    fg=style.WHITE,
    bg=style.CARD
)
heading.pack(pady=(0, 15))

entryUser = tk.Entry(
    card,
    font=style.INPUT_FONT,
    bg=style.INPUT_BG,
    fg=style.WHITE,
    relief="flat"
)

def verify_password(entered_password, stored_password):
    try:
        salt_hex, hash_hex = stored_password.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        expected_hash = bytes.fromhex(hash_hex)

        actual_hash = hashlib.pbkdf2_hmac(
            "sha256",
            entered_password.encode("utf-8"),
            salt,
            200000
        )

        return hmac.compare_digest(actual_hash, expected_hash)

    except (ValueError, TypeError):
        return False
    
def check():
    email = entryUser.get().strip().lower()
    password = entrypassword.get()

    if (
        not email
        or email == "Email"
        or not password
        or password == "Password"
    ):
        messagebox.showwarning(
            "Missing Information",
            "Please enter your email and password.",
            parent=win
        )
        return

    conn = None

    try:
        conn = sqlite3.connect("lan_connect_project.db")
        c = conn.cursor()

        c.execute(
            "SELECT password FROM register WHERE email = ?",
            (email,)
        )

        user = c.fetchone()

        if user is not None and verify_password(password, user[0]):
            messagebox.showinfo(
                "Login Successful",
                "Login successful!",
                parent=win
            )

            win.destroy()
            home.home_page()

        else:
            messagebox.showerror(
                "Login Failed",
                "Incorrect email or password.",
                parent=win
            )

    except sqlite3.Error as e:
        messagebox.showerror(
            "Database Error",
            f"Could not access the database:\n{e}",
            parent=win
        )

    finally:
        if conn is not None:
            conn.close()
        
def add_placeholder_email(entry, placeholder):
    placeholder_color = "#2D3642"
    text_color = style.BLACK
    
    def on_focus_in(event):
        if entry.get() == placeholder:
            entry.delete(0, tk.END)
            entry.config(fg=text_color)
            
    def on_focus_out(event):
        if not entry.get().strip():
            entry.delete(0, tk.END)
            entry.insert(0, placeholder)
            entry.config(fg=placeholder_color)
            
    entry.config(show="")
    entry.insert(0, placeholder)
    entry.config(fg=placeholder_color)
    
    entry.bind("<FocusIn>", on_focus_in)
    entry.bind("<FocusOut>", on_focus_out)

def add_placeholder_password(entry, placeholder):
    placeholder_color = "#2D3642"
    text_color = style.BLACK
    
    def on_focus_in(event):
        if entry.get() == placeholder:
            entry.delete(0, tk.END)
            entry.config(fg=text_color, show="*")
    
    def on_focus_out(event):
        if not entry.get().strip():
            entry.config(show="")
            entry.delete(0, tk.END)
            entry.insert(0, placeholder)
            entry.config(fg=placeholder_color)

    entry.config(show="")
    entry.insert(0, placeholder)
    entry.config(fg=placeholder_color)
    
    entry.bind("<FocusIn>", on_focus_in)
    entry.bind("<FocusOut>", on_focus_out)
    
win.geometry(style.WINDOW_SIZE)

userlabel = tk.Label(
    card,
    text="Email",
    font=style.LABEL_FONT,
    fg=style.WHITE,
    bg=style.CARD,
    anchor="w",
    justify="left"
)
userlabel.pack(fill="x", pady=(0, 5))

entryUser = tk.Entry(
    card, 
    font=style.INPUT_FONT, 
    bg=style.INPUT_BG, 
    fg=style.BLACK, 
    relief="flat"
)
entryUser.pack()
add_placeholder_email(entryUser, "Email")

userpassword = tk.Label(
    card, 
    text="Password", 
    font=style.LABEL_FONT, 
    fg=style.WHITE, 
    bg=style.CARD,
    anchor="w",
    justify="left"
)
userpassword.pack(fill="x", pady=(10, 5))

entrypassword = tk.Entry(
    card, 
    font=style.INPUT_FONT, 
    bg=style.INPUT_BG, 
    fg=style.BLACK, 
    relief="flat", 
    show = '*'
)
entrypassword.pack(pady=(3, 0))
add_placeholder_password(entrypassword, "Password")

btn = tk.Button(card, text="Login", command=check)
btn.pack(side="left", padx=4, pady=15)

btn = tk.Button(card, text="Register", command=register.open_register)
btn.pack(side="right", padx=3, pady=15)

win.mainloop()