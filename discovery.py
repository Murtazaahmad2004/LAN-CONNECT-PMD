
import socket
import json
import threading
import uuid
import time

DISCOVERY_PORT = 37020
CHAT_PORT = 37021

BROADCAST_INTERVAL = 3
USER_TIMEOUT = 10

INSTANCE_ID = str(uuid.uuid4())


def get_local_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        sock.connect(("192.0.2.1", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


class LANDiscovery:
    def __init__(self, username, on_update=None):
        self.username = username
        self.on_update = on_update
        self.local_ip = get_local_ip()

        self.running = False
        self.status = "Online"

        self.users = {}
        self.lock = threading.Lock()
        self.socket = None

    def start(self):
        if self.running:
            return

        self.running = True

        threading.Thread(
            target=self._broadcast_loop,
            daemon=True
        ).start()

        threading.Thread(
            target=self._listen_loop,
            daemon=True
        ).start()

    def set_status(self, status):
        if status not in ("Online", "Inactive", "Offline"):
            return

        if self.status != status:
            self.status = status

    def stop(self):
        if not self.running:
            return

        # Baqi computers ko Offline status bhejein.
        self.status = "Offline"
        self._broadcast_once()

        self.running = False

        if self.socket:
            try:
                self.socket.close()
            except OSError:
                pass

    def _make_packet(self):
        return {
            "type": "discovery",
            "instance_id": INSTANCE_ID,
            "username": self.username,
            "port": CHAT_PORT,
            "status": self.status
        }

    def _broadcast_once(self):
        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM
        )

        try:
            sock.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_BROADCAST,
                1
            )

            sock.sendto(
                json.dumps(self._make_packet()).encode("utf-8"),
                ("255.255.255.255", DISCOVERY_PORT)
            )
        except OSError as error:
            print("Broadcast error:", error)
        finally:
            sock.close()

    def _broadcast_loop(self):
        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM
        )

        sock.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_BROADCAST,
            1
        )

        try:
            while self.running:
                try:
                    sock.sendto(
                        json.dumps(self._make_packet()).encode("utf-8"),
                        ("255.255.255.255", DISCOVERY_PORT)
                    )
                except OSError as error:
                    if self.running:
                        print("Broadcast error:", error)

                time.sleep(BROADCAST_INTERVAL)
        finally:
            sock.close()

    def _listen_loop(self):
        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM
        )

        self.socket = sock

        sock.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1
        )

        try:
            sock.bind(("", DISCOVERY_PORT))
            sock.settimeout(1)

            while self.running:
                try:
                    data, address = sock.recvfrom(4096)
                except socket.timeout:
                    self._check_timeouts()
                    continue
                except OSError:
                    break

                try:
                    packet = json.loads(data.decode("utf-8"))

                    if packet.get("type") != "discovery":
                        continue

                    instance_id = packet.get("instance_id")
                    username = packet.get("username")
                    port = packet.get("port")
                    status = packet.get("status", "Online")

                    if not instance_id or not username:
                        continue

                    if instance_id == INSTANCE_ID:
                        continue

                    if (
                        not isinstance(port, int)
                        or not 1 <= port <= 65535
                    ):
                        continue

                    if status not in (
                        "Online",
                        "Inactive",
                        "Offline"
                    ):
                        status = "Online"

                    now = time.time()

                    with self.lock:
                        if status == "Offline":
                            if instance_id in self.users:
                                self.users[instance_id]["status"] = "Offline"
                                self.users[instance_id]["last_seen"] = now
                        else:
                            self.users[instance_id] = {
                                "instance_id": instance_id,
                                "username": username,
                                "ip": address[0],
                                "port": port,
                                "last_seen": now,
                                "status": status
                            }

                    self._notify_update()

                except (
                    ValueError,
                    UnicodeDecodeError,
                    TypeError
                ):
                    continue

        finally:
            sock.close()

    def _check_timeouts(self):
        now = time.time()
        changed = False

        with self.lock:
            for user in self.users.values():
                if (
                    user["status"] != "Offline"
                    and now - user["last_seen"] > USER_TIMEOUT
                ):
                    user["status"] = "Offline"
                    changed = True

        if changed:
            self._notify_update()

    def _notify_update(self):
        if self.on_update:
            self.on_update(self.get_users())

    def get_users(self):
        with self.lock:
            return [
                user.copy()
                for user in self.users.values()
            ]