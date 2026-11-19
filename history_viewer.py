import csv
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import tkinter as tk
import uuid
from datetime import datetime, timezone
from tkinter import filedialog, messagebox, ttk

try:
    import style
except ImportError:          # sirf standalone testing ke liye
    style = None

_open_window = None          # ek waqt mein sirf ek History window


def open_history(parent, db_path, local_username, select=None):
    """History window kholta hai (pehle se khuli ho to samne le aata hai).
    select = kisi contact ka naam jo shuru mein khula hona chahiye."""
    global _open_window
    try:
        if _open_window is not None and _open_window.top.winfo_exists():
            _open_window.top.deiconify()
            _open_window.top.lift()
            if select:
                _open_window.select_contact(select)
            return _open_window
    except tk.TclError:
        pass
    _open_window = HistoryWindow(parent, db_path, local_username, select)
    return _open_window


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _col(name, default):
    return getattr(style, name, default) if style else default


def to_local(ts):
    """DB mein time UTC hota hai -> local datetime."""
    try:
        return datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc).astimezone()
    except ValueError:
        return datetime.now()


def fmt_ts(ts):
    d = to_local(ts)
    return f"{d:%d-%b-%y} - {d.hour % 12 or 12}:{d:%M:%S %p}"


def make_person_icon(master, color):
    img = tk.PhotoImage(master=master, width=16, height=16)
    for y in range(16):
        for x in range(16):
            head = (x - 8) ** 2 + (y - 4.5) ** 2 <= 11
            body = y >= 9 and ((x - 8) / 6.5) ** 2 + ((y - 15) / 6) ** 2 <= 1
            if head or body:
                img.put(color, (x, y))
    return img


class ToolTip:
    def __init__(self, widget, text):
        self.widget, self.text, self.tip = widget, text, None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def show(self, _=None):
        x = self.widget.winfo_rootx() + 8
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, bg="#ffffe1", fg="#000000",
                 relief="solid", bd=1, font=(style.FONT, 9), padx=4).pack()

    def hide(self, _=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


# --------------------------------------------------------------------------
# window
# --------------------------------------------------------------------------
class HistoryWindow:
    def __init__(self, parent, db_path, me, select=None):
        self.db_path, self.me = db_path, me
        self.current = None
        self.matches, self.match_pos = [], -1

        # theme colours (app ki current theme se)
        self.BG = _col("BG", "#f0f0f0")
        self.CARD = _col("CARD", "#ffffff")
        self.BORDER = _col("BORDER", "#b0b0b0")
        self.TEXT = _col("TEXT", "#000000")
        self.MUTED = _col("MUTED", "#666666")
        self.ACCENT = _col("ACCENT", "#2563eb")
        self.INPUT_BG = _col("INPUT_BG", "#ffffff")
        self.FONT = _col("FONT", "Segoe UI")

        self.top = tk.Toplevel(parent)
        top = self.top
        top.title("Message History")
        top.configure(bg=self.BG)
        top.minsize(760, 440)
        if style:
            try:
                style.set_app_icon(top)
            except Exception:
                pass
            try:
                style.center_window(top, 1000, 620)
            except Exception:
                top.geometry("1000x620")
        else:
            top.geometry("1000x620")

        self.ico_me = make_person_icon(top, "#e8a020")
        self.ico_other = make_person_icon(top, "#3a4fb5")

        self.build_toolbar()
        self.build_body()
        self.build_bottom()
        self.bind_keys()
        self.load_contacts(select)
        top.focus_set()

    # ---------------- database ----------------
    def q(self, sql, args=()):
        conn = sqlite3.connect(self.db_path, timeout=30)
        try:
            rows = conn.execute(sql, args).fetchall()
            conn.commit()
            return rows
        finally:
            conn.close()

    def db_contacts(self, query=""):
        sql = ("SELECT peer FROM ("
               " SELECT CASE WHEN sender=? THEN receiver ELSE sender END AS peer,"
               " message FROM messages WHERE sender=? OR receiver=?)")
        args = [self.me, self.me, self.me]
        if query:
            sql += " WHERE peer LIKE ? OR message LIKE ?"
            args += [f"%{query}%", f"%{query}%"]
        sql += " GROUP BY peer ORDER BY peer COLLATE NOCASE"
        return [r[0] for r in self.q(sql, args)]

    def db_messages(self, peer):
        return self.q(
            "SELECT timestamp, sender, message FROM messages "
            "WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?) "
            "ORDER BY id ASC", (self.me, peer, peer, self.me))

    def db_delete(self, peer):
        self.q("DELETE FROM messages WHERE (sender=? AND receiver=?) "
               "OR (sender=? AND receiver=?)", (self.me, peer, peer, self.me))

    # ---------------- UI ----------------
    def build_toolbar(self):
        bar = tk.Frame(self.top, bg=self.CARD, height=42)
        bar.pack(fill="x", side="top")
        tk.Frame(self.top, bg=self.BORDER, height=1).pack(fill="x")

        def btn(text, cmd, tip, size=15, fg=None):
            b = tk.Button(bar, text=text, command=cmd, relief="flat", bd=0,
                          bg=self.CARD, fg=fg or self.TEXT,
                          activebackground=self.CARD, activeforeground=self.ACCENT,
                          font=("Segoe UI Emoji", size), padx=6, cursor="hand2")
            b.bind("<Enter>", lambda e: b.config(fg=self.ACCENT))
            b.bind("<Leave>", lambda e: b.config(fg=fg or self.TEXT))
            ToolTip(b, tip)
            b.pack(side="left", pady=3)
            return b

        def sep():
            tk.Frame(bar, bg=self.BORDER, width=1).pack(
                side="left", fill="y", pady=8, padx=5)

        btn("🖨", self.print_current, "Print current chat").pack_configure(padx=(8, 0))
        self.arrow = btn("▾", self.show_print_menu, "More print options", size=9)
        self.print_menu = tk.Menu(self.top, tearoff=0)
        self.print_menu.add_command(label="Print current chat", command=self.print_current)
        self.print_menu.add_command(label="Print all chats", command=self.print_all)
        self.print_menu.add_separator()
        self.print_menu.add_command(label="Print preview", command=self.print_preview)

        btn("📂", self.import_history, "Import history (JSON / CSV)")
        sep()
        btn("💾", self.export_chat, "Save / Export current chat")
        sep()
        btn("📋", self.copy_text, "Copy selected text (or whole chat)")
        btn("🗑", self.delete_chat, "Delete history of selected contact")

        right = tk.Frame(bar, bg=self.CARD)
        right.pack(side="right", padx=10)
        tk.Label(right, text="🔎", bg=self.CARD, fg=self.ACCENT,
                 font=("Segoe UI Emoji", 10)).pack(side="left", padx=(0, 4))
        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(
            right, textvariable=self.search_var, width=30, relief="flat",
            bg=self.INPUT_BG, fg=_col("BLACK", "#000000"),
            insertbackground=_col("BLACK", "#000000"),
            highlightthickness=1, highlightbackground=self.BORDER,
            highlightcolor=self.ACCENT, font=(self.FONT, 10))
        self.search_entry.pack(side="left", ipady=3)
        self.search_var.trace_add("write", lambda *_: self.on_search())

    def build_body(self):
        st = ttk.Style(self.top)
        st.configure("Hist.Treeview", rowheight=24, font=(self.FONT, 10),
                     background=self.CARD, fieldbackground=self.CARD,
                     foreground=self.TEXT, borderwidth=0)
        st.map("Hist.Treeview",
               background=[("selected", self.ACCENT)],
               foreground=[("selected", _col("ON_ACCENT", "#ffffff"))])

        pw = ttk.PanedWindow(self.top, orient="horizontal")
        pw.pack(fill="both", expand=True, padx=6, pady=6)

        left = tk.Frame(pw, bg=self.CARD, highlightthickness=1,
                        highlightbackground=self.BORDER)
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse",
                                 style="Hist.Treeview")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_select_contact)
        self.tree.bind("<Button-3>", self.contact_menu)
        self.ctx = tk.Menu(self.top, tearoff=0)
        self.ctx.add_command(label="Export chat...", command=self.export_chat)
        self.ctx.add_command(label="Delete history", command=self.delete_chat)
        pw.add(left, weight=0)

        right = tk.Frame(pw, bg=self.BG, highlightthickness=1,
                         highlightbackground=self.BORDER)
        sb = ttk.Scrollbar(right, orient="vertical")
        sb.pack(side="right", fill="y")
        t = self.text = tk.Text(
            right, wrap="word", bd=0, bg=self.BG, fg=self.TEXT,
            cursor="arrow", font=(self.FONT, 10), yscrollcommand=sb.set,
            padx=4, pady=2, inactiveselectbackground=self.ACCENT,
            highlightthickness=0)
        sb.config(command=t.yview)
        t.pack(fill="both", expand=True)
        pw.add(right, weight=1)
        self.top.after(60, lambda: pw.sashpos(0, 190))

        t.tag_configure("out", background=self.CARD)
        t.tag_configure("inc", background=self.BG)
        t.tag_configure("arrow", foreground="#2e9e2e", font=(self.FONT, 11, "bold"))
        t.tag_configure("head", foreground=self.TEXT, font=(self.FONT, 10))
        t.tag_configure("body", foreground=self.ACCENT, font=(self.FONT, 10),
                        lmargin1=64, lmargin2=64, spacing3=6)
        t.tag_configure("match", background="#fff176", foreground="#000000")
        t.tag_configure("cur", background="#ff9800", foreground="#000000")
        t.tag_raise("sel")
        t.bind("<Key>", self._block_edit)
        t.bind("<Button-3>", self.text_menu)
        self.tctx = tk.Menu(self.top, tearoff=0)
        self.tctx.add_command(label="Copy", command=self.copy_text)
        self.tctx.add_command(label="Select all", command=self.select_all)

    def build_bottom(self):
        bottom = tk.Frame(self.top, bg=self.BG)
        bottom.pack(fill="x", side="bottom")
        self.status = tk.Label(bottom, text="", bg=self.BG, fg=self.MUTED,
                               font=(self.FONT, 9))
        self.status.pack(side="left", padx=10)
        if style and hasattr(style, "make_button"):
            b = style.make_button(bottom, "Close", self.top.destroy,
                                  kind="secondary", width=10)
        else:
            b = ttk.Button(bottom, text="Close", width=10, command=self.top.destroy)
        b.pack(side="right", padx=10, pady=8)

    def bind_keys(self):
        t = self.top
        t.bind("<Escape>", lambda e: t.destroy())
        t.bind("<Control-f>", lambda e: (self.search_entry.focus_set(), "break"))
        t.bind("<Control-p>", lambda e: self.print_current())
        t.bind("<Control-s>", lambda e: self.export_chat())
        t.bind("<Control-o>", lambda e: self.import_history())
        t.bind("<F3>", lambda e: self.next_match(1))
        t.bind("<Shift-F3>", lambda e: self.next_match(-1))
        self.search_entry.bind("<Return>", lambda e: self.next_match(1))
        self.search_entry.bind("<Shift-Return>", lambda e: self.next_match(-1))
        self.tree.bind("<Delete>", lambda e: self.delete_chat())

    def _block_edit(self, e):
        if (e.state & 0x4) and e.keysym.lower() in ("c", "a"):
            if e.keysym.lower() == "a":
                self.select_all()
                return "break"
            return None
        if e.keysym in ("Up", "Down", "Left", "Right", "Prior", "Next", "Home", "End"):
            return None
        return "break"

    # ---------------- contacts / chat ----------------
    def load_contacts(self, select=None):
        names = self.db_contacts(self.search_var.get().strip())
        self.tree.delete(*self.tree.get_children())
        for n in names:
            self.tree.insert("", "end", iid=n, text=" " + n, image=self.ico_other)
        if names:
            target = select if select in names else (
                self.current if self.current in names else names[0])
            self.current = None            # force reload
            self.tree.selection_set(target)
            self.tree.see(target)
        else:
            self.current = None
            self.show_chat()

    def select_contact(self, name):
        if self.tree.exists(name):
            self.tree.selection_set(name)
            self.tree.see(name)

    def on_select_contact(self, _=None):
        sel = self.tree.selection()
        if sel and sel[0] != self.current:
            self.current = sel[0]
            self.show_chat()

    def on_search(self):
        self.load_contacts()
        self.show_chat()
        if self.matches:
            self.next_match(0)

    def show_chat(self):
        t = self.text
        t.config(state="normal")
        t.delete("1.0", "end")
        self.matches, self.match_pos = [], -1
        if not self.current:
            self.status.config(text="No history found")
            return
        rows = self.db_messages(self.current)
        for ts, sender, body in rows:
            out = sender == self.me
            start = t.index("end-1c")
            t.image_create("end", image=self.ico_me if out else self.ico_other)
            t.insert("end", " ")
            t.insert("end", "➜", "arrow")
            t.insert("end", " ")
            t.image_create("end", image=self.ico_other if out else self.ico_me)
            t.insert("end", f" {fmt_ts(ts)} ({'Outgoing' if out else 'Incoming'}):\n", "head")
            t.insert("end", body + "\n", "body")
            t.tag_add("out" if out else "inc", start, "end-1c")
        self.highlight(self.search_var.get().strip())
        t.yview_moveto(0 if self.matches else 1)
        self.status.config(text=f"{self.current}  |  {len(rows)} message(s)")

    def highlight(self, query):
        if not query:
            return
        t, idx, n = self.text, "1.0", tk.IntVar()
        while True:
            pos = t.search(query, idx, stopindex="end", nocase=True, count=n)
            if not pos or n.get() == 0:
                break
            end = f"{pos}+{n.get()}c"
            t.tag_add("match", pos, end)
            self.matches.append((pos, end))
            idx = end

    def next_match(self, step):
        if not self.matches:
            return "break"
        t = self.text
        t.tag_remove("cur", "1.0", "end")
        self.match_pos = (self.match_pos + step) % len(self.matches)
        a, b = self.matches[self.match_pos]
        t.tag_add("cur", a, b)
        t.see(a)
        self.status.config(
            text=f"{self.current}  |  match {self.match_pos + 1} of {len(self.matches)}")
        return "break"

    # ---------------- menus ----------------
    def contact_menu(self, e):
        row = self.tree.identify_row(e.y)
        if row:
            self.tree.selection_set(row)
            self.ctx.tk_popup(e.x_root, e.y_root)

    def text_menu(self, e):
        self.tctx.tk_popup(e.x_root, e.y_root)

    def show_print_menu(self):
        b = self.arrow
        self.print_menu.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())

    # ---------------- text builders ----------------
    def chat_text(self, peer):
        lines = [f"Chat history: {self.me}  <->  {peer}", "=" * 50]
        for ts, sender, body in self.db_messages(peer):
            lines.append(f"{fmt_ts(ts)} ({'Outgoing' if sender == self.me else 'Incoming'}):")
            lines += [f"    {ln}" for ln in body.split("\n")]
            lines.append("")
        return "\n".join(lines)

    # ---------------- actions ----------------
    def need_chat(self):
        if not self.current:
            messagebox.showinfo("Message History", "Pehle koi contact select karein.",
                                parent=self.top)
            return False
        return True

    def select_all(self):
        self.text.tag_add("sel", "1.0", "end-1c")
        return "break"

    def copy_text(self):
        if not self.need_chat():
            return
        try:
            data = self.text.get("sel.first", "sel.last")
        except tk.TclError:
            data = self.chat_text(self.current)
        self.top.clipboard_clear()
        self.top.clipboard_append(data)
        self.status.config(text="Copied to clipboard")

    def _send_to_printer(self, content):
        fd, path = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        try:
            if sys.platform.startswith("win"):
                os.startfile(path, "print")
            else:
                subprocess.run(["lp", path], check=True)
            self.status.config(text="Sent to printer")
        except Exception as ex:
            messagebox.showerror("Print", f"Print nahi ho saka:\n{ex}", parent=self.top)

    def print_current(self):
        if self.need_chat():
            self._send_to_printer(self.chat_text(self.current))

    def print_all(self):
        names = self.db_contacts()
        if not names:
            messagebox.showinfo("Print", "Koi history maujood nahi.", parent=self.top)
            return
        self._send_to_printer("\n\n".join(self.chat_text(n) for n in names))

    def print_preview(self):
        if not self.need_chat():
            return
        win = tk.Toplevel(self.top)
        win.title(f"Print preview - {self.current}")
        win.geometry("620x520")
        win.configure(bg=self.BG)
        txt = tk.Text(win, font=("Consolas", 10), wrap="word", bg="#ffffff",
                      fg="#000000")
        txt.insert("1.0", self.chat_text(self.current))
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True)
        row = tk.Frame(win, bg=self.BG)
        row.pack(fill="x")
        ttk.Button(row, text="Print", command=self.print_current).pack(
            side="right", padx=8, pady=6)
        ttk.Button(row, text="Close", command=win.destroy).pack(side="right", pady=6)

    def export_chat(self):
        if not self.need_chat():
            return
        path = filedialog.asksaveasfilename(
            parent=self.top, title="Save chat history", defaultextension=".txt",
            initialfile=f"{self.current}_history",
            filetypes=[("Text file", "*.txt"), ("CSV file", "*.csv"),
                       ("JSON file", "*.json")])
        if not path:
            return
        rows = [(to_local(ts).strftime("%Y-%m-%d %H:%M:%S"),
                 "out" if s == self.me else "in", b)
                for ts, s, b in self.db_messages(self.current)]
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext == ".csv":
                with open(path, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.writer(f)
                    w.writerow(["contact", "direction", "timestamp", "text"])
                    for ts, d, b in rows:
                        w.writerow([self.current, d, ts, b])
            elif ext == ".json":
                with open(path, "w", encoding="utf-8") as f:
                    json.dump([{"contact": self.current, "direction": d,
                                "timestamp": ts, "text": b} for ts, d, b in rows],
                              f, indent=2, ensure_ascii=False)
            else:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.chat_text(self.current))
            self.status.config(text=f"Saved: {path}")
        except OSError as ex:
            messagebox.showerror("Save", f"File save nahi ho saki:\n{ex}", parent=self.top)

    def import_history(self):
        path = filedialog.askopenfilename(
            parent=self.top, title="Import history",
            filetypes=[("JSON / CSV", "*.json *.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            if path.lower().endswith(".json"):
                with open(path, encoding="utf-8") as f:
                    items = json.load(f)
            else:
                with open(path, newline="", encoding="utf-8-sig") as f:
                    items = list(csv.DictReader(f))
            count = 0
            conn = sqlite3.connect(self.db_path, timeout=30)
            try:
                for it in items:
                    peer, text = it["contact"], it["text"]
                    out = str(it.get("direction", "out")).lower().startswith("o")
                    try:     # export local time mein hota hai, DB UTC mein
                        utc = datetime.strptime(it["timestamp"], "%Y-%m-%d %H:%M:%S") \
                            .astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    except (KeyError, ValueError, TypeError):
                        utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    conn.execute(
                        "INSERT OR IGNORE INTO messages "
                        "(sender, receiver, message, msg_uid, timestamp) "
                        "VALUES (?,?,?,?,?)",
                        (self.me if out else peer, peer if out else self.me,
                         text, uuid.uuid4().hex, utc))
                    count += 1
                conn.commit()
            finally:
                conn.close()
        except Exception as ex:
            messagebox.showerror("Import", f"Import fail hua:\n{ex}", parent=self.top)
            return
        self.load_contacts(self.current)
        messagebox.showinfo("Import", f"{count} message(s) import ho gaye.", parent=self.top)

    def delete_chat(self):
        if not self.need_chat():
            return
        if messagebox.askyesno(
                "Delete history",
                f"'{self.current}' ke saath poori history delete karni hai?\n"
                "Yeh wapas nahi aa sakti.", icon="warning", parent=self.top):
            self.db_delete(self.current)
            self.current = None
            self.load_contacts()