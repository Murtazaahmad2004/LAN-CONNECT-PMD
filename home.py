
import tkinter as tk
import style

def home_page():
    win = tk.Tk()
    win.title("Home Screen")
    win.geometry(style.WINDOW_SIZE)
    win.configure(bg=style.BG)

    # Top Header
    header = tk.Frame(win, bg=style.CARD, height=65)
    header.pack(fill="x")
    header.pack_propagate(False)

    title = tk.Label(
        header,
        text="LAN Connect",
        font=("Segoe UI", 18, "bold"),
        bg=style.CARD,
        fg=style.WHITE
    )
    title.pack(side="left", padx=20)

    # Top Navigation Menu
    menu_frame = tk.Frame(win, bg=style.CARD)
    menu_frame.pack(fill="x")

    menu_items = [
        ("⚙", "Settings"),
        ("📥", "Received Files"),
        ("💬", "Message History"),
        ("❓", "Help"),
        ("ⓘ", "About")
    ]

    for icon_text, item_title in menu_items:
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
            pady=14
        )
        btn.pack(side="left", padx=5, pady=3)

    # Main Content Area
    content_frame = tk.Frame(win, bg=style.BG)
    content_frame.pack(
        fill="both",
        expand=True,
        padx=30,
        pady=30
    )

    welcome = tk.Label(
        content_frame,
        text="Welcome to LAN Connect",
        font=("Segoe UI", 23, "bold"),
        bg=style.BG,
        fg=style.WHITE
    )
    welcome.pack(anchor="w", pady=(10, 8))

    subtitle = tk.Label(
        content_frame,
        text="Decentralized LAN Communication & File Sharing",
        font=("Segoe UI", 11),
        bg=style.BG,
        fg=style.MUTED
    )
    subtitle.pack(anchor="w")

   

    win.mainloop()