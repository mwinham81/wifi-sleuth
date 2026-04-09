"""WiFiSleuth - Flask web application for WiFi analysis."""

import time
import socket
from flask import Flask, render_template, jsonify, request

import scanner
import database
import triangulator

app = Flask(__name__)

# In-memory GPS state from phone
_gps_state = {
    "lat": None,
    "lng": None,
    "accuracy": None,
    "timestamp": 0,
}

# Time-series recording state
_recording = False


def get_local_ip() -> str:
    """Get this machine's LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@app.route("/")
def index():
    return render_template("index.html", local_ip=get_local_ip())


@app.route("/api/scan")
def api_scan():
    """Trigger a WiFi scan and return results."""
    networks = scanner.scan()
    return jsonify({"networks": networks, "timestamp": time.time()})


@app.route("/api/location", methods=["POST"])
def api_location():
    """Receive GPS coordinates from phone."""
    data = request.get_json(force=True)
    _gps_state["lat"] = data.get("lat")
    _gps_state["lng"] = data.get("lng")
    _gps_state["accuracy"] = data.get("accuracy")
    _gps_state["timestamp"] = time.time()
    return jsonify({"status": "ok"})


@app.route("/api/gps")
def api_gps():
    """Get current GPS state."""
    age = time.time() - _gps_state["timestamp"] if _gps_state["timestamp"] else None
    return jsonify({
        **_gps_state,
        "age_seconds": round(age, 1) if age else None,
        "fresh": age is not None and age < 10,
    })


@app.route("/api/record", methods=["POST"])
def api_record():
    """Record a geotagged scan."""
    networks = scanner.scan()
    lat = _gps_state["lat"] if _gps_state["timestamp"] and (time.time() - _gps_state["timestamp"]) < 30 else None
    lng = _gps_state["lng"] if lat else None
    ts = database.save_scan(networks, lat, lng)
    return jsonify({
        "status": "ok",
        "timestamp": ts,
        "network_count": len(networks),
        "geotagged": lat is not None,
        "lat": lat,
        "lng": lng,
    })


@app.route("/api/recording", methods=["POST"])
def api_recording():
    """Start/stop time-series recording."""
    global _recording
    data = request.get_json(force=True)
    _recording = data.get("active", False)
    return jsonify({"recording": _recording})


@app.route("/api/recording")
def api_recording_status():
    """Get recording state."""
    return jsonify({"recording": _recording})


@app.route("/api/timeseries/<bssid>")
def api_timeseries(bssid):
    """Get time-series data for a BSSID."""
    since = request.args.get("since", type=float)
    data = database.get_timeseries(bssid, since)
    return jsonify({"bssid": bssid, "data": data})


@app.route("/api/bssids")
def api_bssids():
    """Get all recorded BSSIDs."""
    return jsonify({"bssids": database.get_all_bssids()})


@app.route("/api/history")
def api_history():
    """Get all geotagged scan history."""
    limit = request.args.get("limit", 5000, type=int)
    return jsonify({"scans": database.get_history(limit)})


@app.route("/api/triangulate/<bssid>")
def api_triangulate(bssid):
    """Triangulate AP location for a BSSID."""
    readings = database.get_geotagged(bssid)
    if len(readings) < 2:
        return jsonify({"error": "Need at least 2 geotagged readings", "count": len(readings)}), 400

    if len(readings) >= 3:
        result = triangulator.trilaterate(readings)
    else:
        result = triangulator.weighted_centroid(readings)

    if not result:
        return jsonify({"error": "Could not estimate location"}), 400

    result["bssid"] = bssid
    return jsonify(result)


@app.route("/api/clear", methods=["POST"])
def api_clear():
    """Clear all recorded data."""
    database.clear_data()
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    local_ip = get_local_ip()
    print(f"\n{'='*60}")
    print(f"  WiFiSleuth - WiFi Analyzer")
    print(f"{'='*60}")
    print(f"  Dashboard:  http://localhost:5000")
    print(f"  On phone:   http://{local_ip}:5000")
    print(f"{'='*60}\n")
    app.run(host="0.0.0.0", port=5000, debug=True)
