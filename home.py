import sqlite3
import tkinter as tk
from tkinter import *
from tkinter import ttk
import style
import settings
# import received_files
# import message_history
# import help_screen
# import about

def open_settings():
    open_screen("Settings")

def open_received_files():
    open_screen("Received Files")

def open_message_history():
    open_screen("Message History")

def open_help():
    open_screen("Help")

def open_about():
    open_screen("About")

DB_NAME = "lan_connect_project.db"

def create_chat_table():
    conn=sqlite3.connect(DB_NAME)
    
    try:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT NOT NULL,
                receiver TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )          
        """)
        conn.commit()
    finally:
        conn.close()
        
def open_chat(firstname, lastname, email):
    chat = tk.Toplevel()
    chat.title(f"Chat with {firstname} {lastname}")
    chat.geometry(style.WINDOW_SIZE)
    chat.configure(bg=style.BG)

    header = tk.Frame(chat, bg=style.CARD)
    header.pack(fill="x")
    tk.Label(
        header,
        text=f"💬 {firstname} {lastname}",
        font=("Segoe UI", 13, "bold"),
        bg=style.CARD,
        fg=style.WHITE,
    ).pack(side="left", padx=15, pady=15)

    conversation = tk.Text(
        chat,
        bg=style.BG,
        fg=style.WHITE,
        font=("Segoe UI", 10),
        wrap="word",
        state="disabled",
        relief="flat",
    )
    conversation.pack(fill="both", expand=True, padx=10, pady=10)

    conn = sqlite3.connect("lan_connect_project.db")
    try:
        c = conn.cursor()
        c.execute("""
                SELECT sender, message 
                FROM messages 
                WHERE receiver = ?    
                ORDER BY id ASC      
            """, (email,))
        mesg = c.fetchall()
    finally:
        conn.close()
    
    conversation.config(state="normal")
    
    for sender, message in mesg:
       conversation.insert(
            "end",
            f"{sender}: {message}\n\n"
    )
       
    conversation.config(state="disabled")
    conversation.see("end")
            
    bottom_frame = tk.Frame(chat, bg=style.CARD)
    bottom_frame.pack(fill="x", padx=10, pady=10)

    message_input = tk.Text(
        bottom_frame,
        font=("Segoe UI", 11),
        height=3,
        wrap="word",
        bg=style.INPUT_BG,
        fg=style.BLACK,
        relief="flat"
    )
    
    message_input.pack(
        side="left",
        fill="x",
        expand=True,
        padx=8,
        pady=8
    )

    def send_message():
        message = message_input.get("1.0", "end-1c").strip()

        if not message:
            return

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        
        c.execute("""
            INSERT INTO messages (sender, receiver, message)
            VALUES(?, ?, ?)
        """, ("You", email, message))
        
        conn.commit()
        conn.close()
        
        conversation.config(state="normal")
        conversation.insert("end", f"You: {message}\n\n")
        conversation.config(state="disabled")

        conversation.see("end")
        message_input.delete("1.0", "end")
        
    tk.Button(
        bottom_frame,
        text="Send",
        font=style.BUTTON_FONT,
        bg=style.ACCENT,
        fg=style.BLACK,
        command=send_message
    ).pack(side="right", padx=8, pady=8)
    
    message_input.bind(
        "<Return>",
        lambda event: send_message()
    )
    
def open_screen(screen_title):
    screen = tk.Toplevel()
    screen.title(screen_title)
    screen.geometry("700x450")
    screen.configure(bg=style.BG)

    title = tk.Label(
        screen, 
        text=screen_title, 
        font=style.TITLE_FONT, 
        bg=style.BG, 
        fg=style.WHITE
    )
    title.pack(pady=30)

    back_btn = tk.Button(
        screen,
        text="Close",
        font=style.BUTTON_FONT,
        bg=style.ACCENT,
        fg=style.BLACK,
        command=screen.destroy,
    )
    back_btn.pack(pady=10)

def home_page():
    win = tk.Tk()
    win.title("Home")
    create_chat_table()
    win.geometry(style.WINDOW_SIZE)
    win.configure(bg=style.BG)

    # Top Header
    header = tk.Frame(win, bg=style.CARD)
    header.pack(fill="x")
    header.pack_propagate(False)

    # Top Navigation Menu
    menu_frame = tk.Frame(win, bg=style.CARD)
    menu_frame.pack(fill="x")

    menu_items = [
        ("⚙", "Settings", settings.open_settings),
        ("📥", "Received Files", open_received_files),
        ("💬", "Message History", open_message_history),
        ("❓", "Help", open_help),
        ("ⓘ", "About", open_about),
    ]

    for icon_text, item_title, screen_function in menu_items:
        btn = tk.Button(
            menu_frame,
            text=f"{icon_text}  {item_title}",
            font=("Segoe UI", 10),
            bg=style.CARD,
            fg=style.WHITE,
            activebackground=style.BORDER,
            activeforeground=style.ACCENT,
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=14,
            command=screen_function,
        )
        btn.pack(side="left", padx=5, pady=3)

    # left side menu
    main_frame = tk.Frame(
        win,
        bg=style.BG,
    )
    main_frame.pack(fill="both", expand=True, pady=4)

    menu_frame = tk.Frame(main_frame, bg=style.CARD, width=220)
    menu_frame.pack(side="left", fill="y")
    menu_frame.pack_propagate(False)

    conn = sqlite3.connect("lan_connect_project.db")
    c = conn.cursor()
    c.execute("SELECT firstname, lastname, email FROM register")
    users = c.fetchall()
    conn.close()

    tk.Label(
        menu_frame,
        text="Registered Users",
        font=("Segoe UI", 10, "bold"),
        bg=style.CARD,
        fg=style.WHITE,
        anchor="w",
    ).pack(anchor="w", padx=10, pady=8)

    for firstname, lastname, email in users:
        user_label = tk.Label(
            menu_frame,
            text=f"💬  {firstname} {lastname}",
            font=("Segoe UI", 10),
            bg=style.CARD,
            fg=style.WHITE,
            anchor="w",
            cursor="hand2",
        )

        user_label.pack(fill="x", padx=10, pady=4)

        user_label.bind(
            "<Button-1>",
            lambda event, fn=firstname, ln=lastname, em=email: 
                open_chat(fn, ln, em),
        )

    win.mainloop()
