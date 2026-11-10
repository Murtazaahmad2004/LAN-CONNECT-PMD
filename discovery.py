import socket
import json
import threading
import uuid
import time

import netconfig

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

        # Where our packets are sent and which network tag we use.
        # home.py sets both from Settings -> Network (see set_broadcasts).
        self.targets = [netconfig.GLOBAL_BROADCAST]
        self.network_tag = ""
        self._send_errors = {}

    def set_broadcasts(self, targets, tag=""):
        """Sets the broadcast addresses we send to and the network tag.

        targets: list of IPv4 broadcast addresses. Invalid ones are skipped;
                 an empty list means the network-wide broadcast.
        tag:     "" = no tagging. Otherwise only computers that use the same
                 tag are shown (and see us).
        """
        clean = []
        for item in targets or []:
            try:
                address = netconfig.parse_broadcast(str(item))
            except ValueError:
                continue
            if address not in clean:
                clean.append(address)

        if not clean:
            clean = [netconfig.GLOBAL_BROADCAST]

        try:
            new_tag = netconfig.clean_tag(tag)
        except ValueError:
            new_tag = ""

        tag_changed = new_tag != self.network_tag

        self.targets = clean
        self.network_tag = new_tag
        self._send_errors = {}

        if tag_changed:
            # Computers seen under the old tag must not stay in the list
            with self.lock:
                self.users.clear()
            self._notify_update()

        # Tell the other computers now, not at the next heartbeat
        if self.running:
            self._broadcast_once()

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
        if status not in ("Online", "Busy", "Inactive", "Offline"):
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
            "roster": self.roster,
            "tag": self.network_tag
        }

    def _send_packet(self, sock):
        """Sends our packet to every broadcast address. One address that
        fails (e.g. no route) does not stop the others."""
        data = json.dumps(self._make_packet()).encode("utf-8")

        for address in list(self.targets):
            try:
                sock.sendto(data, (address, DISCOVERY_PORT))
                self._send_errors.pop(address, None)
            except OSError as error:
                if not self.running:
                    continue

                # Print each problem once, not every few seconds
                if self._send_errors.get(address) != str(error):
                    self._send_errors[address] = str(error)
                    print(f"Broadcast error ({address}):", error)

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

            self._send_packet(sock)
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
                self._send_packet(sock)
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

                    # Only computers with the same network tag see each other
                    packet_tag = packet.get("tag", "")
                    if not isinstance(packet_tag, str):
                        packet_tag = ""
                    if packet_tag != self.network_tag:
                        continue

                    if (
                        not isinstance(port, int)
                        or not 1 <= port <= 65535
                    ):
                        continue

                    if status not in (
                        "Online",
                        "Busy",
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