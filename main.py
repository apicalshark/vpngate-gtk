#!/usr/bin/env python3
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
import sys
import os
import threading

try:
    import gi
except ModuleNotFoundError:
    import subprocess
    result = subprocess.run(
        ["/usr/bin/python3", "-c", "import site; print(site.getsitepackages()[0])"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        sys.path.insert(0, result.stdout.strip())
    import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import GLib, Gio, Gtk, Adw, GObject, Pango

from trayer import TrayIcon
import vpngate_core as vpncore

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

def get_flag(country_short):
    code = country_short.upper()
    if len(code) != 2:
        return '🌍'
    return chr(0x1F1E6 + ord(code[0]) - ord('A')) + chr(0x1F1E6 + ord(code[1]) - ord('A'))


# Region mapping for filtering
REGION_TO_COUNTRIES = {
    "Southeast Asia & Oceania": ["SG", "TH", "MY", "VN", "ID", "PH", "AU", "NZ", "BN", "MM", "KH", "LA", "LK", "PG", "WS", "TO", "FJ", "PW", "TV", "NR", "KI"],
    "East Asia": ["CN", "TW", "HK", "JP", "KR", "MN", "MO"],
    "North America": ["US", "CA", "MX", "GT", "HN", "SV", "NI", "CR", "PA", "CU", "JM", "DO", "BB", "TT", "BS", "BZ", "AG", "DM", "GD", "LC", "KN", "PM", "VC", "AI", "MS", "MF", "SX", "CW", "AW", "BO", "BR", "AR", "CL", "CO", "PE", "VE", "EC", "GY", "PY", "UY"],
    "Central & South America": ["GT", "HN", "SV", "NI", "CR", "PA", "CU", "JM", "DO", "BB", "TT", "BS", "BZ", "AG", "DM", "GD", "LC", "KN", "PM", "VC", "AI", "MS", "MF", "SX", "CW", "AW", "BO", "BR", "AR", "CL", "CO", "PE", "VE", "EC", "GY", "PY", "UY"],
    "Europe": ["GB", "DE", "FR", "IT", "ES", "PT", "NL", "BE", "CH", "AT", "SE", "NO", "DK", "FI", "PL", "CZ", "HU", "RO", "BG", "GR", "IE", "IS", "AL", "HR", "SI", "SK", "EE", "LV", "LT", "MT", "MU", "CY", "LU", "LI", "MC", "SM", "VA", "AD", "GI", "FO", "CK", "JE", "GG", "IM"],
    "Africa": ["ZA", "EG", "KE", "NG", "MA", "DZ", "TN", "GH", "ET", "CI", "MU", "SD", "ZM", "MZ", "RW", "BI", "UG", "TZ", "SS", "GW", "SL", "LR", "GN", "BF", "ML", "NE", "TG", "BJ", "GA", "CG", "CD", "AO", "GM", "SN", "GN", "ML", "MR", "MU", "SC", "ST", "DM", "NE", "TG", "BJ", "GA", "GQ", "CM", "CF", "TD", "ER", "DJ", "SZ", "LS", "BW", "NA"],
    "South Asia": ["IN", "PK", "BD", "LK", "NP", "BT", "MV"],
    "West Asia": ["SA", "IR", "IQ", "YE", "AF", "PK", "TJ", "TM", "AZ", "GE", "AM", "IL", "JO", "LB", "SY", "TR"],
    "North Asia": ["RU", "KZ", "MN", "KG", "AM", "AZ", "BY", "GE", "KG", "KZ", "MN", "RU", "TJ", "TM"]
}


class ServerData(GObject.Object):
    __gtype_name__ = 'ServerData'

    def __init__(self, server_dict):
        super().__init__()
        self.server = server_dict
        self.hostname = server_dict.get('HostName', '')
        self.ip = server_dict.get('IP', '')
        self.score_str = server_dict.get('Score', '0')
        self.ping_str = server_dict.get('Ping', 'N/A')
        self.speed_str = server_dict.get('Speed', '0')
        self.country = server_dict.get('CountryLong', '')
        self.country_short = server_dict.get('CountryShort', '')
        self.uptime = server_dict.get('Uptime', '0')
        self.total_users = server_dict.get('TotalUsers', '0')
        self.total_traffic = server_dict.get('TotalTraffic', '0')
        self.has_udp = server_dict.get('has_udp', False)
        self.has_tcp = server_dict.get('has_tcp', False)
        self.flag = get_flag(self.country_short)

    def get_proto_str(self):
        if self.has_udp and self.has_tcp:
            return "UDP+TCP"
        elif self.has_udp:
            return "UDP"
        return "TCP"

    def get_score_int(self):
        try:
            return int(self.score_str)
        except ValueError:
            return 0

    def get_ping_int(self):
        try:
            return int(self.ping_str)
        except ValueError:
            return 9999

    def get_speed_str(self):
        try:
            speed = int(self.speed_str)
        except ValueError:
            return "N/A"
        if speed >= 1000000:
            return f"{speed / 1000000:.1f} Mbps"
        elif speed >= 1000:
            return f"{speed / 1000:.0f} Kbps"
        return f"{speed} bps"


class VPNClientWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title("VPN Gate Client")
        self.set_default_size(420, 760)

        self.all_server_dicts = []
        self.filtered_data = []
        self.current_sort_key = 'score'
        self.sort_reverse = True
        self.is_busy = False
        self._connecting = False
        self._disconnecting = False
        self.filter_country = None
        self.country_entries = [("All", None)]
        self.filter_region = None
        self.region_entries = [("All regions", None)]

        self._build_ui()
        self._update_ui_state()
        self._load_servers()
        self._stats_timer_id = GLib.timeout_add(3000, self._poll_stats)
        self.connect('close-request', self._on_close_request)

    def _build_ui(self):
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.toast_overlay.set_child(box)

        header = Adw.HeaderBar()
        box.append(header)

        prefs_btn = Gtk.Button(icon_name='preferences-system-symbolic')
        prefs_btn.set_tooltip_text("Settings")
        prefs_btn.connect('clicked', self._show_preferences)
        header.pack_end(prefs_btn)

        filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        filter_box.set_margin_start(12)
        filter_box.set_margin_end(12)
        filter_box.set_margin_top(6)
        filter_box.set_margin_bottom(6)

        self.filter_udp = Gtk.ToggleButton(label="UDP")
        self.filter_tcp = Gtk.ToggleButton(label="TCP")
        self.filter_all = Gtk.ToggleButton(label="All")
        self.filter_udp.set_active(True)

        for btn in (self.filter_udp, self.filter_tcp, self.filter_all):
            btn.add_css_class('flat')
            btn.connect('toggled', self._on_filter_toggled)
            filter_box.append(btn)

        sort_label = Gtk.Label(label="  Sort:")
        filter_box.append(sort_label)

        sort_store = Gtk.StringList.new(['Score', 'Ping', 'Country'])
        self.sort_dropdown = Gtk.DropDown.new(sort_store, None)
        self.sort_dropdown.set_selected(0)
        self.sort_dropdown.connect('notify::selected', self._on_sort_changed)
        filter_box.append(self.sort_dropdown)

        box.append(filter_box)

        self.store = Gio.ListStore.new(ServerData)
        self.selection = Gtk.SingleSelection.new(self.store)
        factory = Gtk.SignalListItemFactory()
        factory.connect('setup', self._setup_row)
        factory.connect('bind', self._bind_row)
        factory.connect('unbind', self._unbind_row)

        self.list_view = Gtk.ListView.new(self.selection, factory)
        self.list_view.set_vexpand(True)

        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.list_view)
        scroll.set_vexpand(True)
        box.append(scroll)

        self.status_label = Gtk.Label(label="Status: DISCONNECTED")
        self.status_label.set_margin_start(12)
        self.status_label.set_margin_end(12)
        self.status_label.set_margin_top(6)
        self.status_label.set_xalign(0)
        self.status_label.add_css_class('heading')
        box.append(self.status_label)

        self.stats_label = Gtk.Label(label="")
        self.stats_label.set_margin_start(12)
        self.stats_label.set_margin_end(12)
        self.stats_label.set_margin_bottom(6)
        self.stats_label.set_xalign(0)
        self.stats_label.add_css_class('dim-label')
        box.append(self.stats_label)

        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        action_box.set_margin_start(12)
        action_box.set_margin_end(12)
        action_box.set_margin_top(6)
        action_box.set_margin_bottom(12)

        self.refresh_btn = Gtk.Button(label="Refresh")
        self.refresh_btn.connect('clicked', lambda b: self._load_servers())

        self.connect_btn = Gtk.Button(label="Connect")
        self.connect_btn.add_css_class('suggested-action')
        self.connect_btn.connect('clicked', self._on_connect)

        self.disconnect_btn = Gtk.Button(label="Disconnect")
        self.disconnect_btn.add_css_class('destructive-action')
        self.disconnect_btn.connect('clicked', self._on_disconnect)

        action_box.append(self.refresh_btn)
        action_box.append(self.connect_btn)
        action_box.append(self.disconnect_btn)
        box.append(action_box)

        css_provider = Gtk.CssProvider()
        css_provider.load_from_bytes(GLib.Bytes.new(b"""
            .ping-badge { background: @accent_bg_color; color: @accent_fg_color;
                          border-radius: 8px; padding: 2px 8px; font-size: 12px; }
            .status-connecting { color: #ffa348; }
            .status-connected { color: #33d17a; }
            .status-error { color: #e01b24; }
        """))
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _setup_row(self, factory, list_item):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(8)
        box.set_margin_bottom(8)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        flag = Gtk.Label()
        flag.set_xalign(0)
        flag.add_css_class('heading')
        country = Gtk.Label()
        country.set_xalign(0)
        country.set_hexpand(True)
        country.set_ellipsize(Pango.EllipsizeMode.END)
        speed = Gtk.Label()
        speed.set_xalign(1)
        speed.add_css_class('dim-label')
        speed.add_css_class('caption')
        ping = Gtk.Label()
        ping.set_xalign(1)
        ping.add_css_class('ping-badge')
        top.append(flag)
        top.append(country)
        top.append(speed)
        top.append(ping)

        bot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        host = Gtk.Label()
        host.set_xalign(0)
        host.set_hexpand(True)
        host.add_css_class('caption')
        host.add_css_class('dim-label')
        proto = Gtk.Label()
        proto.set_xalign(1)
        proto.add_css_class('caption')
        proto.add_css_class('dim-label')
        bot.append(host)
        bot.append(proto)

        box.append(top)
        box.append(bot)
        list_item.set_child(box)

        list_item._flag = flag
        list_item._country = country
        list_item._speed = speed
        list_item._ping = ping
        list_item._host = host
        list_item._proto = proto

    def _bind_row(self, factory, list_item):
        sd = list_item.get_item()
        if not sd:
            return
        list_item._flag.set_text(sd.flag)
        list_item._country.set_text(sd.country)
        list_item._speed.set_text(sd.get_speed_str())
        list_item._ping.set_text(f"{sd.ping_str} ms")
        list_item._host.set_text(sd.hostname or sd.ip)
        list_item._proto.set_text(sd.get_proto_str())

    def _unbind_row(self, factory, list_item):
        pass

    def _on_filter_toggled(self, btn):
        if not btn.get_active():
            return
        if btn == self.filter_udp:
            self.filter_tcp.set_active(False)
            self.filter_all.set_active(False)
        elif btn == self.filter_tcp:
            self.filter_udp.set_active(False)
            self.filter_all.set_active(False)
        elif btn == self.filter_all:
            self.filter_udp.set_active(False)
            self.filter_tcp.set_active(False)
        self._apply_sort_filter()

    def _on_sort_changed(self, dropdown, pspec):
        idx = dropdown.get_selected()
        key_map = {0: 'score', 1: 'ping', 2: 'country'}
        new_key = key_map.get(idx, 'score')
        if new_key == self.current_sort_key:
            self.sort_reverse = not self.sort_reverse
        else:
            self.current_sort_key = new_key
            self.sort_reverse = (new_key != 'country')
        self._apply_sort_filter()

    def _on_refresh(self, servers):
        self.all_server_dicts = servers
        for i, s in enumerate(self.all_server_dicts):
            s['gui_idx'] = i

        short_codes = sorted(set(
            s.get('CountryShort', '--') for s in servers
            if s.get('CountryShort')
        ))
        self.country_entries = [("All", None)]
        for c in short_codes:
            flag = get_flag(c)
            long_name = s.get('CountryLong', c) if any(
                s.get('CountryShort') == c and s.get('CountryLong')
                for s in servers
            ) else c
            for s in servers:
                if s.get('CountryShort') == c and s.get('CountryLong'):
                    long_name = s['CountryLong']
                    break
            self.country_entries.append((f"{flag} {long_name}", c))

        self.region_entries = [("All regions", None)]
        for region_name in sorted(REGION_TO_COUNTRIES.keys()):
            self.region_entries.append((region_name, region_name))

        self._apply_sort_filter()

    def _load_servers(self):
        self.status_label.remove_css_class('status-connected')
        self.status_label.remove_css_class('status-error')
        self.status_label.add_css_class('status-connecting')

        def task():
            servers = vpncore.get_servers()
            GLib.idle_add(self._on_refresh, servers)

        threading.Thread(target=task, daemon=True).start()

    def _sort_key(self, sd):
        if self.current_sort_key == 'score':
            return sd.get_score_int()
        elif self.current_sort_key == 'ping':
            return sd.get_ping_int()
        elif self.current_sort_key == 'country':
            return sd.country.lower()
        return 0

    def _apply_sort_filter(self):
        filter_udp = self.filter_udp.get_active()
        filter_tcp = self.filter_tcp.get_active()

        filtered = []
        for s in self.all_server_dicts:
            if filter_udp and not s.get('has_udp', False):
                continue
            if filter_tcp and not s.get('has_tcp', False):
                continue
            if not filter_udp and not filter_tcp:
                pass

            if self.filter_region and s.get('CountryShort', '') not in REGION_TO_COUNTRIES.get(self.filter_region, []):
                continue

            if self.filter_country and s.get('CountryShort', '') != self.filter_country:
                continue

            filtered.append(s)

        server_data_list = [ServerData(s) for s in filtered]
        server_data_list.sort(key=self._sort_key, reverse=self.sort_reverse)
        self.filtered_data = server_data_list

        self.store.remove_all()
        for sd in server_data_list[:100]:
            self.store.append(sd)

        self._update_ui_state()

    def _get_selected_server(self):
        pos = self.selection.get_selected()
        if pos == Gtk.INVALID_LIST_POSITION:
            return None
        item = self.selection.get_item(pos)
        return item.server if item else None

    def _on_connect(self, btn):
        if vpncore.is_active():
            self._show_toast("A VPN is already active. Disconnect first.")
            return

        server = self._get_selected_server()
        if not server:
            self._show_toast("Select a server first.")
            return

        proto = "tcp" if self.filter_tcp.get_active() else None
        self._connecting = True
        self._set_busy(True)
        self.status_label.set_text(f"Status: Connecting to {server['IP']}...")

        def task():
            success, msg = vpncore.connect_vpn(server, force_proto=proto)
            GLib.idle_add(self._on_connect_result, success, msg)

        threading.Thread(target=task, daemon=True).start()

    def _on_connect_result(self, success, msg):
        if not self._connecting:
            return
        self._connecting = False
        self._set_busy(False)
        self.status_label.set_text(f"Status: {msg}")
        if success:
            self.status_label.remove_css_class('status-connecting')
            self.status_label.remove_css_class('status-error')
            self.status_label.add_css_class('status-connected')
        else:
            self.status_label.remove_css_class('status-connecting')
            self.status_label.remove_css_class('status-connected')
            self.status_label.add_css_class('status-error')
        self._update_ui_state()

    def _on_disconnect(self, btn):
        if self._disconnecting:
            return

        self._disconnecting = True

        if self._connecting:
            self._connecting = False
            vpncore.cancel_connect()
            self.status_label.remove_css_class('status-connecting')
            self.status_label.set_text("Status: Disconnecting...")

            def task():
                vpncore.disconnect_vpn()
                GLib.idle_add(self._on_disconnect_result, True, "VPN disconnected.")

            threading.Thread(target=task, daemon=True).start()
            return

        self.status_label.set_text("Status: Disconnecting...")
        self._set_busy(True)

        def task():
            success, msg = vpncore.disconnect_vpn()
            GLib.idle_add(self._on_disconnect_result, success, msg)

        threading.Thread(target=task, daemon=True).start()

    def _on_disconnect_result(self, success, msg):
        self._disconnecting = False
        self._set_busy(False)
        self.status_label.set_text(f"Status: {msg}")
        self.stats_label.set_text("")
        self.status_label.remove_css_class('status-connected')
        self.status_label.remove_css_class('status-connecting')
        self.status_label.remove_css_class('status-error')
        self._update_ui_state()

    def _set_busy(self, busy):
        self.is_busy = busy
        self.refresh_btn.set_sensitive(not busy)
        self.connect_btn.set_sensitive(not busy)

    def _update_ui_state(self):
        active = vpncore.is_active()
        self.connect_btn.set_sensitive(not active and not self.is_busy)
        self.disconnect_btn.set_sensitive(not self.is_busy)
        self.refresh_btn.set_sensitive(not self.is_busy)
        self.list_view.set_sensitive(not self.is_busy)

    def _poll_stats(self):
        if self.is_busy:
            return True

        if not vpncore.is_active():
            if "ACTIVE" in self.status_label.get_text() or "CONNECTED" in self.status_label.get_text():
                self.status_label.set_text("Status: DISCONNECTED")
                self.stats_label.set_text("")
                self._update_ui_state()
            return True

        def task():
            stats = vpncore.get_stats()
            GLib.idle_add(self._update_stats, stats)

        threading.Thread(target=task, daemon=True).start()
        return True

    def _update_stats(self, stats):
        if stats and not self.is_busy:
            up, down, ping, loss = stats
            self.stats_label.set_text(
                f"DOWN: {down:.1f} KB/s  |  UP: {up:.1f} KB/s  |  PING: {ping}  |  LOSS: {loss}"
            )

    def _on_close_request(self, win):
        if vpncore.get_minimize_on_close():
            self.hide()
            return True
        return False

    def _show_preferences(self, btn):
        dialog = Adw.PreferencesDialog()

        page = Adw.PreferencesPage()
        page.set_title("Settings")

        group = Adw.PreferencesGroup()
        group.set_title("Data Source")
        group.set_description("Choose the VPN server list source")

        source_row = Adw.ComboRow()
        source_row.set_title("API Source")
        model = Gtk.StringList.new(["VPN Gate (recommended)", "api.ovpn.pw (fallback)"])
        source_row.set_model(model)
        source_row.set_selected(0 if vpncore.get_api_source() == "vpngate" else 1)
        group.add(source_row)

        country_group = Adw.PreferencesGroup()
        country_group.set_title("Country Filter")
        country_group.set_description("Only show servers from a specific country")

        country_names = [entry[0] for entry in self.country_entries]
        country_model = Gtk.StringList.new(country_names)
        self.country_pref_row = Adw.ComboRow()
        self.country_pref_row.set_title("Country")
        self.country_pref_row.set_model(country_model)
        current_idx = 0
        for i, (_, code) in enumerate(self.country_entries):
            if code == self.filter_country:
                current_idx = i
                break
        self.country_pref_row.set_selected(current_idx)
        country_group.add(self.country_pref_row)

        region_group = Adw.PreferencesGroup()
        region_group.set_title("Region Filter")
        region_group.set_description("Only show servers from a specific region")

        region_names = [entry[0] for entry in self.region_entries]
        region_model = Gtk.StringList.new(region_names)
        self.region_pref_row = Adw.ComboRow()
        self.region_pref_row.set_title("Region")
        self.region_pref_row.set_model(region_model)
        current_idx = 0
        for i, (_, region_name) in enumerate(self.region_entries):
            if region_name == self.filter_region:
                current_idx = i
                break
        self.region_pref_row.set_selected(current_idx)
        region_group.add(self.region_pref_row)

        behavior_group = Adw.PreferencesGroup()
        behavior_group.set_title("Behavior")
        behavior_group.set_description("Configure application behavior")

        minimize_row = Adw.SwitchRow()
        minimize_row.set_title("Minimize on close")
        minimize_row.set_subtitle("Hide to system tray instead of quitting")
        minimize_row.set_active(vpncore.get_minimize_on_close())
        behavior_group.add(minimize_row)

        page.add(group)
        page.add(country_group)
        page.add(region_group)
        page.add(behavior_group)
        dialog.add(page)
        dialog.minimize_row = minimize_row

        dialog.connect('closed', self._on_prefs_closed, source_row)
        dialog.present(self)

    def _on_prefs_closed(self, dialog, source_row):
        selected_source = source_row.get_selected()
        new_source = "vpngate" if selected_source == 0 else "ovpnpw"
        if new_source != vpncore.get_api_source():
            vpncore.set_api_source(new_source)
            self._show_toast(f"Switched to {vpncore.get_api_source_label()}")
            self._load_servers()

        country_idx = self.country_pref_row.get_selected()
        _, new_code = self.country_entries[country_idx]
        if new_code != self.filter_country:
            self.filter_country = new_code
            self._apply_sort_filter()

        region_idx = self.region_pref_row.get_selected()
        _, new_region = self.region_entries[region_idx]
        if new_region != self.filter_region:
            self.filter_region = new_region
            self._apply_sort_filter()

        minimize = dialog.minimize_row.get_active()
        vpncore.set_minimize_on_close(minimize)

    def _show_toast(self, msg):
        toast = Adw.Toast.new(msg)
        toast.set_timeout(3)
        self.toast_overlay.add_toast(toast)


class VPNClientApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='io.github.apicalshark.vpngategtk')
        self.window = None
        self.tray = None

    def do_activate(self):
        if self.window is not None:
            self.window.present()
            return
        win = VPNClientWindow(self)
        self.window = win
        win.present()

    def toggle_window(self):
        if self.window and self.window.is_visible():
            self.window.hide()
        else:
            self.window.present()


if __name__ == "__main__":
    app = VPNClientApp()

    tray = TrayIcon(
        app_id="io.github.apicalshark.vpngategtk",
        title="VPN Gate Client",
        icon_name="network-vpn-symbolic"
    )
    tray.set_left_click(app.toggle_window)
    tray.add_menu_item("Show VPN Gate", callback=lambda: app.window.present() if app.window else None)
    tray.add_menu_item("Hide VPN Gate", callback=lambda: app.window.hide() if app.window else None)
    tray.add_menu_separator()
    tray.add_menu_item("Quit", callback=app.quit)
    tray.setup()
    app.tray = tray

    sys.exit(app.run(sys.argv))
