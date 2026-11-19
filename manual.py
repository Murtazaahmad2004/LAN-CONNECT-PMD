import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from tkinter import messagebox
import shutil
import tempfile

import style

# Apni manual file ka naam (project folder mein, logo.png ke saath)
MANUAL_FILE = "USER_MANUAL.pdf"

def _browser_paths():
    """Windows par common browsers ke exe paths."""
    roots = [
        os.environ.get("PROGRAMFILES", r"C:\Program Files"),
        os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
        os.environ.get("LOCALAPPDATA", ""),
    ]
    parts = [
        r"Microsoft\Edge\Application\msedge.exe",
        r"Google\Chrome\Application\chrome.exe",
        r"Mozilla Firefox\firefox.exe",
        r"BraveSoftware\Brave-Browser\Application\brave.exe",
    ]
    for root in roots:
        if not root:
            continue
        for part in parts:
            full = os.path.join(root, part)
            if os.path.exists(full):
                yield full

def _open_path(path):
    """True = koi na koi tareeqe se khul gayi."""
    uri = Path(path).resolve().as_uri()

    # 1) Seedha browser exe se (default program galat ho tab bhi chalta hai)
    if sys.platform.startswith("win"):
        for exe in _browser_paths():
            try:
                subprocess.Popen([exe, uri])
                print("[HELP] Opened with:", exe)
                return True
            except OSError as e:
                print("[HELP] Browser start error:", exe, e)

        # 2) Windows ka default program
        try:
            os.startfile(path)
            print("[HELP] Opened with os.startfile")
            return True
        except OSError as e:
            print("[HELP] startfile error:", e)

    # 3) Python ka webbrowser module
    try:
        if webbrowser.open(uri):
            print("[HELP] Opened with webbrowser")
            return True
    except Exception as e:
        print("[HELP] webbrowser error:", e)

    return False

def open_manual(parent=None):
    """User manual ko browser mein kholta hai."""
    path = os.path.abspath(style.resource_path(MANUAL_FILE))
    print("[HELP] Manual path:", path)

    if not os.path.exists(path):
        messagebox.showerror(
            "Help",
            f"User manual file not found:\n{path}",
            parent=parent,
        )
        return

    size = os.path.getsize(path)
    print("[HELP] File size:", size, "bytes")

    # PDF ki jaanch: asli PDF "%PDF" se shuru hoti hai
    if path.lower().endswith(".pdf"):
        try:
            with open(path, "rb") as f:
                header = f.read(5)
        except OSError as e:
            header = b""
            print("[HELP] Read error:", e)

        if size == 0 or not header.startswith(b"%PDF"):
            messagebox.showerror(
                "Help",
                "This file pdf is wrong.\n\n"
                f"Size: {size} bytes\nFile: {path}\n\n"
                "Please save this again as a pdf.",
                parent=parent,
            )
            return

        # Simple naam ke saath temp folder se kholein (path ke masle se bachne ke liye)
        try:
            temp_path = os.path.join(tempfile.gettempdir(), "Nexo User Manual")
            shutil.copyfile(path, temp_path)
            path = temp_path
        except OSError as e:
            print("[HELP] Temp copy error:", e)

    if not _open_path(path):
        messagebox.showerror(
            "Help",
            f"Manual is not open in browser.\n\nFile place on this path:\n{path}",
            parent=parent,
        )