import ipaddress
import json
import os
import socket
import sys

GLOBAL_BROADCAST = "255.255.255.255"
MAX_TAG_LENGTH = 32
FILE_VERSION = 1

_FILE_KEYS = ("broadcasts", "include_system", "include_global",
              "tag_enabled", "tag", "network_tag")


def _data_path(filename):
    if getattr(sys, "frozen", False):
        folder = os.path.dirname(sys.executable)
    else:
        folder = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(folder, filename)


CONFIG_FILE = _data_path("network_settings.json")


# ---------------------------------------------------------------- validation
def parse_broadcast(text):
    """'192.168.1.255' or '192.168.1.0/24'  ->  broadcast address text.

    Raises ValueError with a message that can be shown to the user.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("Please enter an address.")

    network = None
    try:
        if "/" in text:
            network = ipaddress.IPv4Network(text, strict=False)
        else:
            address = ipaddress.IPv4Address(text)
    except ValueError:
        raise ValueError(
            f"'{text}' is not valid.\n\n"
            "Enter an IPv4 broadcast address (for example 192.168.1.255)\n"
            "or a subnet (for example 192.168.1.0/24)."
        ) from None

    if network is not None:
        if network.prefixlen >= 31:
            raise ValueError(
                "That subnet is too small.\n"
                "Use a subnet such as 192.168.1.0/24."
            )
        address = network.broadcast_address

    if address.is_unspecified or address.is_loopback or address.is_multicast:
        raise ValueError("That address cannot be used as a broadcast.")

    return str(address)


def clean_tag(text):
    """Trims the tag. Raises ValueError if it is too long."""
    tag = " ".join(str(text or "").split())
    if len(tag) > MAX_TAG_LENGTH:
        raise ValueError(f"The tag can have at most {MAX_TAG_LENGTH} characters.")
    return tag


def _clean_list(items):
    result = []
    if not isinstance(items, (list, tuple)):
        return result
    for item in items:
        try:
            address = parse_broadcast(str(item))
        except ValueError:
            continue
        if address not in result:
            result.append(address)
    return result


def default_config():
    return {
        "mode": "system",
        "file": "",
        "broadcasts": [],
        "include_system": True,
        "include_global": True,
        "tag_enabled": False,
        "tag": "",
    }


def _normalize(raw):
    """Any dict -> a complete, safe config dict."""
    cfg = default_config()
    if not isinstance(raw, dict):
        return cfg

    cfg["mode"] = raw.get("mode") if raw.get("mode") in ("system", "file") else "system"
    cfg["file"] = str(raw.get("file") or "")
    cfg["broadcasts"] = _clean_list(raw.get("broadcasts"))
    cfg["include_system"] = bool(raw.get("include_system", True))
    cfg["include_global"] = bool(raw.get("include_global", True))

    try:
        tag = clean_tag(raw.get("tag", raw.get("network_tag", "")))
    except ValueError:
        tag = ""
    cfg["tag"] = tag
    cfg["tag_enabled"] = bool(tag) and bool(raw.get("tag_enabled", True))
    return cfg


# ---------------------------------------------------------- load / save / file
def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
            return _normalize(json.load(fh))
    except (OSError, ValueError):
        return default_config()


def save_config(cfg):
    """Saves the app's network settings. Raises OSError if it cannot write."""
    cfg = _normalize(cfg)
    temp = CONFIG_FILE + ".tmp"
    with open(temp, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    os.replace(temp, CONFIG_FILE)


def read_settings_file(path):
    """Reads a network settings file. Raises ValueError (message for the user)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except OSError as exc:
        raise ValueError(f"Could not read the file:\n{exc.strerror or exc}") from None
    except ValueError:
        raise ValueError("This is not a valid network settings file.") from None

    if not isinstance(raw, dict) or not any(key in raw for key in _FILE_KEYS):
        raise ValueError("This is not a valid network settings file.")

    cfg = _normalize(raw)
    cfg["mode"] = "system"
    cfg["file"] = ""
    return cfg


def export_settings_file(path, cfg):
    """Writes the settings to a file others can load. Raises OSError."""
    cfg = _normalize(cfg)
    data = {
        "version": FILE_VERSION,
        "broadcasts": cfg["broadcasts"],
        "include_system": cfg["include_system"],
        "include_global": cfg["include_global"],
        "tag_enabled": cfg["tag_enabled"],
        "tag": cfg["tag"],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


# ------------------------------------------------------------ system broadcasts
def _guess_local_ips():
    ips = []
    try:
        ips.extend(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass

    probe = None
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))      # nothing is sent; just picks the adapter
        ips.append(probe.getsockname()[0])
    except OSError:
        pass
    finally:
        if probe is not None:
            probe.close()
    return ips


def _interfaces():
    """[(ip, netmask), ...]  psutil gives exact masks; otherwise /24 is assumed."""
    pairs = []
    try:
        import psutil
        for addresses in psutil.net_if_addrs().values():
            for item in addresses:
                if item.family == socket.AF_INET and item.address and item.netmask:
                    pairs.append((item.address, item.netmask))
    except Exception:
        pairs = []

    if not pairs:
        pairs = [(ip, "255.255.255.0") for ip in _guess_local_ips()]
    return pairs


def system_broadcasts():
    """Broadcast addresses calculated from this computer's network adapters."""
    found = []
    for ip, mask in _interfaces():
        try:
            interface = ipaddress.IPv4Interface(f"{ip}/{mask}")
        except ValueError:
            continue

        address = interface.ip
        if address.is_loopback or address.is_link_local or address.is_unspecified:
            continue
        if interface.network.prefixlen >= 31:
            continue

        broadcast = str(interface.network.broadcast_address)
        if broadcast not in found:
            found.append(broadcast)
    return found


# ---------------------------------------------------------- what is in force
def effective_config(cfg=None):
    """The settings actually used.  In "file" mode the file wins; if the file
    cannot be read the app's own saved settings are used instead."""
    cfg = _normalize(cfg) if cfg is not None else load_config()

    if cfg["mode"] == "file" and cfg["file"]:
        try:
            return read_settings_file(cfg["file"])
        except ValueError as exc:
            print("[NETWORK] Settings file not used:", str(exc).replace("\n", " "))
    return cfg


def get_send_targets(cfg=None):
    """Broadcast addresses to send discovery packets to (no duplicates)."""
    eff = effective_config(cfg)
    targets = []

    def add(address):
        if address not in targets:
            targets.append(address)

    for address in eff["broadcasts"]:
        add(address)
    if eff["include_system"]:
        for address in system_broadcasts():
            add(address)
    if eff["include_global"]:
        add(GLOBAL_BROADCAST)

    return targets or [GLOBAL_BROADCAST]     # never leave the app deaf


def get_network_tag(cfg=None):
    """'' when tagging is off, otherwise the tag text."""
    eff = effective_config(cfg)
    return eff["tag"] if eff["tag_enabled"] else ""