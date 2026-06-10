# VPN Gate GTK Client

A GTK4/Adwaita-based desktop client for [VPN Gate](https://www.vpngate.net/). Built with Python, libadwaita, and NetworkManager.

## Requirements

### System Dependencies (Fedora/RHEL)

```bash
sudo dnf install libadwaita-devel python3-gobject NetworkManager-openvpn
```

### System Dependencies (Arch/Manjaro)

```bash
sudo pacman -S libadwaita python-gobject networkmanager-openvpn
```

### System Dependencies (Ubuntu/Debian)

```bash
sudo apt install libadwaita-1-dev python3-gi gir1.2-adw-1 network-manager-openvpn
```

### Python Dependencies

```bash
pip install -r requirements.txt
# Or with uv:
uv sync
```

## Installation

### Fedora

```bash
sudo dnf copr enable apicalshark/collection
sudo dnf install vpngate-gtk
```

For other linux distribution, please make your own package.

### Run Directly

```bash
python main.py
# Or with uv (recommended):
uv run main.py
```

## Usage

1. **Launch the application** — Run `vpngate-gtk` or `python main.py`
2. **Select a server** — Click a server in the list
3. **Choose protocol** — Use the UDP/TCP/All toggle buttons
4. **Connect** — Click "Connect" button
5. **Monitor** — View real-time stats (download/upload speed, ping, packet loss)
6. **Disconnect** — Click "Disconnect" when done

The app minimizes to the system tray on close (configurable in Settings).

## Configuration

Settings are stored in `~/.config/vpngate-gtk/config.json`:

```json
{
  "api_source": "vpngate",
  "minimize_on_close": false
}
```

- `api_source`: `"vpngate"` (recommended) or `"ovpnpw"` (fallback)
- `minimize_on_close`: `true` to hide to tray instead of quitting

## License

GPL-3.0 — See [LICENSE](LICENSE) for details.
