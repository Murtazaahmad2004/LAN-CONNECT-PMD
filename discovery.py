import socket
import json
import threading
import uuid
import time

DISCOVERY_PORT = 37020
CHAT_PORT = 37021

BROADCAST_INTERVAL = 3
USER_TIMEOUT = 10
ROSTER_LIMIT = 30

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
        self._last_timeout_check = 0

        self.roster = []

    def set_roster(self, names):
        self.roster = [
            name for name in names
            if isinstance(name, str) and 0 < len(name) <= 60
        ][:ROSTER_LIMIT]

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

            # Tell the other computers immediately, not at the next heartbeat
            if self.running:
                self._broadcast_once()

    def stop(self):
        if not self.running:
            return

        # Tell the other computers we are Offline. UDP can drop packets,
        # so send it a few times.
        self.status = "Offline"
        for _ in range(3):
            self._broadcast_once()
            time.sleep(0.1)

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
            "status": self.status,
            "roster": self.roster
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
                # Check for silent computers (crashed / unplugged) every
                # second, even when other computers keep sending packets.
                now_check = time.time()
                if now_check - self._last_timeout_check >= 1:
                    self._last_timeout_check = now_check
                    self._check_timeouts()

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

                            # The real entry replaces the shared placeholder
                            self.users.pop("roster:" + username, None)

                            # Same person restarted: drop the old Offline entry
                            for old_id in [
                                key for key, old in self.users.items()
                                if old["username"] == username
                                and key != instance_id
                                and old["status"] == "Offline"
                            ]:
                                del self.users[old_id]

                        # Learn Offline users that other computers know
                        roster = packet.get("roster", [])

                        if isinstance(roster, list):
                            known_names = {
                                u["username"] for u in self.users.values()
                            }
                            known_names.add(self.username)

                            for name in roster[:ROSTER_LIMIT]:
                                if (
                                    isinstance(name, str)
                                    and 0 < len(name) <= 60
                                    and name not in known_names
                                ):
                                    known_names.add(name)
                                    self.users["roster:" + name] = {
                                        "instance_id": "roster:" + name,
                                        "username": name,
                                        "ip": "",
                                        "port": CHAT_PORT,
                                        "last_seen": 0,
                                        "status": "Offline"
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