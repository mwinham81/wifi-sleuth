"""SQLite database for storing WiFi scan time-series data."""

import sqlite3
import os
import time
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "wifisleuth.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            lat REAL,
            lng REAL,
            ssid TEXT NOT NULL,
            bssid TEXT NOT NULL,
            channel INTEGER,
            band TEXT,
            frequency_mhz INTEGER,
            signal_pct INTEGER,
            signal_dbm INTEGER,
            auth TEXT,
            encryption TEXT,
            radio_type TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_scans_bssid ON scans(bssid)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_scans_timestamp ON scans(timestamp)
    """)
    conn.commit()
    conn.close()


def save_scan(networks: list[dict], lat: Optional[float] = None, lng: Optional[float] = None):
    """Save a batch of network scan results."""
    ts = time.time()
    conn = get_connection()
    conn.executemany(
        """INSERT INTO scans (timestamp, lat, lng, ssid, bssid, channel, band,
           frequency_mhz, signal_pct, signal_dbm, auth, encryption, radio_type)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(ts, lat, lng, n["ssid"], n["bssid"], n["channel"], n["band"],
          n["frequency_mhz"], n["signal_pct"], n["signal_dbm"],
          n["auth"], n["encryption"], n.get("radio_type", ""))
         for n in networks],
    )
    conn.commit()
    conn.close()
    return ts


def get_timeseries(bssid: str, since: Optional[float] = None) -> list[dict]:
    """Get signal strength over time for a BSSID."""
    conn = get_connection()
    if since:
        rows = conn.execute(
            "SELECT timestamp, signal_pct, signal_dbm, lat, lng FROM scans "
            "WHERE bssid = ? AND timestamp >= ? ORDER BY timestamp",
            (bssid, since),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT timestamp, signal_pct, signal_dbm, lat, lng FROM scans "
            "WHERE bssid = ? ORDER BY timestamp",
            (bssid,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_geotagged(bssid: str) -> list[dict]:
    """Get all geotagged readings for a BSSID (only those with lat/lng)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT timestamp, lat, lng, signal_pct, signal_dbm FROM scans "
        "WHERE bssid = ? AND lat IS NOT NULL AND lng IS NOT NULL "
        "ORDER BY timestamp",
        (bssid,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_bssids() -> list[dict]:
    """Get distinct BSSIDs with their latest info."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT bssid, ssid, band, channel,
           MAX(timestamp) as last_seen,
           COUNT(*) as reading_count
           FROM scans GROUP BY bssid ORDER BY last_seen DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_history(limit: int = 5000) -> list[dict]:
    """Get all recorded scans for map display."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT timestamp, lat, lng, ssid, bssid, channel, band, "
        "signal_pct, signal_dbm FROM scans "
        "WHERE lat IS NOT NULL AND lng IS NOT NULL "
        "ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def clear_data():
    """Clear all scan data."""
    conn = get_connection()
    conn.execute("DELETE FROM scans")
    conn.commit()
    conn.close()


# Initialize on import
init_db()
