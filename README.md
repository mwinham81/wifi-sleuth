# WiFiSleuth

A WiFi network analyzer and geolocation tool for Windows. Scans nearby access points, records signal strength with GPS coordinates, and estimates AP locations through triangulation.

<img width="2333" height="856" alt="image" src="https://github.com/user-attachments/assets/80a98428-97b1-4b29-b648-b342c9d40da3" />


![Python](https://img.shields.io/badge/python-3.x-blue)
![Flask](https://img.shields.io/badge/flask-%E2%89%A53.0-green)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)

## Features

- **Live WiFi Scanning** - Real-time detection of nearby networks with signal strength, channel, band, and security info
- **GPS Geotagging** - Tag scans with GPS coordinates from your phone's browser
- **Signal Mapping** - Visualize signal strength readings on an interactive Leaflet map
- **AP Triangulation** - Estimate access point physical locations using trilateration from multiple geotagged readings
- **Channel Analysis** - View network distribution across 2.4 GHz and 5 GHz bands with Plotly charts
- **Time-Series Recording** - Log signal strength over time for selected networks
- **Multi-Device** - Run the server on your laptop, connect from your phone on the same WiFi to provide GPS data

## How It Works

1. **Laptop** runs the Flask server and performs WiFi scans using the Windows `netsh` command
2. **Phone** (on the same network) opens the web UI and provides GPS coordinates via the browser Geolocation API
3. Walk around to collect geotagged signal readings, then use triangulation to estimate where access points are physically located

## Prerequisites

- Windows 10/11
- Python 3.x

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/wifi-sleuth.git
cd wifi-sleuth
pip install -r requirements.txt
```

If you need to install Python, there's a helper script:

```powershell
.\install-pyenv-win.ps1
```

## Usage

```bash
python app.py
```

The server starts on port 5000. The console will print your local IP address.

- **Desktop**: http://localhost:5000
- **Phone** (same WiFi): http://YOUR_LOCAL_IP:5000

### Tabs

| Tab | Purpose |
|-----|---------|
| **Live Scan** | Real-time network list with signal strength, channel, and security details |
| **Channel Map** | Bar chart of network distribution across WiFi channels |
| **Time Series** | Record and chart signal strength over time for selected BSSIDs |
| **Signal Map** | Interactive map showing geotagged readings and triangulated AP locations |

### Workflow

1. Open the app on your laptop and phone
2. On the phone, allow location access when prompted
3. The GPS status indicator turns green when coordinates are available
4. Click **Record** on the Live Scan tab to save a geotagged snapshot
5. Move to a different location, record again - repeat for multiple readings
6. Switch to the Signal Map tab to see your readings and triangulated AP positions

## Project Structure

```
wifi-sleuth/
├── app.py              # Flask routes and API endpoints
├── scanner.py          # WiFi scanning via netsh, signal parsing
├── database.py         # SQLite storage and schema
├── triangulator.py     # Trilateration and weighted centroid algorithms
├── requirements.txt    # Python dependencies
├── install-pyenv-win.ps1
├── templates/
│   └── index.html      # Single-page UI with tabs
└── static/
    ├── app.js          # Frontend logic (scanning, mapping, charting)
    └── style.css       # Dark theme styles
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/scan` | Current WiFi networks |
| POST | `/api/location` | Receive GPS coordinates from phone |
| GET | `/api/gps` | Current GPS state |
| POST | `/api/record` | Save a geotagged scan |
| POST | `/api/recording` | Start/stop time-series recording |
| GET | `/api/recording` | Recording status |
| GET | `/api/timeseries/<bssid>` | Signal history for a BSSID |
| GET | `/api/bssids` | All recorded BSSIDs |
| GET | `/api/history` | All geotagged scans (for map) |
| GET | `/api/triangulate/<bssid>` | Estimated AP location |
| POST | `/api/clear` | Erase all stored data |

## Technical Notes

- WiFi scanning uses `netsh wlan show networks mode=bssid` (Windows-only)
- Triangulation uses a log-distance path loss model (reference RSSI: -30 dBm at 1m, path loss exponent: 3.0)
- The database is SQLite with WAL mode, stored as `wifisleuth.db` in the project root
- The frontend auto-refreshes scan results every 3 seconds
- Networks that disappear from scans are shown as "ghosts" for 15 seconds before removal

## License

MIT
