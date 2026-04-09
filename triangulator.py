"""Signal triangulation using weighted centroid and path loss model."""

import math
from typing import Optional


# Log-distance path loss model parameters
# Reference distance (meters)
D0 = 1.0
# Reference RSSI at d0 (dBm) - typical for WiFi at 1 meter
RSSI_D0 = -30.0
# Path loss exponent (2.0 = free space, 2.7-3.5 = indoor, 3.0-5.0 = obstructed)
PATH_LOSS_EXPONENT = 3.0


def dbm_to_distance(rssi_dbm: int, path_loss_exp: float = PATH_LOSS_EXPONENT) -> float:
    """Estimate distance in meters from RSSI using log-distance path loss model.

    d = d0 * 10^((RSSI_d0 - RSSI) / (10 * n))
    """
    if rssi_dbm >= RSSI_D0:
        return D0
    exponent = (RSSI_D0 - rssi_dbm) / (10 * path_loss_exp)
    return D0 * (10 ** exponent)


def weighted_centroid(readings: list[dict]) -> Optional[dict]:
    """Estimate AP location using signal-weighted centroid.

    Each reading must have: lat, lng, signal_pct (or signal_dbm).
    Stronger signals get more weight.
    """
    if not readings or len(readings) < 2:
        return None

    total_weight = 0.0
    weighted_lat = 0.0
    weighted_lng = 0.0

    for r in readings:
        lat = r.get("lat")
        lng = r.get("lng")
        if lat is None or lng is None:
            continue

        # Use signal_pct as weight (squared to emphasize strong signals)
        weight = (r.get("signal_pct", 0) / 100.0) ** 2
        if weight < 0.001:
            continue

        weighted_lat += lat * weight
        weighted_lng += lng * weight
        total_weight += weight

    if total_weight < 0.001:
        return None

    est_lat = weighted_lat / total_weight
    est_lng = weighted_lng / total_weight

    # Compute confidence radius from spread of readings
    distances_m = []
    for r in readings:
        if r.get("lat") and r.get("lng"):
            d = _haversine(est_lat, est_lng, r["lat"], r["lng"])
            distances_m.append(d)

    confidence_radius = max(distances_m) if distances_m else 0

    return {
        "lat": est_lat,
        "lng": est_lng,
        "confidence_radius_m": round(confidence_radius, 1),
        "num_readings": len(readings),
    }


def trilaterate(readings: list[dict], path_loss_exp: float = PATH_LOSS_EXPONENT) -> Optional[dict]:
    """Estimate AP location using trilateration with distance estimates.

    Uses log-distance path loss model to estimate distances, then
    finds the point minimizing weighted distance errors.
    """
    valid = [r for r in readings if r.get("lat") is not None and r.get("lng") is not None]
    if len(valid) < 3:
        return weighted_centroid(valid) if len(valid) >= 2 else None

    # Estimate distances from signal strength
    points = []
    for r in valid:
        dbm = r.get("signal_dbm", -100)
        dist = dbm_to_distance(dbm, path_loss_exp)
        points.append({
            "lat": r["lat"],
            "lng": r["lng"],
            "estimated_distance_m": dist,
            "signal_dbm": dbm,
            "signal_pct": r.get("signal_pct", 0),
        })

    # Weighted least squares via grid search around weighted centroid
    centroid = weighted_centroid(valid)
    if not centroid:
        return None

    best_lat = centroid["lat"]
    best_lng = centroid["lng"]
    best_error = float("inf")

    # Search in progressively finer grids
    search_radius = 0.002  # ~200m in degrees
    for _ in range(4):
        step = search_radius / 10
        for lat_offset in range(-10, 11):
            for lng_offset in range(-10, 11):
                test_lat = centroid["lat"] + lat_offset * step
                test_lng = centroid["lng"] + lng_offset * step

                error = 0.0
                for p in points:
                    actual_dist = _haversine(test_lat, test_lng, p["lat"], p["lng"])
                    est_dist = p["estimated_distance_m"]
                    weight = (p["signal_pct"] / 100.0) ** 2
                    error += weight * (actual_dist - est_dist) ** 2

                if error < best_error:
                    best_error = error
                    best_lat = test_lat
                    best_lng = test_lng

        # Narrow search around best point
        centroid["lat"] = best_lat
        centroid["lng"] = best_lng
        search_radius /= 5

    return {
        "lat": best_lat,
        "lng": best_lng,
        "confidence_radius_m": round(math.sqrt(best_error / len(points)), 1),
        "num_readings": len(valid),
        "method": "trilateration",
        "points": points,
    }


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in meters between two lat/lng points."""
    R = 6371000  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c
