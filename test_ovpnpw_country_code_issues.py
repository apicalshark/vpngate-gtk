#!/usr/bin/env python3
"""Test script to reproduce ovpn.pw API data issues.

Fetches from ovpn.pw and checks for:
1. The 'ovpn.pw/update' fake server entry being included (no filter)
2. CountryLong vs CountryShort mismatches (wrong country name displayed)
3. Any servers where get_flag returns globe emoji (broken flag)
"""
import sys
import os
import requests
import base64
import csv
import io

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

API_URL_OVPNPW = "https://api.ovpn.pw/csv"


def get_flag(country_short):
    code = country_short.strip().upper()
    # Ensure it is a valid 2-letter alphabetic country code
    if len(code) != 2 or not code.isalpha():
        return "🌍"
    return chr(0x1F1E6 + ord(code[0]) - ord("A")) + chr(
        0x1F1E6 + ord(code[1]) - ord("A")
    )


# Expected CountryShort -> CountryLong mapping
EXPECTED_NAMES = {
    "AR": "Argentina", "AU": "Australia", "AT": "Austria", "BD": "Bangladesh",
    "BY": "Belarus", "BE": "Belgium", "BR": "Brazil", "BG": "Bulgaria",
    "CA": "Canada", "CL": "Chile", "CN": "China", "CO": "Colombia",
    "HR": "Croatia", "CZ": "Czech Republic", "DK": "Denmark", "EE": "Estonia",
    "FI": "Finland", "FR": "France", "DE": "Germany", "GR": "Greece",
    "HK": "Hong Kong", "HU": "Hungary", "IS": "Iceland", "IN": "India",
    "ID": "Indonesia", "IE": "Ireland", "IL": "Israel", "IT": "Italy",
    "JP": "Japan", "KR": "Korea Republic of", "LV": "Latvia",
    "LT": "Lithuania", "LU": "Luxembourg", "MY": "Malaysia", "MX": "Mexico",
    "MD": "Moldova", "NL": "Netherlands", "NZ": "New Zealand", "NG": "Nigeria",
    "NO": "Norway", "PH": "Philippines", "PL": "Poland", "PT": "Portugal",
    "RO": "Romania", "RU": "Russian Federation", "SG": "Singapore",
    "SK": "Slovakia", "SI": "Slovenia", "ZA": "South Africa", "ES": "Spain",
    "SE": "Sweden", "CH": "Switzerland", "TW": "Taiwan", "TH": "Thailand",
    "TR": "Turkey", "UA": "Ukraine", "AE": "United Arab Emirates",
    "GB": "United Kingdom", "US": "United States", "VN": "Viet Nam",
    "GD": "Grenada", "BB": "Barbados", "BS": "Bahamas", "PA": "Panama",
    "CR": "Costa Rica", "UY": "Uruguay",
}


def fetch_ovpnpw():
    response = requests.get(API_URL_OVPNPW, timeout=10)
    response.raise_for_status()
    
    # Use StringIO and csv.reader to correctly parse quoted strings containing commas
    csv_file = io.StringIO(response.text)
    reader = csv.reader(csv_file)
    
    header = None
    servers = []
    
    for row in reader:
        if not row:
            continue
        
        # Skip VPN Gate meta-lines (like '*vpn_servers' or '*' at the end)
        if len(row) == 1 and (row[0].startswith("*") or row[0].strip() == "*"):
            continue
            
        # Detect and clean the header row
        if row[0].startswith("#"):
            header = [row[0][1:]] + row[1:]
            continue
            
        # If we haven't encountered the header yet, skip this data row
        if not header:
            continue
            
        # Ensure row length matches the parsed header length
        if len(row) < len(header):
            continue
            
        server = dict(zip(header, row))
        try:
            if "OpenVPN_ConfigData_Base64" not in server:
                continue
                
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


def main():
    print("Fetching from ovpn.pw...")
    try:
        servers = fetch_ovpnpw()
    except Exception as e:
        print(f"Error fetching/parsing API data: {e}")
        return 1

    print(f"Total servers parsed: {len(servers)}\n")

    # If no servers are found, fail early instead of falsely passing
    if not servers:
        print("RESULT: FAIL - No servers were successfully parsed.")
        return 1

    issues = []

    # Issue 1: Check for the fake update entry
    update_entries = [s for s in servers if s.get("HostName") == "ovpn.pw/update"]
    if update_entries:
        issues.append(
            f"ISSUE 1: Fake 'ovpn.pw/update' entry is included in server list "
            f"(CountryShort={update_entries[0]['CountryShort']!r}). "
            f"This should be filtered out."
        )

    # Issue 2: Check CountryLong vs CountryShort mismatches
    for s in servers:
        cs = s.get("CountryShort", "")
        cl = s.get("CountryLong", "")
        if cs in EXPECTED_NAMES and cl != EXPECTED_NAMES[cs]:
            issues.append(
                f"ISSUE 2: CountryLong mismatch: HostName={s['HostName']!r} "
                f"CountryShort={cs!r} CountryLong={cl!r} "
                f"(expected {EXPECTED_NAMES[cs]!r})"
            )

    # Issue 3: Check for broken flags (globe emoji)
    for s in servers:
        cs = s.get("CountryShort", "")
        flag = get_flag(cs)
        if flag == "\U0001f30d":
            issues.append(
                f"ISSUE 3: Broken flag: HostName={s['HostName']!r} "
                f"CountryShort={cs!r} -> globe emoji instead of country flag"
            )

    # Issue 4: Check for CountryShort appearing with multiple CountryLong values
    short_to_longs = {}
    for s in servers:
        cs = s.get("CountryShort", "")
        cl = s.get("CountryLong", "")
        if cs:  # Only track non-empty country codes
            short_to_longs.setdefault(cs, set()).add(cl)
            
    for cs, longs in short_to_longs.items():
        if len(longs) > 1:
            issues.append(
                f"ISSUE 4: CountryShort={cs!r} maps to multiple CountryLong values: {longs}"
            )

    # Report
    if issues:
        print(f"Found {len(issues)} issue(s):\n")
        for i, issue in enumerate(issues, 1):
            print(f"  [{i}] {issue}\n")
        print("RESULT: FAIL - issues detected")
        return 1
    else:
        print("No issues found.")
        print("RESULT: PASS")
        return 0


if __name__ == "__main__":
    sys.exit(main())