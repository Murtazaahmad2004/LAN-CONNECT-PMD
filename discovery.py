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
        
        #while loop say lay kr end tak code likhna ha