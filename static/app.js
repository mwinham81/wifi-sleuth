// WiFiSleuth Frontend

(function () {
    "use strict";

    // ── State ──────────────────────────────────────────────
    let networks = [];          // current display list (includes ghosts)
    let networkMap = {};        // bssid -> {network data + _lastSeen + _ghost}
    const GHOST_TIMEOUT = 15;   // seconds before ghost rows are removed
    let sortKey = "signal_pct";
    let sortAsc = false;
    let autoRefreshTimer = null;
    let recording = false;
    let recordingTimer = null;
    let timeseriesData = {};  // bssid -> [{timestamp, signal_pct, signal_dbm}]
    let map = null;
    let mapMarkers = [];
    let triangleMarker = null;
    let phoneMarker = null;

    // ── Tab Switching ──────────────────────────────────────
    document.querySelectorAll(".tab").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
            document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
            btn.classList.add("active");
            document.getElementById(btn.dataset.tab).classList.add("active");
            if (btn.dataset.tab === "signal-map") initMap();
            if (btn.dataset.tab === "channel-map") updateChannelCharts();
        });
    });

    // ── GPS Streaming (phone sends location) ───────────────
    function startGPS() {
        if (!navigator.geolocation) return;
        navigator.geolocation.watchPosition(
            pos => {
                fetch("/api/location", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        lat: pos.coords.latitude,
                        lng: pos.coords.longitude,
                        accuracy: pos.coords.accuracy,
                    }),
                }).catch(() => { });
            },
            () => { },
            { enableHighAccuracy: true, maximumAge: 2000, timeout: 5000 }
        );
    }
    startGPS();

    // Poll GPS status
    async function updateGPSStatus() {
        try {
            const res = await fetch("/api/gps");
            const gps = await res.json();
            const el = document.getElementById("gps-status");
            if (gps.fresh) {
                el.textContent = `GPS: ${gps.lat?.toFixed(5)}, ${gps.lng?.toFixed(5)}`;
                el.className = "status-badge connected";
                if (map && gps.lat && gps.lng) updatePhoneMarker(gps.lat, gps.lng, gps.accuracy);
            } else if (gps.lat) {
                el.textContent = `GPS: stale (${gps.age_seconds}s)`;
                el.className = "status-badge stale";
            } else {
                el.textContent = "GPS: no signal";
                el.className = "status-badge disconnected";
            }
        } catch { }
    }
    setInterval(updateGPSStatus, 2000);

    // ── Live Scan ──────────────────────────────────────────
    async function doScan() {
        try {
            const res = await fetch("/api/scan");
            const data = await res.json();
            const now = data.timestamp;
            const liveBssids = new Set();

            // Update or add live networks
            data.networks.forEach(n => {
                liveBssids.add(n.bssid);
                networkMap[n.bssid] = { ...n, _lastSeen: now, _ghost: false };
            });

            // Ghost any previously-seen network that wasn't in this scan
            Object.keys(networkMap).forEach(bssid => {
                if (!liveBssids.has(bssid)) {
                    const entry = networkMap[bssid];
                    if (!entry._ghost) {
                        // Just disappeared: mark as ghost, drop signal to 0
                        entry._ghost = true;
                        entry._ghostedAt = now;
                        entry.signal_pct = 0;
                        entry.signal_dbm = -100;
                    } else if (now - entry._ghostedAt > GHOST_TIMEOUT) {
                        // Ghost expired: remove entirely
                        delete networkMap[bssid];
                    }
                }
            });

            // Build display list
            networks = Object.values(networkMap);
            const liveCount = networks.filter(n => !n._ghost).length;
            const ghostCount = networks.filter(n => n._ghost).length;
            document.getElementById("network-count").textContent =
                `Networks: ${liveCount}` + (ghostCount ? ` (+${ghostCount} gone)` : "");
            document.getElementById("scan-status").textContent =
                `Scan: ${new Date(now * 1000).toLocaleTimeString()}`;
            renderTable();
            updateBSSIDSelectors();
        } catch (e) {
            document.getElementById("scan-status").textContent = "Scan: error";
        }
    }

    function renderTable() {
        const filter = document.getElementById("band-filter").value;
        let filtered = filter === "all" ? networks : networks.filter(n => n.band === filter);

        filtered.sort((a, b) => {
            let va = a[sortKey], vb = b[sortKey];
            if (typeof va === "string") va = va.toLowerCase();
            if (typeof vb === "string") vb = vb.toLowerCase();
            if (va < vb) return sortAsc ? -1 : 1;
            if (va > vb) return sortAsc ? 1 : -1;
            return 0;
        });

        const tbody = document.getElementById("scan-tbody");
        tbody.innerHTML = filtered.map(n => {
            const sigClass = n._ghost ? "signal-ghost" :
                n.signal_pct >= 70 ? "signal-strong" :
                n.signal_pct >= 50 ? "signal-medium" :
                    n.signal_pct >= 30 ? "signal-weak" : "signal-very-weak";
            const bandClass = n.band === "2.4 GHz" ? "band-24" : "band-5";
            const ghostClass = n._ghost ? " ghost-row" : "";
            return `<tr class="${bandClass}${ghostClass}">
                <td>${escHtml(n.ssid)}</td>
                <td><code>${n.bssid}</code></td>
                <td>${n.band}</td>
                <td>${n.channel}</td>
                <td>${n.frequency_mhz}</td>
                <td><span class="signal-bar ${sigClass}" style="width:${n._ghost ? 0 : n.signal_pct * 0.8}px"></span>${n._ghost ? "0%" : n.signal_pct + "%"}</td>
                <td>${n._ghost ? "--" : n.signal_dbm}</td>
                <td>${escHtml(n.auth)}</td>
            </tr>`;
        }).join("");
    }

    function escHtml(s) {
        const d = document.createElement("div");
        d.textContent = s;
        return d.innerHTML;
    }

    // Table sorting
    document.querySelectorAll("#scan-table th[data-sort]").forEach(th => {
        th.addEventListener("click", () => {
            const key = th.dataset.sort;
            if (sortKey === key) sortAsc = !sortAsc;
            else { sortKey = key; sortAsc = true; }
            renderTable();
        });
    });

    document.getElementById("band-filter").addEventListener("change", renderTable);
    document.getElementById("btn-scan-now").addEventListener("click", doScan);

    // Auto-refresh
    function toggleAutoRefresh() {
        if (document.getElementById("auto-refresh").checked) {
            if (!autoRefreshTimer) autoRefreshTimer = setInterval(doScan, 3000);
        } else {
            clearInterval(autoRefreshTimer);
            autoRefreshTimer = null;
        }
    }
    document.getElementById("auto-refresh").addEventListener("change", toggleAutoRefresh);

    // ── BSSID Selectors ────────────────────────────────────
    function updateBSSIDSelectors() {
        const seen = new Set();
        const options = networks
            .filter(n => { if (seen.has(n.bssid)) return false; seen.add(n.bssid); return true; })
            .sort((a, b) => b.signal_pct - a.signal_pct)
            .map(n => `<option value="${n.bssid}">${escHtml(n.ssid)} (${n.bssid}) ${n.band} ch${n.channel} ${n.signal_pct}%</option>`)
            .join("");

        const tsSelect = document.getElementById("ts-bssid-select");
        const prevTs = Array.from(tsSelect.selectedOptions).map(o => o.value);
        tsSelect.innerHTML = options;
        prevTs.forEach(v => { const o = tsSelect.querySelector(`[value="${v}"]`); if (o) o.selected = true; });

        const mapSelect = document.getElementById("map-bssid-select");
        const prevMap = mapSelect.value;
        mapSelect.innerHTML = '<option value="">-- Select Network --</option>' + options;
        if (prevMap) mapSelect.value = prevMap;
    }

    // ── Channel Map Charts ─────────────────────────────────
    const plotlyLayout = {
        paper_bgcolor: "#1a1d27",
        plot_bgcolor: "#1a1d27",
        font: { color: "#8b90a0", size: 11 },
        margin: { t: 30, b: 40, l: 50, r: 20 },
        xaxis: { gridcolor: "#2d3140", title: "Channel" },
        yaxis: { gridcolor: "#2d3140", title: "Signal %", range: [0, 105] },
        barmode: "group",
        showlegend: true,
        legend: { orientation: "h", y: 1.12 },
    };

    function updateChannelCharts() {
        // 2.4 GHz
        const nets24 = networks.filter(n => n.band === "2.4 GHz");
        const channels24 = Array.from({ length: 14 }, (_, i) => i + 1);
        const traces24 = [];

        // Group by SSID for coloring
        const ssidGroups24 = {};
        nets24.forEach(n => {
            const key = n.ssid || n.bssid;
            if (!ssidGroups24[key]) ssidGroups24[key] = [];
            ssidGroups24[key].push(n);
        });

        Object.entries(ssidGroups24).forEach(([ssid, nets]) => {
            const x = [], y = [], text = [];
            nets.forEach(n => {
                x.push(n.channel);
                y.push(n.signal_pct);
                text.push(`${ssid}<br>${n.bssid}<br>${n.signal_pct}% (${n.signal_dbm} dBm)`);
            });
            traces24.push({
                x, y, text, type: "bar", name: ssid,
                hovertemplate: "%{text}<extra></extra>",
                width: 0.8,
            });
        });

        Plotly.react("chart-24ghz", traces24.length ? traces24 : [{
            x: channels24, y: channels24.map(() => 0), type: "bar",
        }], {
            ...plotlyLayout,
            xaxis: { ...plotlyLayout.xaxis, tickvals: channels24, dtick: 1 },
        }, { responsive: true });

        // 5 GHz
        const nets5 = networks.filter(n => n.band === "5 GHz");
        const ssidGroups5 = {};
        nets5.forEach(n => {
            const key = n.ssid || n.bssid;
            if (!ssidGroups5[key]) ssidGroups5[key] = [];
            ssidGroups5[key].push(n);
        });

        const traces5 = [];
        Object.entries(ssidGroups5).forEach(([ssid, nets]) => {
            const x = [], y = [], text = [];
            nets.forEach(n => {
                x.push(n.channel);
                y.push(n.signal_pct);
                text.push(`${ssid}<br>${n.bssid}<br>${n.signal_pct}% (${n.signal_dbm} dBm)`);
            });
            traces5.push({
                x, y, text, type: "bar", name: ssid,
                hovertemplate: "%{text}<extra></extra>",
                width: 2,
            });
        });

        const ch5 = [36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 140, 144, 149, 153, 157, 161, 165];
        Plotly.react("chart-5ghz", traces5.length ? traces5 : [{
            x: ch5, y: ch5.map(() => 0), type: "bar",
        }], {
            ...plotlyLayout,
            xaxis: { ...plotlyLayout.xaxis, tickvals: ch5, tickangle: -45 },
        }, { responsive: true });
    }

    // ── Time Series ────────────────────────────────────────
    const btnRecord = document.getElementById("btn-record");
    btnRecord.addEventListener("click", async () => {
        recording = !recording;
        await fetch("/api/recording", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ active: recording }),
        });
        btnRecord.textContent = recording ? "Stop Recording" : "Start Recording";
        btnRecord.classList.toggle("recording", recording);
        document.getElementById("record-status").textContent = recording ? "Recording..." : "";

        if (recording) {
            timeseriesData = {};
            recordingTimer = setInterval(recordTimeseriesPoint, 2000);
        } else {
            clearInterval(recordingTimer);
            recordingTimer = null;
        }
    });

    async function recordTimeseriesPoint() {
        // Trigger a recorded scan
        try {
            await fetch("/api/record", { method: "POST" });
        } catch { }

        // Fetch timeseries for selected BSSIDs
        const selected = Array.from(document.getElementById("ts-bssid-select").selectedOptions).map(o => o.value);
        for (const bssid of selected) {
            try {
                const res = await fetch(`/api/timeseries/${encodeURIComponent(bssid)}`);
                const data = await res.json();
                timeseriesData[bssid] = data.data;
            } catch { }
        }
        updateTimeseriesChart();
    }

    function updateTimeseriesChart() {
        const traces = Object.entries(timeseriesData).map(([bssid, points]) => {
            const net = networks.find(n => n.bssid === bssid);
            const label = net ? `${net.ssid} (${bssid.slice(-8)})` : bssid;
            return {
                x: points.map(p => new Date(p.timestamp * 1000)),
                y: points.map(p => p.signal_pct),
                type: "scatter",
                mode: "lines+markers",
                name: label,
                line: { width: 2 },
                marker: { size: 4 },
            };
        });

        Plotly.react("chart-timeseries", traces.length ? traces : [{
            x: [], y: [], type: "scatter",
        }], {
            ...plotlyLayout,
            xaxis: { ...plotlyLayout.xaxis, title: "Time", type: "date" },
            yaxis: { ...plotlyLayout.yaxis, title: "Signal %", range: [0, 105] },
        }, { responsive: true });
    }

    // ── Signal Map ─────────────────────────────────────────
    function initMap() {
        if (map) return;
        map = L.map("map-container").setView([39.8283, -98.5795], 4);  // US center default
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            attribution: "&copy; OpenStreetMap contributors",
            maxZoom: 19,
        }).addTo(map);
        setTimeout(() => map.invalidateSize(), 200);
    }

    function updatePhoneMarker(lat, lng, accuracy) {
        if (!map) return;
        if (phoneMarker) {
            phoneMarker.setLatLng([lat, lng]);
        } else {
            phoneMarker = L.circleMarker([lat, lng], {
                radius: 8, fillColor: "#4f8cff", color: "#fff",
                weight: 2, fillOpacity: 0.9,
            }).addTo(map).bindPopup("Phone GPS");
            map.setView([lat, lng], 17);
        }
    }

    document.getElementById("btn-record-point").addEventListener("click", async () => {
        const info = document.getElementById("map-info");
        info.textContent = "Recording...";
        try {
            const res = await fetch("/api/record", { method: "POST" });
            const data = await res.json();
            if (data.geotagged) {
                info.textContent = `Recorded ${data.network_count} networks at (${data.lat.toFixed(5)}, ${data.lng.toFixed(5)})`;
                loadMapPoints();
            } else {
                info.textContent = "No GPS available - point not geotagged. Open this page on your phone.";
            }
        } catch (e) {
            info.textContent = "Error recording point.";
        }
    });

    async function loadMapPoints() {
        const bssid = document.getElementById("map-bssid-select").value;
        try {
            const res = await fetch("/api/history");
            const data = await res.json();

            // Clear old markers
            mapMarkers.forEach(m => map.removeLayer(m));
            mapMarkers = [];

            const scans = bssid ? data.scans.filter(s => s.bssid === bssid) : data.scans;
            const uniquePoints = {};

            scans.forEach(s => {
                const key = `${s.lat.toFixed(6)},${s.lng.toFixed(6)},${s.bssid}`;
                if (!uniquePoints[key] || s.signal_pct > uniquePoints[key].signal_pct) {
                    uniquePoints[key] = s;
                }
            });

            Object.values(uniquePoints).forEach(s => {
                const color = s.signal_pct >= 70 ? "#34d399" :
                    s.signal_pct >= 50 ? "#fbbf24" :
                        s.signal_pct >= 30 ? "#fb923c" : "#f87171";
                const marker = L.circleMarker([s.lat, s.lng], {
                    radius: 6 + (s.signal_pct / 20),
                    fillColor: color,
                    color: "#fff",
                    weight: 1,
                    fillOpacity: 0.8,
                }).addTo(map).bindPopup(
                    `<b>${s.ssid}</b><br>${s.bssid}<br>${s.band} ch${s.channel}<br>Signal: ${s.signal_pct}% (${s.signal_dbm} dBm)`
                );
                mapMarkers.push(marker);
            });

            if (mapMarkers.length) {
                const group = L.featureGroup(mapMarkers);
                map.fitBounds(group.getBounds().pad(0.2));
            }
        } catch { }
    }

    document.getElementById("map-bssid-select").addEventListener("change", loadMapPoints);

    document.getElementById("btn-triangulate").addEventListener("click", async () => {
        const bssid = document.getElementById("map-bssid-select").value;
        const info = document.getElementById("map-info");
        if (!bssid) { info.textContent = "Select a network first."; return; }

        try {
            const res = await fetch(`/api/triangulate/${encodeURIComponent(bssid)}`);
            if (!res.ok) {
                const err = await res.json();
                info.textContent = err.error || "Triangulation failed.";
                return;
            }
            const data = await res.json();
            info.textContent = `Estimated: (${data.lat.toFixed(6)}, ${data.lng.toFixed(6)}) ~${data.confidence_radius_m}m radius, ${data.num_readings} readings`;

            if (triangleMarker) map.removeLayer(triangleMarker);
            triangleMarker = L.marker([data.lat, data.lng], {
                icon: L.divIcon({
                    className: "",
                    html: '<div style="background:#f87171;color:#fff;border-radius:50%;width:24px;height:24px;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:14px;border:2px solid #fff;">AP</div>',
                    iconSize: [24, 24],
                    iconAnchor: [12, 12],
                }),
            }).addTo(map).bindPopup(
                `<b>Estimated AP Location</b><br>Confidence: ~${data.confidence_radius_m}m<br>Readings: ${data.num_readings}`
            ).openPopup();

            // Draw confidence circle
            const circle = L.circle([data.lat, data.lng], {
                radius: data.confidence_radius_m,
                color: "#f87171",
                fillColor: "#f87171",
                fillOpacity: 0.1,
                weight: 1,
                dashArray: "5,5",
            }).addTo(map);
            mapMarkers.push(circle);
        } catch {
            info.textContent = "Triangulation error.";
        }
    });

    document.getElementById("btn-clear-data").addEventListener("click", async () => {
        if (!confirm("Clear all recorded scan data?")) return;
        await fetch("/api/clear", { method: "POST" });
        mapMarkers.forEach(m => map.removeLayer(m));
        mapMarkers = [];
        if (triangleMarker) { map.removeLayer(triangleMarker); triangleMarker = null; }
        document.getElementById("map-info").textContent = "Data cleared.";
    });

    // ── Init ───────────────────────────────────────────────
    doScan();
    toggleAutoRefresh();
})();
