import json
import os
import socket
import uuid

import filestore

CHUNK = 64 * 1024
MAX_SIZE = 20 * 1024 ** 3        # 20 GB
ASK_TIMEOUT = 120                # seconds the receiver may take to answer
IO_TIMEOUT = 30                  # seconds without any data = connection lost


def human_size(size):
    size = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def _read_line(sock, limit=64):
    data = b""
    while not data.endswith(b"\n"):
        chunk = sock.recv(1)
        if not chunk:
            break
        data += chunk
        if len(data) > limit:
            break
    return data.strip().decode("ascii", "replace")


# ------------------------------------------------------------------ sending
def send_file(ip, ports, sender, receiver, path, tracker=None):
    """Sends one file.  Returns (status, detail, transfer_id).

    status: "sent" | "declined" | "skipped" | "cancelled" | "offline" | "error"
    """
    transfer_id = uuid.uuid4().hex

    try:
        size = os.path.getsize(path)
    except OSError as error:
        return "error", f"Cannot read the file: {error}", transfer_id

    if not os.path.isfile(path):
        return "error", "This is not a file.", transfer_id
    if size > MAX_SIZE:
        return "error", f"File is too big (limit {human_size(MAX_SIZE)}).", \
            transfer_id

    header = json.dumps({
        "type": "file", "id": transfer_id, "from": sender, "to": receiver,
        "name": os.path.basename(path), "size": size,
    }).encode("utf-8") + b"\n"

    last_error = "Could not connect to the other computer."

    for port in ports:
        try:
            sock = socket.create_connection((ip, port), timeout=3)
        except ConnectionRefusedError:
            continue
        except OSError as error:
            return "offline", str(error), transfer_id

        with sock:
            try:
                sock.sendall(header)
                sock.settimeout(ASK_TIMEOUT + 10)   # user may be deciding
                reply = _read_line(sock)

                if reply == "NO":
                    continue                        # another copy owns this port
                if reply == "DECLINED":
                    return "declined", "", transfer_id
                if reply == "SKIPPED":
                    return "skipped", "", transfer_id
                if reply != "OK":
                    return "error", "The other computer did not accept " \
                        "the file.", transfer_id

                sock.settimeout(IO_TIMEOUT)
                sent = 0
                with open(path, "rb") as source:
                    while True:
                        if tracker is not None and tracker.cancelled:
                            return "cancelled", "", transfer_id
                        block = source.read(CHUNK)
                        if not block:
                            break
                        sock.sendall(block)
                        sent += len(block)
                        if tracker is not None:
                            tracker.update(sent, size)

                if sent != size:
                    return "error", "The file changed while sending.", \
                        transfer_id

                sock.settimeout(ASK_TIMEOUT)
                if _read_line(sock) == "DONE":
                    return "sent", "", transfer_id
                return "error", "The other computer could not save the file.", \
                    transfer_id

            except (OSError, ValueError) as error:
                last_error = f"Connection problem: {error}"
                return "error", last_error, transfer_id

    return "offline", last_error, transfer_id


# ---------------------------------------------------------------- receiving
def receive_file(conn, header, leftover, decide, resolve, begin=None):
    """Handles one incoming file offer on an accepted connection.

    decide(sender, name, size) -> bool           True = accept (may ask the user)
    resolve(sender, name, create) -> path|None   where to save; None = skip
    begin(sender, name, size) -> tracker|None    progress window (optional)

    Returns a dict {"sender","name","size","path","id"} when a file was saved,
    otherwise None.
    """
    def reply(text):
        try:
            conn.sendall(text.encode("ascii") + b"\n")
        except OSError:
            pass

    sender = str(header.get("from", "")).strip()
    name = filestore.safe_name(header.get("name"))
    size = header.get("size")

    if (not sender or isinstance(size, bool) or not isinstance(size, int)
            or not 0 <= size <= MAX_SIZE):
        reply("NO")
        return None

    # "If file already exists: Skip" is answered before the user is asked
    if resolve(sender, name, False) is None:
        reply("SKIPPED")
        return None

    if not decide(sender, name, size):
        reply("DECLINED")
        return None

    path = resolve(sender, name, True)
    if path is None:
        reply("SKIPPED")
        return None

    part = path + ".part"
    tracker = begin(sender, name, size) if begin else None
    received = 0
    ok = False

    try:
        conn.settimeout(IO_TIMEOUT)
        reply("OK")

        with open(part, "wb") as target:
            if leftover:
                piece = leftover[:size]
                target.write(piece)
                received += len(piece)

            while received < size:
                if tracker is not None and tracker.cancelled:
                    break
                block = conn.recv(min(CHUNK, size - received))
                if not block:
                    break
                target.write(block)
                received += len(block)
                if tracker is not None:
                    tracker.update(received, size)

        if received == size:
            os.replace(part, path)
            ok = True
    except OSError as error:
        print("[FILE] Receive error:", error)
    finally:
        if not ok:
            try:
                os.remove(part)
            except OSError:
                pass
        if tracker is not None:
            tracker.close()

    reply("DONE" if ok else "FAIL")

    if not ok:
        return None
    return {"sender": sender, "name": os.path.basename(path), "size": size,
            "path": path, "id": str(header.get("id", ""))}