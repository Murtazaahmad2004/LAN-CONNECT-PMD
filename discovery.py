import socket
import json
import threading
import time
import uuid

DISCOVERY_PORT = 37020
CHAT_PORT = 37021
BROADCAST_INTERVAL = 3
USER_TIMEOUT = 10

INSTANCE_ID = str(uuid.uuid4())

def get_local_ip():
    """Local Ips find active network interface."""
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
        self.users = {}
        self.lock = threading.Lock()
        
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
        
    def stop(self):
        self.running = False
        
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
                packet = {
                    "type": "discovery",
                    "instance_id": INSTANCE_ID,
                    "username": self.username,
                    "port": CHAT_PORT
                }

                try:
                    sock.sendto(
                        json.dumps(packet).encode("utf-8"),
                        ("255.255.255.255", DISCOVERY_PORT)
                    )
                except OSError as error:
                    print("Broadcast error:", error)

                time.sleep(BROADCAST_INTERVAL)
        finally:
            sock.close()

    def _listen_loop(self):
        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM
        )

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
                    self._remove_offline_users()
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

                    if not instance_id or not username:
                        continue

                    if instance_id == INSTANCE_ID:
                        continue

                    if not isinstance(port, int) or not 1 <= port <= 65535:
                        continue

                    now = time.time()

                    with self.lock:
                        self.users[instance_id] = {
                            "instance_id": instance_id,
                            "username": username,
                            "ip": address[0],
                            "port": port,
                            "last_seen": now
                        }

                    self._notify_update()

                except (ValueError, UnicodeDecodeError, TypeError):
                    continue
        finally:
            sock.close()

    def _remove_offline_users(self):
        now = time.time()
        changed = False

        with self.lock:
            offline_ids = [
                user_id
                for user_id, user in self.users.items()
                if now - user["last_seen"] > USER_TIMEOUT
            ]

            for user_id in offline_ids:
                del self.users[user_id]
                changed = True

        if changed:
            self._notify_update()

    def _notify_update(self):
        if self.on_update:
            self.on_update(self.get_users())

    def get_users(self):
        with self.lock:
            return [user.copy() for user in self.users.values()]