"""WiFi network scanner using Windows netsh command."""

import subprocess
import re
from typing import Optional

# Channel to frequency mapping (MHz)
CHANNEL_FREQ = {
    # 2.4 GHz band
    1: 2412, 2: 2417, 3: 2422, 4: 2427, 5: 2432, 6: 2437, 7: 2442,
    8: 2447, 9: 2452, 10: 2457, 11: 2462, 12: 2467, 13: 2472, 14: 2484,
    # 5 GHz band
    32: 5160, 36: 5180, 40: 5200, 44: 5220, 48: 5240,
    52: 5260, 56: 5280, 60: 5300, 64: 5320,
    100: 5500, 104: 5520, 108: 5540, 112: 5560, 116: 5580,
    120: 5600, 124: 5620, 128: 5640, 132: 5660, 136: 5680, 140: 5700, 144: 5720,
    149: 5745, 153: 5765, 157: 5785, 161: 5805, 165: 5825,
    169: 5845, 173: 5865, 177: 5885,
    # 6 GHz band (Wi-Fi 6E)
    1: 5955, 5: 5975, 9: 5995, 13: 6015, 17: 6035, 21: 6055, 25: 6075,
    29: 6095, 33: 6115, 37: 6135, 41: 6155, 45: 6175, 49: 6195, 53: 6215,
    57: 6235, 61: 6255, 65: 6275, 69: 6295, 73: 6315, 77: 6335, 81: 6355,
    85: 6375, 89: 6395, 93: 6415, 97: 6435, 101: 6455, 105: 6475, 109: 6495,
    113: 6515, 117: 6535, 121: 6555, 125: 6575, 129: 6595, 133: 6615,
    137: 6635, 141: 6655, 145: 6675, 149: 6695, 153: 6715, 157: 6735,
    161: 6755, 165: 6775, 169: 6795, 173: 6815, 177: 6835, 181: 6855,
    185: 6875, 189: 6895, 193: 6915, 197: 6935, 201: 6955, 205: 6975,
    209: 6995, 213: 7015, 217: 7035, 221: 7055, 225: 7075, 229: 7095, 233: 7115,
}

# Separate maps for band determination (since channels can overlap between bands)
CHANNELS_24GHZ = set(range(1, 15))
CHANNELS_5GHZ = {32, 36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112, 116,
                 120, 124, 128, 132, 136, 140, 144, 149, 153, 157, 161, 165, 169, 173, 177}

FREQ_24GHZ = {ch: freq for ch, freq in [
    (1, 2412), (2, 2417), (3, 2422), (4, 2427), (5, 2432), (6, 2437), (7, 2442),
    (8, 2447), (9, 2452), (10, 2457), (11, 2462), (12, 2467), (13, 2472), (14, 2484),
]}

FREQ_5GHZ = {ch: freq for ch, freq in [
    (32, 5160), (36, 5180), (40, 5200), (44, 5220), (48, 5240),
    (52, 5260), (56, 5280), (60, 5300), (64, 5320),
    (100, 5500), (104, 5520), (108, 5540), (112, 5560), (116, 5580),
    (120, 5600), (124, 5620), (128, 5640), (132, 5660), (136, 5680),
    (140, 5700), (144, 5720),
    (149, 5745), (153, 5765), (157, 5785), (161, 5805), (165, 5825),
    (169, 5845), (173, 5865), (177, 5885),
]}


def signal_pct_to_dbm(pct: int) -> int:
    """Convert Windows signal percentage (0-100) to approximate dBm."""
    # Windows uses a roughly linear mapping: 100% ~ -30 dBm, 0% ~ -100 dBm
    return int(-100 + (pct * 0.7))


def get_band(channel: int, radio_type: str = "") -> str:
    """Determine band from channel number and optional radio type hint."""
    radio_lower = radio_type.lower()
    if "802.11a" in radio_lower or "802.11ac" in radio_lower or "802.11ax" in radio_lower:
        if channel in CHANNELS_5GHZ:
            return "5 GHz"
    if channel in CHANNELS_5GHZ and channel not in CHANNELS_24GHZ:
        return "5 GHz"
    if channel in CHANNELS_24GHZ and channel not in CHANNELS_5GHZ:
        return "2.4 GHz"
    # Ambiguous channels - use radio type hint
    if "802.11n" in radio_lower or "802.11g" in radio_lower or "802.11b" in radio_lower:
        return "2.4 GHz"
    if channel <= 14:
        return "2.4 GHz"
    return "5 GHz"


def get_frequency(channel: int, band: str) -> Optional[int]:
    """Get frequency in MHz for a channel and band."""
    if band == "2.4 GHz":
        return FREQ_24GHZ.get(channel)
    elif band == "5 GHz":
        return FREQ_5GHZ.get(channel)
    return None


def scan() -> list[dict]:
    """Scan for WiFi networks using netsh. Returns list of network dicts."""
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "networks", "mode=bssid"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return _parse_netsh_output(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        print(f"Scan error: {e}")
        return []


def _parse_netsh_output(output: str) -> list[dict]:
    """Parse netsh wlan show networks mode=bssid output."""
    networks = []
    current_ssid = ""
    current_network_type = ""
    current_auth = ""
    current_encryption = ""

    for line in output.splitlines():
        line = line.strip()

        # SSID line (not BSSID)
        ssid_match = re.match(r"^SSID\s+\d+\s*:\s*(.*)", line)
        if ssid_match:
            current_ssid = ssid_match.group(1).strip()
            continue

        # Network type
        type_match = re.match(r"^Network type\s*:\s*(.*)", line)
        if type_match:
            current_network_type = type_match.group(1).strip()
            continue

        # Authentication
        auth_match = re.match(r"^Authentication\s*:\s*(.*)", line)
        if auth_match:
            current_auth = auth_match.group(1).strip()
            continue

        # Encryption
        enc_match = re.match(r"^Encryption\s*:\s*(.*)", line)
        if enc_match:
            current_encryption = enc_match.group(1).strip()
            continue

        # BSSID
        bssid_match = re.match(r"^BSSID\s+\d+\s*:\s*(.*)", line)
        if bssid_match:
            bssid = bssid_match.group(1).strip()
            networks.append({
                "ssid": current_ssid or "(Hidden)",
                "bssid": bssid,
                "network_type": current_network_type,
                "auth": current_auth,
                "encryption": current_encryption,
                "signal_pct": 0,
                "signal_dbm": -100,
                "channel": 0,
                "band": "",
                "frequency_mhz": 0,
                "radio_type": "",
            })
            continue

        if not networks:
            continue

        # Signal
        sig_match = re.match(r"^Signal\s*:\s*(\d+)%", line)
        if sig_match:
            pct = int(sig_match.group(1))
            networks[-1]["signal_pct"] = pct
            networks[-1]["signal_dbm"] = signal_pct_to_dbm(pct)
            continue

        # Channel
        ch_match = re.match(r"^Channel\s*:\s*(\d+)", line)
        if ch_match:
            channel = int(ch_match.group(1))
            radio_type = networks[-1].get("radio_type", "")
            band = get_band(channel, radio_type)
            freq = get_frequency(channel, band)
            networks[-1]["channel"] = channel
            networks[-1]["band"] = band
            networks[-1]["frequency_mhz"] = freq or 0
            continue

        # Radio type
        radio_match = re.match(r"^Radio type\s*:\s*(.*)", line)
        if radio_match:
            radio_type = radio_match.group(1).strip()
            networks[-1]["radio_type"] = radio_type
            # Re-derive band if channel already set
            if networks[-1]["channel"]:
                band = get_band(networks[-1]["channel"], radio_type)
                networks[-1]["band"] = band
                networks[-1]["frequency_mhz"] = get_frequency(networks[-1]["channel"], band) or 0
            continue

    return networks


if __name__ == "__main__":
    import json
    results = scan()
    print(json.dumps(results, indent=2))
    print(f"\nFound {len(results)} networks")
