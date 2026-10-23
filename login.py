from ast import Lambda
from tkinter import messagebox
import tkinter as tk
import style
import register

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

def check():
    username = entryUser.get().strip()
    password = entrypassword.get().strip()
    
    if username == "Email"  or password == "Password":
        messagebox.showwarning("Missing Information", "Please Enter Email and Password")
        return
    
    if username == "admin" and password == "1234":
        messagebox.showinfo("Login Info", ("Login Successful"))
    else:
        messagebox.showerror("Login Info", "Login Failed. Please Check Username and Password")
        
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
btn.pack(pady=10)

btn = tk.Button(card, text="Register", command=register.open_register)
btn.pack(pady=5)

win.mainloop()