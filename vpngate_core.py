#!/usr/bin/env python3
import json
import requests
import base64
import subprocess
import os
import re
import time

API_URL_VPNGATE = "https://www.vpngate.net/api/iphone/"
API_URL_OVPNPW = "https://api.ovpn.pw/csv"
CONNECTION_NAME = "vpngate-active"
PID_FILE = "/tmp/vpngate-gtk.pid"
CONFIG_PATH = os.path.expanduser("~/.config/vpngate-gtk/config.json")

api_source = "vpngate"
minimize_on_close = False


def _load_config():
    global api_source, minimize_on_close
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
            api_source = cfg.get("api_source", "vpngate")
            minimize_on_close = cfg.get("minimize_on_close", False)
    except FileNotFoundError:
        pass


def _save_config():
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, 'w') as f:
        json.dump({"api_source": api_source, "minimize_on_close": minimize_on_close}, f)


def set_api_source(name):
    global api_source
    api_source = name
    _save_config()


def get_api_source():
    return api_source


def get_api_source_label():
    return {
        "vpngate": "VPN Gate (recommended)",
        "ovpnpw": "api.ovpn.pw (fallback)",
    }.get(api_source, "Unknown")


def get_minimize_on_close():
    return minimize_on_close


def set_minimize_on_close(value):
    global minimize_on_close
    minimize_on_close = value
    _save_config()


_load_config()


def get_servers():
    if api_source == "ovpnpw":
        return _get_servers_ovpnpw()
    return _get_servers_vpngate()


def _get_servers_vpngate():
    try:
        response = requests.get(API_URL_VPNGATE, timeout=10)
        response.raise_for_status()
        lines = response.text.splitlines()
        if len(lines) < 2:
            return []

        header = lines[1][1:].split(",")
        servers = []
        for line in lines[2:]:
            if line.startswith("*") or line.startswith("#") or not line.strip():
                continue
            parts = line.split(",")
            if len(parts) < 15:
                continue
            server = dict(zip(header, parts))

            try:
                config_data = base64.b64decode(server['OpenVPN_ConfigData_Base64']).decode('utf-8', errors='ignore')
                server['has_udp'] = "proto udp" in config_data.lower()
                server['has_tcp'] = "proto tcp" in config_data.lower() or "proto udp" not in config_data.lower()
                server['config_text'] = config_data
                servers.append(server)
            except:
                continue
        return servers
    except Exception as e:
        print(f"Error fetching servers from VPN Gate: {e}")
        return []


def _get_servers_ovpnpw():
    try:
        response = requests.get(API_URL_OVPNPW, timeout=10)
        response.raise_for_status()
        lines = response.text.splitlines()
        if len(lines) < 2:
            return []

        header = lines[0][1:].split(",")
        servers = []
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) < 15:
                continue
            server = dict(zip(header, parts))

            try:
                config_data = base64.b64decode(server['OpenVPN_ConfigData_Base64']).decode('utf-8', errors='ignore')
                server['has_udp'] = "proto udp" in config_data.lower()
                server['has_tcp'] = "proto tcp" in config_data.lower() or "proto udp" not in config_data.lower()
                server['config_text'] = config_data
                servers.append(server)
            except:
                continue
        return servers
    except Exception as e:
        print(f"Error fetching servers from api.ovpn.pw: {e}")
        return []


def is_active():
    res = subprocess.run(["nmcli", "-t", "-f", "NAME,STATE", "connection", "show", "--active"], capture_output=True, text=True)
    return CONNECTION_NAME in res.stdout


def get_stats():
    if not is_active():
        return None

    res = subprocess.run(["nmcli", "-t", "-f", "NAME,DEVICE", "connection", "show", "--active"], capture_output=True, text=True)
    device = None
    for line in res.stdout.splitlines():
        if line.startswith(CONNECTION_NAME):
            device = line.split(":")[1]
            break

    if not device:
        return None

    def get_bytes():
        try:
            with open("/proc/net/dev", "r") as f:
                for line in f:
                    if device in line:
                        parts = line.split()
                        return int(parts[1]), int(parts[9])
        except:
            pass
        return 0, 0

    b1_rx, b1_tx = get_bytes()
    time.sleep(1)
    b2_rx, b2_tx = get_bytes()

    down_speed = (b2_rx - b1_rx) / 1024
    up_speed = (b2_tx - b1_tx) / 1024

    ping_res = subprocess.run(["ping", "-c", "3", "-W", "2", "8.8.8.8"], capture_output=True, text=True)
    ping_val = "N/A"
    loss_val = "100%"

    if ping_res.returncode == 0:
        loss_match = re.search(r"(\d+)% packet loss", ping_res.stdout)
        if loss_match:
            loss_val = loss_match.group(1) + "%"

        avg_match = re.search(r"avg/max/mdev = [\d\.]+/([\d\.]+)/", ping_res.stdout)
        if avg_match:
            ping_val = avg_match.group(1) + " ms"

    return up_speed, down_speed, ping_val, loss_val


def connect_vpn(server, force_proto=None):
    if is_active():
        return False, "Error: A VPN connection is already active. Stop it first."

    config_data = server['config_text']

    if force_proto == "tcp" and "proto tcp" in config_data.lower() and "proto udp" in config_data.lower():
        config_data = re.sub(r"^proto udp", ";proto udp", config_data, flags=re.MULTILINE | re.IGNORECASE)
        config_data = re.sub(r"^[; \t]*proto tcp", "proto tcp", config_data, flags=re.MULTILINE | re.IGNORECASE)
    elif force_proto == "udp" and "proto udp" in config_data.lower() and "proto tcp" in config_data.lower():
        config_data = re.sub(r"^proto tcp", ";proto tcp", config_data, flags=re.MULTILINE | re.IGNORECASE)
        config_data = re.sub(r"^[; \t]*proto udp", "proto udp", config_data, flags=re.MULTILINE | re.IGNORECASE)

    temp_ovpn = "/tmp/vpngate-active.ovpn"
    with open(temp_ovpn, 'w') as f:
        f.write(config_data)

    subprocess.run(["nmcli", "connection", "delete", CONNECTION_NAME], capture_output=True)

    import_res = subprocess.run(["nmcli", "connection", "import", "type", "openvpn", "file", temp_ovpn], capture_output=True, text=True)

    if import_res.returncode != 0:
        return False, f"Failed to import: {import_res.stderr}"

    remote_match = re.search(r"^remote\s+([\d\.]+)\s+(\d+)", config_data, re.MULTILINE)
    remote_ip = remote_match.group(1) if remote_match else server['IP']
    remote_port = remote_match.group(2) if remote_match else "443"

    subprocess.run(["nmcli", "connection", "modify", CONNECTION_NAME,
                    "vpn.user-name", "vpn",
                    "vpn.secrets", "password=vpn",
                    "+vpn.data", f"auth=SHA1, cipher=AES-128-CBC, data-ciphers=AES-256-GCM:AES-128-GCM:AES-128-CBC, data-ciphers-fallback=AES-128-CBC, connection-type=password, remote={remote_ip}, port={remote_port}"], capture_output=True)

    try:
        up_res = subprocess.run(["timeout", "20s", "nmcli", "connection", "up", CONNECTION_NAME], capture_output=True, text=True)

        if up_res.returncode == 0:
            with open(PID_FILE, "w") as f:
                f.write(str(os.getpid()))
            return True, "Successfully connected!"
        elif up_res.returncode == 124:
            subprocess.run(["nmcli", "connection", "delete", CONNECTION_NAME], capture_output=True)
            return False, "Connection timed out (>20s)."
        else:
            subprocess.run(["nmcli", "connection", "delete", CONNECTION_NAME], capture_output=True)
            return False, f"Connection failed: {up_res.stderr}"
    except Exception as e:
        subprocess.run(["nmcli", "connection", "delete", CONNECTION_NAME], capture_output=True)
        return False, str(e)
    finally:
        if os.path.exists(temp_ovpn):
            os.remove(temp_ovpn)


def disconnect_vpn():
    if not is_active():
        subprocess.run(["nmcli", "connection", "delete", CONNECTION_NAME], capture_output=True)
        return False, "No active VPN connection found."

    subprocess.run(["nmcli", "connection", "down", CONNECTION_NAME], capture_output=True)
    subprocess.run(["nmcli", "connection", "delete", CONNECTION_NAME], capture_output=True)
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
    return True, "VPN disconnected."
