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
IPV6_STATE_FILE = "/tmp/vpngate-gtk-ipv6-state.json"
CONFIG_PATH = os.path.expanduser("~/.config/vpngate-gtk/config.json")

_connect_process = None
_connect_cancelled = False

# Default settings
api_source = "vpngate"
minimize_on_close = False
filter_country = None
filter_region = None
sort_key = "score"
protocol = "all"
ipv6_mode = "block_while_connected"  # block_while_connected | dont_block


def _load_config():
    global \
        api_source, \
        minimize_on_close, \
        filter_country, \
        filter_region, \
        sort_key, \
        protocol, \
        ipv6_mode
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
            api_source = cfg.get("api_source", "vpngate")
            minimize_on_close = cfg.get("minimize_on_close", False)
            filter_country = cfg.get("filter_country", None)
            filter_region = cfg.get("filter_region", None)
            sort_key = cfg.get("sort_key", "score")
            protocol = cfg.get("protocol", "all")
            ipv6_mode = cfg.get("ipv6_mode", "block_while_connected")
    except (FileNotFoundError, json.JSONDecodeError):
        pass


def _save_config():
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(
                {
                    "api_source": api_source,
                    "minimize_on_close": minimize_on_close,
                    "filter_country": filter_country,
                    "filter_region": filter_region,
                    "sort_key": sort_key,
                    "protocol": protocol,
                    "ipv6_mode": ipv6_mode,
                },
                f,
                indent=2,
            )
    except Exception as e:
        print(f"Error saving configuration: {e}")


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


def get_filter_country():
    return filter_country


def set_filter_country(value):
    global filter_country
    filter_country = value
    _save_config()


def get_filter_region():
    return filter_region


def set_filter_region(value):
    global filter_region
    filter_region = value
    _save_config()


def get_sort_key():
    return sort_key


def set_sort_key(value):
    global sort_key
    sort_key = value
    _save_config()


def get_protocol():
    return protocol


def set_protocol(value):
    global protocol
    protocol = value
    _save_config()


def get_ipv6_mode():
    return ipv6_mode


def set_ipv6_mode(value):
    global ipv6_mode
    ipv6_mode = value
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
                config_data = base64.b64decode(
                    server["OpenVPN_ConfigData_Base64"]
                ).decode("utf-8", errors="ignore")
                server["has_udp"] = "proto udp" in config_data.lower()
                server["has_tcp"] = (
                    "proto tcp" in config_data.lower()
                    or "proto udp" not in config_data.lower()
                )
                server["config_text"] = config_data
                servers.append(server)
            except Exception:
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
                config_data = base64.b64decode(
                    server["OpenVPN_ConfigData_Base64"]
                ).decode("utf-8", errors="ignore")
                server["has_udp"] = "proto udp" in config_data.lower()
                server["has_tcp"] = (
                    "proto tcp" in config_data.lower()
                    or "proto udp" not in config_data.lower()
                )
                server["config_text"] = config_data
                servers.append(server)
            except Exception:
                continue
        return servers
    except Exception as e:
        print(f"Error fetching servers from api.ovpn.pw: {e}")
        return []


def is_active():
    res = subprocess.run(
        ["nmcli", "-t", "-f", "NAME,STATE", "connection", "show", "--active"],
        capture_output=True,
        text=True,
    )
    return CONNECTION_NAME in res.stdout


def get_stats():
    if not is_active():
        return None

    res = subprocess.run(
        ["nmcli", "-t", "-f", "NAME,DEVICE", "connection", "show", "--active"],
        capture_output=True,
        text=True,
    )
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
        except Exception:
            pass
        return 0, 0

    b1_rx, b1_tx = get_bytes()
    time.sleep(1)
    b2_rx, b2_tx = get_bytes()

    down_speed = (b2_rx - b1_rx) / 1024
    up_speed = (b2_tx - b1_tx) / 1024

    ping_res = subprocess.run(
        ["ping", "-c", "3", "-W", "2", "8.8.8.8"], capture_output=True, text=True
    )
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


def _get_main_connection():
    res = subprocess.run(
        ["nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active"],
        capture_output=True,
        text=True,
    )
    for line in res.stdout.splitlines():
        parts = line.split(":")
        if len(parts) >= 3 and parts[0] != CONNECTION_NAME:
            if parts[1] in ("802-3-ethernet", "802-11-wireless"):
                return parts[0]
    return None


def _get_ipv6_method(connection_name):
    res = subprocess.run(
        ["nmcli", "-t", "-f", "ipv6.method", "connection", "show", connection_name],
        capture_output=True,
        text=True,
    )
    for line in res.stdout.splitlines():
        if line.startswith("ipv6.method:"):
            return line.split(":", 1)[1].strip()
    return None


def _save_ipv6_state(connection_name, ipv6_method):
    try:
        with open(IPV6_STATE_FILE, "w") as f:
            json.dump({"connection": connection_name, "ipv6_method": ipv6_method}, f)
    except Exception:
        pass


def _load_ipv6_state():
    try:
        with open(IPV6_STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _clear_ipv6_state():
    try:
        os.remove(IPV6_STATE_FILE)
    except FileNotFoundError:
        pass


def _disable_ipv6_on_main():
    main_conn = _get_main_connection()
    if not main_conn:
        return False
    ipv6_method = _get_ipv6_method(main_conn)
    if not ipv6_method or ipv6_method == "disabled":
        return False
    _save_ipv6_state(main_conn, ipv6_method)
    subprocess.run(
        ["nmcli", "connection", "modify", main_conn, "ipv6.method", "disabled"],
        capture_output=True,
    )
    subprocess.run(
        ["nmcli", "connection", "up", main_conn],
        capture_output=True,
    )
    return True


def _restore_ipv6_on_main():
    state = _load_ipv6_state()
    if not state:
        return
    conn = state.get("connection")
    method = state.get("ipv6_method")
    if conn and method:
        subprocess.run(
            ["nmcli", "connection", "modify", conn, "ipv6.method", method],
            capture_output=True,
        )
        subprocess.run(
            ["nmcli", "connection", "up", conn],
            capture_output=True,
        )
    _clear_ipv6_state()


def recover_ipv6_on_startup():
    if ipv6_mode == "block_while_connected" and os.path.exists(IPV6_STATE_FILE) and not is_active():
        _restore_ipv6_on_main()


recover_ipv6_on_startup()


def cancel_connect():
    global _connect_process, _connect_cancelled
    _connect_cancelled = True
    if _connect_process:
        _connect_process.terminate()


def connect_vpn(server, force_proto=None):
    global _connect_process, _connect_cancelled
    _connect_cancelled = False
    _connect_process = None

    if is_active():
        return False, "Error: A VPN connection is already active. Stop it first."

    config_data = server["config_text"]

    if (
        force_proto == "tcp"
        and "proto tcp" in config_data.lower()
        and "proto udp" in config_data.lower()
    ):
        config_data = re.sub(
            r"^proto udp", ";proto udp", config_data, flags=re.MULTILINE | re.IGNORECASE
        )
        config_data = re.sub(
            r"^[; \t]*proto tcp",
            "proto tcp",
            config_data,
            flags=re.MULTILINE | re.IGNORECASE,
        )
    elif (
        force_proto == "udp"
        and "proto udp" in config_data.lower()
        and "proto tcp" in config_data.lower()
    ):
        config_data = re.sub(
            r"^proto tcp", ";proto tcp", config_data, flags=re.MULTILINE | re.IGNORECASE
        )
        config_data = re.sub(
            r"^[; \t]*proto udp",
            "proto udp",
            config_data,
            flags=re.MULTILINE | re.IGNORECASE,
        )

    temp_ovpn = "/tmp/vpngate-active.ovpn"
    with open(temp_ovpn, "w") as f:
        f.write(config_data)

    subprocess.run(
        ["nmcli", "connection", "delete", CONNECTION_NAME], capture_output=True
    )

    import_res = subprocess.run(
        ["nmcli", "connection", "import", "type", "openvpn", "file", temp_ovpn],
        capture_output=True,
        text=True,
    )

    if import_res.returncode != 0:
        return False, f"Failed to import: {import_res.stderr}"

    remote_match = re.search(r"^remote\s+([\d\.]+)\s+(\d+)", config_data, re.MULTILINE)
    remote_ip = remote_match.group(1) if remote_match else server["IP"]
    remote_port = remote_match.group(2) if remote_match else "443"

    subprocess.run(
        [
            "nmcli",
            "connection",
            "modify",
            CONNECTION_NAME,
            "+vpn.data",
            f"auth=SHA1, cipher=AES-128-CBC, data-ciphers=AES-256-GCM:AES-128-GCM:AES-128-CBC, data-ciphers-fallback=AES-128-CBC, remote={remote_ip}, port={remote_port}",
        ],
        capture_output=True,
    )

    subprocess.run(
        [
            "nmcli",
            "connection",
            "modify",
            CONNECTION_NAME,
            "ipv6.method",
            "disabled",
        ],
        capture_output=True,
    )

    if _connect_cancelled:
        subprocess.run(
            ["nmcli", "connection", "delete", CONNECTION_NAME], capture_output=True
        )
        return False, "Connection cancelled."

    if ipv6_mode != "dont_block":
        _disable_ipv6_on_main()

    try:
        _connect_process = subprocess.Popen(
            ["timeout", "20s", "nmcli", "connection", "up", CONNECTION_NAME],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = _connect_process.communicate()
        retcode = _connect_process.returncode
        _connect_process = None

        if _connect_cancelled:
            subprocess.run(
                ["nmcli", "connection", "delete", CONNECTION_NAME], capture_output=True
            )
            if ipv6_mode == "block_while_connected":
                _restore_ipv6_on_main()
            return False, "Connection cancelled."

        if retcode == 0:
            with open(PID_FILE, "w") as f:
                f.write(str(os.getpid()))
            return True, "Successfully connected!"
        else:
            subprocess.run(
                ["nmcli", "connection", "delete", CONNECTION_NAME], capture_output=True
            )
            if ipv6_mode == "block_while_connected":
                _restore_ipv6_on_main()
            if retcode == 124:
                return False, "Connection timed out (>20s)."
            else:
                return False, f"Connection failed: {stderr}"
    except Exception as e:
        subprocess.run(
            ["nmcli", "connection", "delete", CONNECTION_NAME], capture_output=True
        )
        if ipv6_mode == "block_while_connected":
            _restore_ipv6_on_main()
        return False, str(e)
    finally:
        _connect_process = None
        if os.path.exists(temp_ovpn):
            os.remove(temp_ovpn)


def disconnect_vpn():
    if not is_active():
        subprocess.run(
            ["nmcli", "connection", "delete", CONNECTION_NAME], capture_output=True
        )
        if ipv6_mode == "block_while_connected":
            _restore_ipv6_on_main()
        return False, "No active VPN connection found."

    subprocess.run(
        ["nmcli", "connection", "down", CONNECTION_NAME], capture_output=True
    )
    subprocess.run(
        ["nmcli", "connection", "delete", CONNECTION_NAME], capture_output=True
    )
    if ipv6_mode == "block_while_connected":
        _restore_ipv6_on_main()
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
    return True, "VPN disconnected."
