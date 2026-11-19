import os
import re
import subprocess
import sys
from datetime import datetime

APP_FOLDER_NAME = "Nexo Lan Messenger"

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")

# value stored in the settings -> text shown in the drop-down list
EXISTS_CHOICES = {
    "rename": "Rename incoming file",
    "overwrite": "Overwrite existing file",
    "skip": "Skip incoming file",
}

_RESERVED = {"CON", "PRN", "AUX", "NUL"}
_RESERVED.update(f"COM{i}" for i in range(1, 10))
_RESERVED.update(f"LPT{i}" for i in range(1, 10))
_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


# ------------------------------------------------------------------- names
def safe_name(text, fallback="file", max_length=100):
    """Turns any text into one safe file / folder name.

    Only the last part of a path is kept, so names like  ..\\..\\evil.exe
    can never leave the target folder.
    """
    name = re.split(r"[\\/]", str(text or ""))[-1]
    name = _BAD_CHARS.sub("_", name).strip().rstrip(". ")

    if not name:
        return fallback

    if len(name) > max_length:
        stem, ext = os.path.splitext(name)
        ext = ext[:20]
        name = stem[:max(1, max_length - len(ext))] + ext

    if os.path.splitext(name)[0].upper() in _RESERVED:
        name = "_" + name

    return name


def unique_path(path):
    """report.pdf -> report (1).pdf -> report (2).pdf ... (first free name)."""
    if not os.path.exists(path):
        return path

    stem, ext = os.path.splitext(path)
    number = 1
    while os.path.exists(f"{stem} ({number}){ext}"):
        number += 1
    return f"{stem} ({number}){ext}"


def is_image(filename):
    return str(filename).lower().endswith(IMAGE_EXTENSIONS)


# ----------------------------------------------------------------- folders
def default_folder():
    """The system-defined location:  <home>\\Documents\\<app name>"""
    return os.path.join(os.path.expanduser("~"), "Documents", APP_FOLDER_NAME)


def expand(path):
    """Expands %userprofile% / ~ in a folder typed by the user."""
    return os.path.expandvars(os.path.expanduser(str(path or "").strip()))


def base_folder(cfg, local_user=""):
    """The main incoming-files folder (before transfer / sender subfolders)."""
    if cfg.get("incoming_location") != "custom":
        return default_folder()

    custom = expand(cfg.get("download_folder"))
    base = custom if custom and os.path.isabs(custom) else default_folder()

    if cfg.get("custom_user_subfolder") and local_user:
        base = os.path.join(base, safe_name(local_user, "user"))
    return base


def resolve(cfg, local_user, sender, filename, stamp=None,
            create=True, check_exists=True):
    """Full path an incoming file must be saved to.

    cfg           the settings (a dict from settings.load_settings)
    local_user    this user's name (used by "Create \\<name> subfolder")
    sender        who sent the file
    stamp         time of the transfer; give the SAME value for every file of
                  one transfer so they land in the same subfolder
    create        create the folders (False = only calculate, e.g. preview)
    check_exists  apply the "if file already exists" rule (False for preview)

    Returns None if the file has to be skipped.
    """
    base = base_folder(cfg, local_user)
    sender_name = safe_name(sender, "unknown")
    name = safe_name(filename)

    if cfg.get("save_mode") == "one_folder":
        folder = base
        if cfg.get("sender_subfolders", 1):
            folder = os.path.join(folder, sender_name)
        policy = cfg.get("if_file_exists", "rename")
    else:
        stamp = stamp or datetime.now()
        folder = os.path.join(base, f"{sender_name} {stamp:%Y-%m-%d %H.%M.%S}")
        policy = "rename"          # a new folder: only a repeated name can clash

    if create:
        os.makedirs(folder, exist_ok=True)

    path = os.path.join(folder, name)

    if check_exists and os.path.exists(path):
        if policy == "skip":
            return None
        if policy == "rename":
            path = unique_path(path)
        # "overwrite": keep the same path

    return path


# ------------------------------------------------------------ small helpers
def wants_permission(cfg):
    return cfg.get("file_accept") == "ask"


def wants_preview(cfg):
    return bool(cfg.get("show_image_previews", 1))


def open_folder(path):
    """Opens a folder in the file manager (creates it first). True if opened."""
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        return False
    return open_file(path)


def open_file(path):
    """Opens a file (or folder) with the system's default program."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)                      # noqa: S606 - local folder
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except (OSError, ValueError):
        return False