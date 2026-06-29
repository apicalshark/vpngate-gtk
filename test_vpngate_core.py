import unittest
import os
import vpngate_core as vpncore


class TestVPNGateCore(unittest.TestCase):
    def setUp(self):
        # Backup existing config if any
        self.config_path = os.path.expanduser("~/.config/vpngate-gtk/config.json")
        self.backup_path = self.config_path + ".bak"
        if os.path.exists(self.config_path):
            os.rename(self.config_path, self.backup_path)

    def tearDown(self):
        # Restore config
        if os.path.exists(self.backup_path):
            if os.path.exists(self.config_path):
                os.remove(self.config_path)
            os.rename(self.backup_path, self.config_path)
        elif os.path.exists(self.config_path):
            os.remove(self.config_path)

    def test_settings_persistence(self):
        vpncore.set_protocol("udp")
        vpncore.set_sort_key("ping")
        vpncore.set_filter_country("JP")

        # Force reload
        vpncore._load_config()

        self.assertEqual(vpncore.get_protocol(), "udp")
        self.assertEqual(vpncore.get_sort_key(), "ping")
        self.assertEqual(vpncore.get_filter_country(), "JP")


if __name__ == "__main__":
    unittest.main()
