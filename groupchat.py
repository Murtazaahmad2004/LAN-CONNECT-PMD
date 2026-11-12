import sqlite3
import threading
import tkinter as tk
import uuid
from datetime import datetime, timezone
from tkinter import messagebox

import style

GROUP_ID = "general"
GROUP_NAME = "General Group"
UNREAD_KEY = "__group__"          # key used in home.py's `unread` dict
MAX_MEMBERS = 200
MAX_NAME_LEN = 100

_DB = None
_window = None


# ==========================================================================
# Database
# ==========================================================================
def _connect():
    return sqlite3.connect(_DB, timeout=30)


def _q(sql, args=()):
    conn = _connect()
    try:
        rows = conn.execute(sql, args).fetchall()
        conn.commit()
        return rows
    finally:
        conn.close()


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _clean(name):
    """Trims a user name and collapses repeated spaces."""
    return " ".join(str(name).split())[:MAX_NAME_LEN]


def _add_column(conn, table, column, definition):
    columns = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init(db_path):
    """Call once from home.py, next to sharedfiles.init().
    Creates the tables and upgrades tables made by an older version."""
    global _DB
    _DB = db_path
    conn = _connect()
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS group_members (
                            viewer TEXT NOT NULL, group_id TEXT NOT NULL,
                            member TEXT NOT NULL, added_by TEXT, added_at TEXT,
                            PRIMARY KEY (viewer, group_id, member))""")
        conn.execute("""CREATE TABLE IF NOT EXISTS group_messages (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            viewer TEXT NOT NULL, group_id TEXT NOT NULL,
                            uid TEXT NOT NULL, sender TEXT NOT NULL,
                            message TEXT NOT NULL,
                            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                            kind TEXT NOT NULL DEFAULT 'message',
                            UNIQUE (viewer, group_id, uid))""")

        # upgrade tables created by the first version
        _add_column(conn, "group_members", "added_by", "TEXT")
        _add_column(conn, "group_members", "added_at", "TEXT")
        _add_column(conn, "group_messages", "kind", "TEXT NOT NULL DEFAULT 'message'")

        # remove duplicate members that differ only in upper/lower case,
        # then make such duplicates impossible
        conn.execute("""DELETE FROM group_members WHERE rowid NOT IN (
                            SELECT MIN(rowid) FROM group_members
                            GROUP BY viewer, group_id, member COLLATE NOCASE)""")
        conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_group_members_nocase
                        ON group_members (viewer, group_id, member COLLATE NOCASE)""")
        conn.execute("""CREATE INDEX IF NOT EXISTS idx_group_messages_order
                        ON group_messages (viewer, group_id, id)""")
        conn.commit()
    finally:
        conn.close()


def get_members(me):
    rows = _q("SELECT member FROM group_members WHERE viewer=? AND group_id=? "
              "ORDER BY member COLLATE NOCASE", (me, GROUP_ID))
    return [r[0] for r in rows]


def add_members(me, names, added_by=None):
    """Saves the names as members.  Returns only the names that were really
    new (a name that is already a member is never stored twice)."""
    clean, seen = [], set()
    for name in names:
        name = _clean(name)
        if name and name.lower() not in seen:
            seen.add(name.lower())
            clean.append(name)
    if not clean:
        return []

    added = []
    conn = _connect()
    try:
        for name in clean:
            cur = conn.execute(
                "INSERT OR IGNORE INTO group_members "
                "(viewer, group_id, member, added_by, added_at) VALUES (?,?,?,?,?)",
                (me, GROUP_ID, name, added_by, _now()))
            if cur.rowcount:
                added.append(name)
        conn.commit()
    finally:
        conn.close()
    return added


def save_message(me, uid, sender, text, kind="message"):
    """Stores one message.  Returns True if it is new, False if a message with
    this uid was stored before (so nothing is ever saved twice)."""
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO group_messages "
            "(viewer, group_id, uid, sender, message, kind, timestamp) "
            "VALUES (?,?,?,?,?,?,?)",
            (me, GROUP_ID, uid, sender, text, kind, _now()))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_history(me, after_id=0):
    """Rows (id, sender, message, timestamp, kind) newer than `after_id`."""
    return _q("SELECT id, sender, message, timestamp, kind FROM group_messages "
              "WHERE viewer=? AND group_id=? AND id>? ORDER BY id ASC",
              (me, GROUP_ID, after_id))


def handle_incoming(me, msg):
    """Called by home.py (network thread) for 'group_sync' / 'group_msg'.
    Returns {'kind': 'sync'} or {'kind': 'msg', 'sender', 'text'} or None."""
    kind = msg.get("type")
    sender = _clean(msg.get("from", ""))
    if not sender:
        return None

    if kind == "group_sync":
        names = [str(n) for n in (msg.get("members") or [])][:MAX_MEMBERS]
        add_members(me, [sender, me])
        add_members(me, names, added_by=sender)

        # "Ali added you, Sara" - the same sync_id is never shown twice
        added = [_clean(n) for n in (msg.get("added") or []) if _clean(n)]
        sync_id = str(msg.get("sync_id", "")).strip()
        if added and sync_id:
            shown = ["you" if n.lower() == me.lower() else n for n in added]
            save_message(me, f"sys-{sync_id}", sender,
                         f"{sender} added {', '.join(shown)}", kind="system")
        return {"kind": "sync"}

    if kind == "group_msg":
        text = str(msg.get("text", ""))
        uid = str(msg.get("id", "")).strip() or uuid.uuid4().hex
        if not text.strip():
            return None
        add_members(me, [me, sender])
        if not save_message(me, uid, sender, text):
            return None
        return {"kind": "msg", "sender": sender, "text": text}

    return None


def _local(ts=None):
    if ts is None:
        return datetime.now()
    try:
        return datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc).astimezone()
    except ValueError:
        return datetime.now()


def _deliver(send_json, names, payload, done=None):
    """Sends `payload` to every name in a background thread.
    done(ok_list, failed_list) is called when finished."""
    def work():
        ok, failed = [], []
        for name in names:
            try:
                good = send_json(name, dict(payload))
            except Exception as e:
                print(f"[GROUP] Could not send to {name}: {e}")
                good = False
            (ok if good else failed).append(name)
        if done:
            done(ok, failed)

    threading.Thread(target=work, daemon=True).start()


# ==========================================================================
# Window
# ==========================================================================
def open_group_window(parent, me, discovery, send_json, chat_view_cls, font_size=13):
    """send_json(name, dict) -> bool   (MessageService.send_json in home.py)
    chat_view_cls: the ChatView class of home.py (bubbles)."""
    global _window
    try:
        if _window is not None and _window.top.winfo_exists():
            _window.top.deiconify()
            _window.top.lift()
            _window.top.focus_force()
            return _window
    except tk.TclError:
        pass
    _window = GroupWindow(parent, me, discovery, send_json, chat_view_cls, font_size)
    return _window


def window_open():
    """The open GroupWindow or None."""
    try:
        if _window is not None and _window.top.winfo_exists():
            return _window
    except tk.TclError:
        pass
    return None


class GroupWindow:
    def __init__(self, parent, me, discovery, send_json, chat_view_cls, font_size):
        self.me, self.discovery, self.send_json = me, discovery, send_json
        self.last_id = 0                # id of the last message shown
        add_members(me, [me])           # the first person to open it is a member

        self.top = tk.Toplevel(parent)
        top = self.top
        top.title(GROUP_NAME)
        top.configure(bg=style.BG)
        top.minsize(520, 420)
        try:
            style.set_app_icon(top)
        except Exception:
            pass
        try:
            style.center_window(top, 720, 560)
        except Exception:
            top.geometry("720x560")

        # ---- header
        header = tk.Frame(top, bg=style.CARD)
        header.pack(fill="x")
        tk.Frame(top, bg=style.BORDER, height=1).pack(fill="x")
        tk.Label(header, text=f"👥  {GROUP_NAME}", font=style.HEADING_FONT,
                 bg=style.CARD, fg=style.WHITE).pack(side="left", padx=15, pady=12)
        style.make_button(header, "➕  Add new members", self.add_members_dialog,
                          kind="primary").pack(side="right", padx=12, pady=8)

        self.members_label = tk.Label(top, text="", bg=style.BG, fg=style.MUTED,
                                      font=(style.FONT, 9), anchor="w", justify="left")
        self.members_label.pack(fill="x", padx=14, pady=(6, 0))
        self.members_label.bind(
            "<Configure>",
            lambda e: self.members_label.config(wraplength=max(200, e.width - 8)))

        # ---- bottom (packed before the chat so it stays visible)
        bottom = tk.Frame(top, bg=style.CARD)
        bottom.pack(side="bottom", fill="x", padx=10, pady=10)
        self.status = tk.Label(top, text="", bg=style.BG, fg=style.MUTED,
                               font=(style.FONT, 9), anchor="w")
        self.status.pack(side="bottom", fill="x", padx=14)

        self.input = tk.Text(bottom, font=(style.FONT, font_size), width=1, height=3,
                             wrap="word", bg=style.INPUT_BG, fg=style.BLACK,
                             insertbackground=style.BLACK, relief="flat",
                             padx=10, pady=8, highlightthickness=1,
                             highlightbackground=style.BORDER,
                             highlightcolor=style.ACCENT)
        self.input.pack(side="left", fill="x", expand=True, padx=8, pady=8)
        style.make_button(bottom, "Send", self.send, kind="primary"
                          ).pack(side="right", padx=8, pady=8)
        self.input.bind("<Return>", self._on_enter)

        # ---- messages
        self.chat = chat_view_cls(top, font_size)
        self.chat.pack(fill="both", expand=True, padx=10, pady=(6, 4))

        self.sync_new()                 # shows the saved history
        top.protocol("WM_DELETE_WINDOW", self.close)
        top.bind("<Escape>", lambda e: self.close())
        self.input.focus_set()

    # ---------------- helpers ----------------
    def ui(self, fn):
        try:
            self.top.after(0, fn)
        except (tk.TclError, RuntimeError):
            pass

    def close(self):
        global _window
        _window = None
        try:
            self.top.destroy()
        except tk.TclError:
            pass

    def is_active(self):
        try:
            return (self.top.state() in ("normal", "zoomed")
                    and self.top.focus_displayof() is not None)
        except tk.TclError:
            return False

    def refresh_members(self):
        members = get_members(self.me)
        names = [("You" if m.lower() == self.me.lower() else m) for m in members]
        self.members_label.config(
            text=f"Members ({len(members)}):  " + ", ".join(names))

    def add_line(self, sender, text, ts=None, kind="message"):
        moment = _local(ts)
        time_text = moment.strftime("%I:%M %p")
        if kind == "system":
            self.chat.add_message(f"ℹ  {text}", time_text, False, day=moment.date())
            return
        is_me = sender == self.me
        shown = text if is_me else f"{sender}\n{text}"
        self.chat.add_message(shown, time_text, is_me, day=moment.date())

    def sync_new(self):
        """Shows every saved message that is not on the screen yet and updates
        the member list.  The database is the single source, so nothing can be
        shown twice."""
        for rid, sender, text, ts, kind in get_history(self.me, self.last_id):
            self.last_id = rid
            self.add_line(sender, text, ts, kind)
        self.refresh_members()

    # ---------------- called from home.py ----------------
    def on_message(self, sender=None, text=None):
        self.sync_new()                 # the message is already saved

    def on_members_changed(self):
        self.sync_new()

    # ---------------- sending ----------------
    def _on_enter(self, event):
        if event.state & 0x1:           # Shift+Enter = new line
            return None
        self.send()
        return "break"

    def send(self):
        text = self.input.get("1.0", "end-1c").strip()
        if not text:
            return
        targets = [m for m in get_members(self.me) if m.lower() != self.me.lower()]
        if not targets:
            messagebox.showinfo(
                GROUP_NAME,
                "There are no other members in the group yet.\n\n"
                "Click 'Add new members' to add the users who are online.",
                parent=self.top)
            return

        uid = uuid.uuid4().hex
        try:
            save_message(self.me, uid, self.me, text)
        except sqlite3.Error as e:
            messagebox.showerror("Database Error", str(e), parent=self.top)
            return

        self.sync_new()
        self.input.delete("1.0", "end")
        self.status.config(text="Sending...")

        def done(ok, failed):
            if failed:
                msg = "Not delivered (offline): " + ", ".join(failed)
            else:
                msg = f"Delivered to {len(ok)} member(s)."
            self.ui(lambda: self.status.config(text=msg))

        _deliver(self.send_json, targets,
                 {"type": "group_msg", "id": uid, "group": GROUP_ID, "text": text},
                 done)

    # ---------------- add members ----------------
    def add_members_dialog(self):
        current = {m.lower() for m in get_members(self.me)}
        online = {}
        for u in self.discovery.get_users():
            name = _clean(u.get("username") or "")
            status = u.get("status", "Offline")
            if (name and name.lower() != self.me.lower() and status != "Offline"
                    and name.lower() not in current):
                online[name] = status
        names = sorted(online, key=str.lower)

        dlg = tk.Toplevel(self.top)
        dlg.title("Add new members")
        dlg.configure(bg=style.BG)
        dlg.transient(self.top)
        try:
            style.center_window(dlg, 360, 420)
        except Exception:
            dlg.geometry("360x420")

        tk.Label(dlg, text="Users who are online", font=style.ui_font(11, True),
                 bg=style.BG, fg=style.WHITE).pack(anchor="w", padx=16, pady=(14, 2))

        buttons = tk.Frame(dlg, bg=style.BG)
        buttons.pack(side="bottom", fill="x", padx=16, pady=12)
        style.make_button(buttons, "Cancel", dlg.destroy, kind="secondary",
                          width=10).pack(side="right", padx=4)

        if not names:
            tk.Label(dlg, text="No other user is online right now,\n"
                               "or everyone online is already in the group.",
                     bg=style.BG, fg=style.MUTED, justify="left"
                     ).pack(anchor="w", padx=16, pady=20)
        else:
            tk.Label(dlg, text="Click to select one or more users.",
                     bg=style.BG, fg=style.MUTED, font=(style.FONT, 9)
                     ).pack(anchor="w", padx=16, pady=(0, 6))

            box = tk.Frame(dlg, bg=style.BG)
            box.pack(fill="both", expand=True, padx=16)
            lb = tk.Listbox(box, selectmode="multiple", activestyle="none",
                            font=(style.FONT, 11), bg=style.INPUT_BG, fg=style.BLACK,
                            selectbackground=style.ACCENT,
                            selectforeground=style.ON_ACCENT,
                            highlightthickness=1, highlightbackground=style.BORDER,
                            relief="flat", exportselection=False)
            sb = tk.Scrollbar(box, orient="vertical", command=lb.yview)
            lb.configure(yscrollcommand=sb.set)
            sb.pack(side="right", fill="y")
            lb.pack(side="left", fill="both", expand=True)
            for n in names:
                suffix = {"Busy": "   (Busy)", "Inactive": "   (Away)"}.get(online[n], "")
                lb.insert("end", f"{n}{suffix}")

            def add_selected():
                chosen = [names[i] for i in lb.curselection()]
                if not chosen:
                    messagebox.showinfo(GROUP_NAME, "Please select at least one user.",
                                        parent=dlg)
                    return
                dlg.destroy()
                self.add_chosen(chosen)

            style.make_button(buttons, "Add selected", add_selected, kind="primary",
                              width=14).pack(side="right", padx=4)

        try:
            dlg.grab_set()
        except tk.TclError:
            pass

    def add_chosen(self, chosen):
        sync_id = uuid.uuid4().hex
        try:
            add_members(self.me, [self.me])
            newly = add_members(self.me, chosen, added_by=self.me)
            if not newly:
                self.status.config(text="Selected user(s) are already members.")
                return
            everyone = get_members(self.me)
            save_message(self.me, f"sys-{sync_id}", self.me,
                         f"You added {', '.join(newly)}", kind="system")
        except sqlite3.Error as e:
            messagebox.showerror("Database Error", str(e), parent=self.top)
            return

        self.sync_new()
        self.status.config(text="Adding " + ", ".join(newly) + "...")

        def done(ok, failed):
            msg = "Added: " + ", ".join(newly) + "."
            if failed:
                msg += "  Could not reach: " + ", ".join(failed) + "."
            self.ui(lambda: self.status.config(text=msg))

        # every member (new and old) gets the full member list
        _deliver(self.send_json,
                 [m for m in everyone if m.lower() != self.me.lower()],
                 {"type": "group_sync", "group": GROUP_ID, "members": everyone,
                  "added": newly, "sync_id": sync_id},
                 done)