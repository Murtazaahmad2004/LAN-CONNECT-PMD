import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import uuid
from datetime import datetime, timezone
from tkinter import filedialog, messagebox, ttk

try:
    import style
except ImportError:
    style = None

try:
    from discovery import CHAT_PORT
except Exception:
    CHAT_PORT = 50505          # fallback only, if discovery.py cannot be imported
PORT_TRIES = 10                # same value as PORT_TRIES in home.py
CHUNK = 64 * 1024

AUTO_SYNC_MAX_MB = 500         # bigger files are not copied to every PC automatically
SYNC_INTERVAL = 10             # seconds between two sync runs

_DB = None
_ME = None                     # username of the logged-in user
_DISC = None                   # LANDiscovery object
_window = None
_sync_stop = threading.Event()
_sync_thread = None
_sync_lock = threading.Lock()
_holders = {}                  # file id -> set of ONLINE users who hold that file
_syncing = set()               # file ids that are being copied right now
_report = ""                  # result of the last sync (shown in the window)


# ==========================================================================
# Database and storage
# ==========================================================================
def init(db_path):
    """Call once from home.py, right after create_chat_table()."""
    global _DB
    _DB = db_path
    os.makedirs(files_dir(), exist_ok=True)
    # items this user holds a copy of
    _q("""CREATE TABLE IF NOT EXISTS share_items (
              id TEXT NOT NULL, holder TEXT NOT NULL, owner TEXT NOT NULL,
              name TEXT NOT NULL, size INTEGER NOT NULL, path TEXT NOT NULL,
              added TEXT NOT NULL, PRIMARY KEY (id, holder))""")
    # every file this user has heard about (held or not)
    _q("""CREATE TABLE IF NOT EXISTS share_catalog (
              id TEXT NOT NULL, viewer TEXT NOT NULL, owner TEXT NOT NULL,
              name TEXT NOT NULL, size INTEGER NOT NULL, added TEXT NOT NULL,
              PRIMARY KEY (id, viewer))""")
    # removed files (so they are not downloaded again)
    _q("""CREATE TABLE IF NOT EXISTS share_deleted (
              id TEXT NOT NULL, viewer TEXT NOT NULL,
              PRIMARY KEY (id, viewer))""")


def files_dir():
    return os.path.join(os.path.dirname(os.path.abspath(_DB)), "shared_files")


def held_dir(holder):
    safe = "".join(c if c.isalnum() or c in " ._-" else "_" for c in holder)
    return os.path.join(files_dir(), safe)


def _q(sql, args=()):
    conn = sqlite3.connect(_DB, timeout=30)
    try:
        rows = conn.execute(sql, args).fetchall()
        conn.commit()
        return rows
    finally:
        conn.close()


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def add_file(me, src, progress=None):
    """Copies a file into the shared folder and registers it. Returns its id."""
    fid = uuid.uuid4().hex
    name = os.path.basename(src)
    os.makedirs(held_dir(me), exist_ok=True)
    dest = os.path.join(held_dir(me), f"{fid}_{name}")
    total = os.path.getsize(src)
    done = 0
    with open(src, "rb") as fi, open(dest, "wb") as fo:
        while True:
            chunk = fi.read(CHUNK)
            if not chunk:
                break
            fo.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    added = now_utc()
    _q("INSERT INTO share_items (id, holder, owner, name, size, path, added) "
       "VALUES (?,?,?,?,?,?,?)", (fid, me, me, name, total, dest, added))
    _q("INSERT OR REPLACE INTO share_catalog (id, viewer, owner, name, size, added) "
       "VALUES (?,?,?,?,?,?)", (fid, me, me, name, total, added))
    return fid

def held_items(holder):
    return _q("SELECT id, owner, name, size, added, path FROM share_items "
        "WHERE holder=? ORDER BY added DESC", (holder,))

def file_owner(me, fid):
    """Real owner of a file, read from the database (None if unknown)."""
    rows = _q("SELECT owner FROM share_catalog WHERE id=? AND viewer=?", (fid, me))
    if not rows:
        rows = _q("SELECT owner FROM share_items WHERE id=? AND holder=?", (fid, me))
    return rows[0][0] if rows else None

def delete_own_file(me, fid):
    """User-initiated removal. Only the owner may do it. Returns True if removed."""
    if file_owner(me, fid) != me:
        return False
    apply_deletion(me, fid)
    return True

def apply_deletion(me, fid):
    """Deletes the local copy and remembers the removal (it spreads to others)."""
    for (path,) in _q("SELECT path FROM share_items WHERE id=? AND holder=?", (fid, me)):
        try:
            os.remove(path)
        except OSError:
            pass
    _q("DELETE FROM share_items WHERE id=? AND holder=?", (fid, me))
    _q("DELETE FROM share_catalog WHERE id=? AND viewer=?", (fid, me))
    _q("INSERT OR IGNORE INTO share_deleted (id, viewer) VALUES (?,?)", (fid, me))
    _holders.pop(fid, None)


def human_size(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{int(n)} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def to_local(ts):
    try:
        return datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc).astimezone()
    except ValueError:
        return datetime.now()


def online_peers(me, discovery):
    found = {}
    for u in discovery.get_users():
        name = u.get("username")
        if name and name != me and u.get("status") != "Offline" and u.get("ip"):
            try:
                port = int(u.get("port") or CHAT_PORT)
            except (TypeError, ValueError):
                port = CHAT_PORT
            found[name] = (u.get("ip"), port)
    return found


# ==========================================================================
# Server side (called by MessageService._handle in home.py)
# ==========================================================================
def serve(conn, msg):
    """msg type: 'share_list' or 'share_get'. msg['to'] is the user being asked."""
    holder = str(msg.get("to", ""))
    try:
        conn.settimeout(30)
        if msg.get("type") == "share_notify":
            # another user just uploaded / removed a file: sync right now
            conn.sendall(b"OK\n")
            sync_now()
            return
        if msg.get("type") == "share_list":
            files = [{"id": i, "owner": o, "name": n, "size": s, "added": a}
                     for i, o, n, s, a, _p in held_items(holder)]
            deleted = [r[0] for r in _q(
                "SELECT id FROM share_deleted WHERE viewer=?", (holder,))]
            conn.sendall(json.dumps({"files": files, "deleted": deleted}
                                    ).encode("utf-8") + b"\n")
            return

        fid = str(msg.get("id", ""))
        rows = _q("SELECT name, path FROM share_items WHERE id=? AND holder=?",
                  (fid, holder))
        if not rows or not os.path.isfile(rows[0][1]):
            conn.sendall(json.dumps(
                {"ok": False, "error": "This user no longer has the file."}
            ).encode("utf-8") + b"\n")
            return
        name, path = rows[0]
        conn.sendall(json.dumps(
            {"ok": True, "name": name, "size": os.path.getsize(path)}
        ).encode("utf-8") + b"\n")
        with open(path, "rb") as f:
            while True:
                chunk = f.read(CHUNK)
                if not chunk:
                    break
                conn.sendall(chunk)
    except (OSError, sqlite3.Error) as e:
        print("[SHARE] Serve error:", e)


# ==========================================================================
# Client side
# ==========================================================================
def _readline(sock):
    buf = b""
    while b"\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
    line, _, rest = buf.partition(b"\n")
    return line.strip(), rest


def _request(ip, port, payload, timeout=10):
    """Tries the advertised port first, then the other ports of the range (several
    copies of the app can run on one PC). Returns (socket, first_line, leftover)."""
    ports = [port] + [p for p in range(CHAT_PORT, CHAT_PORT + PORT_TRIES) if p != port]
    for p in ports:
        try:
            sock = socket.create_connection((ip, p), timeout=3)
        except ConnectionRefusedError:
            continue
        except OSError:
            return None
        try:
            sock.settimeout(timeout)
            sock.sendall(payload)
            line, rest = _readline(sock)
        except OSError:
            sock.close()
            continue
        if not line or line == b"NO":
            sock.close()
            continue
        return sock, line, rest
    return None


def fetch_list(me, holder, ip, port):
    """Returns {'files': [...], 'deleted': [...]} or None."""
    payload = json.dumps({"type": "share_list", "from": me, "to": holder}
                         ).encode("utf-8") + b"\n"
    res = _request(ip, port, payload)
    if res is None:
        return None
    sock, line, _rest = res
    try:
        data = json.loads(line.decode("utf-8"))
        return data if isinstance(data, dict) else None
    except (ValueError, UnicodeDecodeError):
        return None
    finally:
        sock.close()


def download(me, holder, ip, port, fid, dest, progress, cancel):
    """Downloads one file from `holder`. Returns (ok, message)."""
    payload = json.dumps({"type": "share_get", "id": fid, "from": me, "to": holder}
                         ).encode("utf-8") + b"\n"
    res = _request(ip, port, payload, timeout=15)
    if res is None:
        return False, f"Could not connect to {holder}."
    sock, line, rest = res
    tmp = dest + ".part"
    try:
        head = json.loads(line.decode("utf-8"))
        if not head.get("ok"):
            return False, head.get("error", "The download was refused.")
        size, got = int(head["size"]), 0
        with open(tmp, "wb") as f:
            if rest:
                part = rest[:size]
                f.write(part)
                got = len(part)
            while got < size and not cancel.is_set():
                chunk = sock.recv(min(CHUNK, size - got))
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                progress(got, size)
        if cancel.is_set():
            os.remove(tmp)
            return False, "Cancelled."
        if got != size:
            os.remove(tmp)
            return False, "The connection was lost before the file was complete."
        os.replace(tmp, dest)
        return True, "ok"
    except (OSError, ValueError) as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False, str(e)
    finally:
        sock.close()


def open_path(path):
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.run(["open", path])
        else:
            subprocess.run(["xdg-open", path])
    except Exception as e:
        print("[SHARE] Could not open file:", e)


# ==========================================================================
# Background sync service
# ==========================================================================
def notify_peers():
    """Tells every online user to sync right now (after an upload or a removal),
    so new files appear on their screens within a second or two."""
    me, disc = _ME, _DISC
    if not me or disc is None:
        return

    def work():
        for name, (ip, port) in online_peers(me, disc).items():
            payload = json.dumps({"type": "share_notify", "from": me, "to": name}
                                 ).encode("utf-8") + b"\n"
            try:
                res = _request(ip, port, payload, timeout=3)
                if res:
                    res[0].close()
            except Exception as e:
                print(f"[SHARE] Could not notify {name}: {e}")

    threading.Thread(target=work, daemon=True).start()


def sync_once():
    """Learns what the online users hold, applies removals and copies the files
    this PC does not have yet. Returns False if a sync is already running."""
    global _holders, _report
    if not _sync_lock.acquire(blocking=False):
        return False
    try:
        me, disc = _ME, _DISC
        if not me or disc is None or _DB is None:
            _report = "Sharing is not ready yet."
            return True
        peers = online_peers(me, disc)

        lists, failed = {}, []
        for name, (ip, port) in peers.items():
            try:
                data = fetch_list(me, name, ip, port)
            except Exception as e:
                print(f"[SHARE] Error while reading the list of {name}: {e}")
                data = None
            if data is None:
                failed.append(name)
                print(f"[SHARE] {name} ({ip}:{port}) did not answer the file list request.")
            else:
                lists[name] = data

        # 1) removals first, so removed files are never copied again
        for data in lists.values():
            for fid in data.get("deleted", []):
                apply_deletion(me, str(fid))
        deleted = {r[0] for r in _q("SELECT id FROM share_deleted WHERE viewer=?", (me,))}

        # 2) who holds what
        holders = {}
        for name, data in lists.items():
            for f in data.get("files", []):
                try:
                    fid = str(f["id"])
                    if fid in deleted:
                        continue
                    holders.setdefault(fid, set()).add(name)
                    _q("INSERT OR REPLACE INTO share_catalog "
                       "(id, viewer, owner, name, size, added) VALUES (?,?,?,?,?,?)",
                       (fid, me, f["owner"], f["name"], int(f["size"]), f["added"]))
                except (KeyError, ValueError, TypeError, sqlite3.Error) as e:
                    print(f"[SHARE] Skipped an invalid list entry from {name}: {e!r}")
        _holders = holders

        _report = f"Checked {len(lists)} of {len(peers)} online user(s)."
        if failed:
            _report += " No answer from: " + ", ".join(failed) + "."
        print("[SHARE]", _report)

        # 3) copy everything this PC does not have yet
        held = {r[0] for r in held_items(me)}
        os.makedirs(held_dir(me), exist_ok=True)
        for fid, who in holders.items():
            if fid in held or _sync_stop.is_set():
                continue
            try:
                row = _q("SELECT owner, name, size, added FROM share_catalog "
                         "WHERE id=? AND viewer=?", (fid, me))
                if not row:
                    continue
                owner, name, size, added = row[0]
                if size > AUTO_SYNC_MAX_MB * 1024 * 1024:
                    continue
                dest = os.path.join(held_dir(me), f"{fid}_{name}")
                _syncing.add(fid)
                try:
                    for holder in list(who):
                        if holder not in peers:
                            continue
                        ip, port = peers[holder]
                        ok, msg = download(me, holder, ip, port, fid, dest,
                                           lambda d, t: None, threading.Event())
                        if ok:
                            _q("INSERT OR REPLACE INTO share_items "
                               "(id, holder, owner, name, size, path, added) "
                               "VALUES (?,?,?,?,?,?,?)",
                               (fid, me, owner, name, size, dest, added))
                            print(f"[SHARE] Copied '{name}' from {holder}.")
                            break
                        print(f"[SHARE] Could not copy '{name}' from {holder}: {msg}")
                finally:
                    _syncing.discard(fid)
            except Exception as e:
                print(f"[SHARE] Error while copying {fid}: {e!r}")
    except sqlite3.Error as e:
        _report = f"Database error: {e}"
        print("[SHARE] Sync database error:", e)
    finally:
        _sync_lock.release()
    return True


def _sync_loop():
    """Syncs every SYNC_INTERVAL seconds, and immediately whenever the set of
    online users changes (for example when a user logs in again)."""
    last_names, last_run = None, 0.0
    _sync_stop.wait(2)
    while not _sync_stop.is_set():
        try:
            if _ME and _DISC is not None and _DB is not None:
                names = set(online_peers(_ME, _DISC))
                if names != last_names or time.monotonic() - last_run >= SYNC_INTERVAL:
                    last_names = names
                    sync_once()
                    last_run = time.monotonic()
        except Exception as e:
            print("[SHARE] Sync error:", e)
        _sync_stop.wait(2)


def sync_now():
    threading.Thread(target=sync_once, daemon=True).start()


def start_sync(me, discovery, db_path=None):
    """Call from home.py after the discovery object is created."""
    global _ME, _DISC, _sync_thread
    if _DB is None and db_path:
        init(db_path)
    _ME, _DISC = me, discovery
    if _sync_thread is not None and _sync_thread.is_alive():
        return
    _sync_stop.clear()
    _sync_thread = threading.Thread(target=_sync_loop, daemon=True)
    _sync_thread.start()


def stop_sync():
    """Call from shutdown() in home.py."""
    _sync_stop.set()


# ==========================================================================
# Window
# ==========================================================================
def open_shared_files(parent, db_path, me, discovery):
    global _window
    if _DB is None:
        init(db_path)
    start_sync(me, discovery)
    try:
        if _window is not None and _window.top.winfo_exists():
            _window.top.deiconify()
            _window.top.lift()
            _window.refresh()
            return _window
    except tk.TclError:
        pass
    _window = SharedFilesWindow(parent, me, discovery)
    return _window


def _col(name, default):
    return getattr(style, name, default) if style else default


# --------------------------------------------------------------------------
# Icons: Segoe Fluent Icons / Segoe MDL2 Assets glyphs (Windows 10/11).
# If neither font is installed, the old Unicode symbols are used instead.
# --------------------------------------------------------------------------
ICONS = {
    "upload":   ("⇧", "⇧"),
    "download": ("⇩", "⇩"),
    "refresh":  ("↻", "↻"),
    "delete":   ("🗑", "🗑"),
    "search":   ("⌕", "⌕"),
    "close":    ("✕", "✕"),
}


# Colour of every icon (same colours as the toolbar on the home screen)
ICON_COLORS = {
    "upload":   "#10B981",    # green
    "download": "#0EA5E9",    # sky blue
    "refresh":  "#8B5CF6",    # purple
    "delete":   "#EF4444",    # red
    "search":   "#64748B",    # slate
    "close":    "#64748B",    # slate (turns red on hover)
}


def icon_font(size=16):
    """Same icon font as the toolbar of the home screen: ((family, size, weight), False)."""
    return ("Segoe UI Symbol", size, "bold"), False


class Tooltip:
    """Shows a small label with the icon name when the mouse rests on a widget."""

    def __init__(self, widget, text, delay=350):
        self.widget, self.text, self.delay = widget, text, delay
        self.tip, self.job = None, None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def _schedule(self, _e=None):
        self._cancel()
        try:
            self.job = self.widget.after(self.delay, self._show)
        except tk.TclError:
            self.job = None

    def _cancel(self):
        if self.job:
            try:
                self.widget.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None

    def _show(self):
        self.job = None
        try:
            if self.tip or not self.widget.winfo_exists():
                return
            x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2 - 30
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
            self.tip = tk.Toplevel(self.widget)
            self.tip.wm_overrideredirect(True)
            self.tip.wm_attributes("-topmost", True)
            self.tip.wm_geometry(f"+{x}+{y}")
            tk.Label(self.tip, text=self.text, bg="#1f2937", fg="#ffffff",
                     font=(_col("FONT", "Segoe UI"), 9), padx=8, pady=4, bd=0).pack()
        except tk.TclError:
            self.tip = None

    def _hide(self, _e=None):
        self._cancel()
        if self.tip:
            try:
                self.tip.destroy()
            except tk.TclError:
                pass
            self.tip = None


class SharedFilesWindow:
    def __init__(self, parent, me, discovery):
        self.me, self.discovery = me, discovery
        self.cancel = threading.Event()
        self.after_id = None

        self.BG = _col("BG", "#f0f0f0")
        self.CARD = _col("CARD", "#ffffff")
        self.BORDER = _col("BORDER", "#b0b0b0")
        self.TEXT = _col("TEXT", "#000000")
        self.MUTED = _col("MUTED", "#666666")
        self.ACCENT = _col("ACCENT", "#2563eb")
        self.FONT = _col("FONT", "Segoe UI")
        self.HOVER = _col("HOVER", "#eef2f7")
        self.DANGER = "#dc2626"

        self.top = tk.Toplevel(parent)
        top = self.top
        top.title("Shared Files")
        top.configure(bg=self.BG)
        top.minsize(760, 420)
        if style:
            try:
                style.set_app_icon(top)
                style.center_window(top, 960, 560)
            except Exception:
                top.geometry("960x560")
        else:
            top.geometry("960x560")

        self.build_toolbar()
        self.build_table()
        self.build_bottom()
        top.bind("<Escape>", lambda e: self.close())
        top.protocol("WM_DELETE_WINDOW", self.close)

        self.reload()
        self.tick()

    # ---------------- icon helpers ----------------
    def glyph(self, key):
        return ICONS[key][0] if self.pro else ICONS[key][1]

    def icon_button(self, parent, key, tip, cmd, danger=False, size=16, pady=4):
        color = ICON_COLORS.get(key, self.MUTED)
        b = tk.Button(parent, text=self.glyph(key), command=cmd, relief="flat", bd=0,
                      bg=self.CARD, fg=color, cursor="hand2",
                      activebackground=self.CARD, activeforeground=color,
                      font=icon_font(size)[0], width=2, padx=2, pady=pady)
        Tooltip(b, tip)
        return b

    # ---------------- layout ----------------
    def build_toolbar(self):
        _font, self.pro = icon_font()

        bar = tk.Frame(self.top, bg=self.CARD)
        bar.pack(fill="x")
        tk.Frame(self.top, bg=self.BORDER, height=1).pack(fill="x")

        def sep():
            tk.Frame(bar, bg=self.BORDER, width=1).pack(
                side="left", fill="y", pady=8, padx=3)

        self.icon_button(bar, "upload", "Upload files", self.upload
                         ).pack(side="left", padx=(8, 0))
        self.icon_button(bar, "download", "Download selected", self.download_selected
                         ).pack(side="left", padx=0)
        self.icon_button(bar, "refresh", "Refresh / Sync now", self.refresh
                         ).pack(side="left", padx=0)
        self.icon_button(bar, "delete", "Remove selected file", self.remove_selected,
                         danger=True).pack(side="left", padx=0)

        right = tk.Frame(bar, bg=self.CARD)
        right.pack(side="right", padx=10)
        tk.Label(right, text=self.glyph("search"), bg=self.CARD, fg=ICON_COLORS["search"],
                 font=icon_font(16)[0]).pack(side="left", padx=(0, 6))
        self.search = tk.StringVar()
        tk.Entry(right, textvariable=self.search, width=28, relief="flat",
                 bg=_col("INPUT_BG", "#ffffff"), fg=_col("BLACK", "#000000"),
                 insertbackground=_col("BLACK", "#000000"), highlightthickness=1,
                 highlightbackground=self.BORDER, highlightcolor=self.ACCENT
                 ).pack(side="left", ipady=4)
        self.search.trace_add("write", lambda *_: self.reload())

    def build_table(self):
        st = ttk.Style(self.top)
        st.configure("Share.Treeview", rowheight=26, font=(self.FONT, 10),
                     background=self.CARD, fieldbackground=self.CARD,
                     foreground=self.TEXT, borderwidth=0)
        st.configure("Share.Treeview.Heading", font=(self.FONT, 10, "bold"))
        st.map("Share.Treeview",
               background=[("selected", self.ACCENT)],
               foreground=[("selected", _col("ON_ACCENT", "#ffffff"))])

        frame = tk.Frame(self.top, bg=self.BG)
        frame.pack(fill="both", expand=True, padx=8, pady=8)
        cols = ("name", "size", "owner", "date", "status")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings",
                                 selectmode="browse", style="Share.Treeview")
        for key, title, width in (("name", "File name", 330), ("size", "Size", 90),
                                  ("owner", "Shared by", 150), ("date", "Date", 150),
                                  ("status", "Status", 120)):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor="e" if key == "size" else "w")
        self.tree.tag_configure("unavailable", foreground=self.MUTED)
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.download_selected())

    def build_bottom(self):
        bottom = tk.Frame(self.top, bg=self.BG)
        bottom.pack(fill="x", side="bottom", padx=8, pady=(0, 8))
        self.status = tk.Label(bottom, text="", bg=self.BG, fg=self.MUTED,
                               font=(self.FONT, 9), anchor="w")
        self.status.pack(side="left")

        self.close_btn = self.icon_button(bottom, "close", "Close window", self.close,
                                          danger=True, size=14, pady=2)
        self.close_btn.pack(side="right", padx=2)

        self.cancel_btn = self.icon_button(bottom, "close", "Cancel transfer",
                                           self.cancel.set, danger=True, size=14, pady=2)
        self.bar = ttk.Progressbar(bottom, maximum=100, length=220)

    # ---------------- helpers ----------------
    def ui(self, fn):
        try:
            self.top.after(0, fn)
        except (tk.TclError, RuntimeError):
            pass

    def tick(self):
        """Re-reads the database every 3 seconds (the sync service fills it)."""
        try:
            if not self.top.winfo_exists():
                return
        except tk.TclError:
            return
        self.reload()
        self.after_id = self.top.after(3000, self.tick)

    def close(self):
        if self.after_id:
            try:
                self.top.after_cancel(self.after_id)
            except tk.TclError:
                pass
        self.cancel.set()
        self.top.destroy()

    def show_progress(self, on, cancellable=True):
        if on:
            self.cancel.clear()
            self.bar["value"] = 0
            self.bar.pack(side="left", padx=10)
            if cancellable:
                self.cancel_btn.pack(side="left")
        else:
            self.bar.pack_forget()
            self.cancel_btn.pack_forget()

    # ---------------- list ----------------
    def reload(self):
        q = self.search.get().strip().lower()
        held = {i: (o, n, s, a, p) for i, o, n, s, a, p in held_items(self.me)}
        rows = {}
        for fid, owner, name, size, added in _q(
                "SELECT id, owner, name, size, added FROM share_catalog WHERE viewer=?",
                (self.me,)):
            rows[fid] = (name, size, added, owner)
        for fid, (owner, name, size, added, _p) in held.items():
            rows[fid] = (name, size, added, owner)

        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        ordered = sorted(rows.items(), key=lambda kv: kv[1][2], reverse=True)
        for fid, (name, size, added, owner) in ordered:
            if q and q not in name.lower() and q not in owner.lower():
                continue
            tags = ()
            if fid in held:
                status = "Ready"
            elif fid in _syncing:
                status = "Copying..."
            elif _holders.get(fid):
                status = "Available"
            else:
                status, tags = "Unavailable", ("unavailable",)
            self.tree.insert("", "end", iid=fid, tags=tags, values=(
                name, human_size(size), "You" if owner == self.me else owner,
                to_local(added).strftime("%d-%b-%y %I:%M %p"), status))
        if selected and self.tree.exists(selected[0]):
            self.tree.selection_set(selected[0])
        if not self.bar.winfo_ismapped():
            text = f"{len(self.tree.get_children())} shared file(s)"
            self.status.config(text=f"{text}   |   {_report}" if _report else text)

    def refresh(self):
        self.status.config(text="Refreshing...")

        def work():
            ran = sync_once()

            def done():
                self.reload()
                if not ran:
                    self.status.config(text="A sync is already running, please wait...")
            self.ui(done)

        threading.Thread(target=work, daemon=True).start()

    # ---------------- actions ----------------
    def selected_row(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Shared Files", "Please select a file in the list first.",
                                parent=self.top)
            return None
        v = self.tree.item(sel[0], "values")
        owner = self.me if v[2] == "You" else v[2]
        return sel[0], v[0], owner

    def upload(self):
        paths = filedialog.askopenfilenames(
            parent=self.top, title="Select files to share with everyone")
        if not paths:
            return
        self.status.config(text="Uploading...")
        self.show_progress(True, cancellable=False)

        def prog(done, total):
            self.ui(lambda: self.bar.config(value=done * 100 / max(1, total)))

        def work():
            errors = []
            for p in paths:
                try:
                    add_file(self.me, p, prog)
                except (OSError, sqlite3.Error) as e:
                    errors.append(f"{os.path.basename(p)}: {e}")

            def done():
                self.show_progress(False)
                self.reload()
                notify_peers()
                sync_now()
                if errors:
                    messagebox.showerror("Upload", "\n".join(errors), parent=self.top)
                else:
                    self.status.config(
                        text=f"{len(paths)} file(s) uploaded. Other users will "
                             "receive them automatically.")
            self.ui(done)

        threading.Thread(target=work, daemon=True).start()

    def download_selected(self):
        row = self.selected_row()
        if not row:
            return
        fid, name, _owner = row
        dest = filedialog.asksaveasfilename(parent=self.top, title="Save file as",
                                            initialfile=name)
        if not dest:
            return

        # 1) a copy is already stored on this PC -> just copy it
        local = _q("SELECT path FROM share_items WHERE id=? AND holder=?", (fid, self.me))
        if local and os.path.isfile(local[0][0]):
            try:
                shutil.copyfile(local[0][0], dest)
                self.status.config(text=f"Saved: {dest}")
                if messagebox.askyesno("Download complete",
                                       f"{name} was saved.\nDo you want to open it now?",
                                       parent=self.top):
                    open_path(dest)
            except OSError as e:
                messagebox.showerror("Download", str(e), parent=self.top)
            return

        # 2) otherwise download from any online user who holds the file
        peers = online_peers(self.me, self.discovery)
        candidates = [(h, peers[h]) for h in _holders.get(fid, ()) if h in peers]
        if not candidates:
            messagebox.showwarning(
                "Shared Files",
                "No user who has this file is online right now.\n\n"
                "The file will be available again as soon as one of them comes online.",
                parent=self.top)
            return

        self.status.config(text=f"Downloading {name}...")
        self.show_progress(True)

        def prog(done, total):
            self.ui(lambda: self.bar.config(value=done * 100 / max(1, total)))

        def work():
            ok, msg = False, "Download failed."
            for holder, (ip, port) in candidates:
                ok, msg = download(self.me, holder, ip, port, fid, dest, prog, self.cancel)
                if ok or self.cancel.is_set():
                    break

            def finish():
                self.show_progress(False)
                if ok:
                    self.status.config(text=f"Saved: {dest}")
                    if messagebox.askyesno("Download complete",
                                           f"{name} was downloaded.\n"
                                           "Do you want to open it now?",
                                           parent=self.top):
                        open_path(dest)
                else:
                    self.status.config(text="Download failed")
                    messagebox.showerror("Download", msg, parent=self.top)
            self.ui(finish)

        threading.Thread(target=work, daemon=True).start()

    def remove_selected(self):
        row = self.selected_row()
        if not row:
            return
        fid, name, owner = row
        if owner != self.me:
            messagebox.showinfo("Shared Files",
                                "You can only remove files that you uploaded yourself.",
                                parent=self.top)
            return
        if messagebox.askyesno(
                "Remove file",
                f"Stop sharing '{name}'?\n\nThe file will be deleted from every "
                "user's PC during their next sync.", parent=self.top):
            apply_deletion(self.me, fid)
            self.reload()
            notify_peers()
            sync_now()