/* ==========================================
   NEXUS IoT - Dashboard Logic (v4.8)
   Chart absolute positioning + anti-tumpuk + auto-scroll + clamp.
   ========================================== */

(function() {
    'use strict';

const state = {
    devices: [],
    attendance: [],
    currentSection: 'dashboard',
    charts: [],
    chartIdCounter: 0,
    globalTimeMinutes: 1440,
    deviceFilter: 'all',
    deviceFilterFull: 'all',
    mapPreview: null,
    mapFull: null,
    markerCluster: null,
    marker: null,
    selectedLat: null,
    selectedLng: null,
    selectedMapDeviceId: null,
    refreshTimeout: null,
    autoRefreshInterval: null,
    dashboardInterval: null,
    attendanceInterval: null,
    attendanceLastId: 0,
    deviceSearchTerm: '',
    alertSearchTerm: '',        // ← TAMBAH INI
    analyticsTabs: [],
    currentTabId: null,
    isInitialized: false,
    dashboardSlug: null,
    mapFilter: 'all',
    mapSearchTerm: '',
    mapHasUnsavedChange: false,
    activityRefreshInterval: null,
    markerMap: new Map(),
    attendanceView: 'report',
    deleteTarget: null,
    canvasHeight: 720,
};

    const CHART_FONT = "'Inter', -apple-system, sans-serif";
    const CHART_COLORS = ['#c97a7a', '#7a9dc4', '#5fb587', '#d99a56', '#a88cc4', '#6ab8b8', '#b8a85a', '#8cb069'];
    const GAP = 12;
    const PADDING = 16;
    const DEFAULT_W = 440;
    const DEFAULT_H = 320;
    const MIN_W = 240;
    const MIN_H = 160;

    const DATA_KEYS = {
        temperature: { label: 'Suhu', unit: '°C', color: '#c97a7a' },
        humidity: { label: 'Kelembaban', unit: '%', color: '#7a9dc4' },
        gas_level: { label: 'Gas', unit: '%', color: '#d99a56' },
        smoke: { label: 'Asap', unit: 'ppm', color: '#a88cc4' },
        motion: { label: 'Gerakan', unit: '', color: '#6ab8b8' },
        rfid: { label: 'RFID', unit: '', color: '#8cb069' },
        moisture: { label: 'K. Tanah', unit: '%', color: '#6aa8c4' },
        lux: { label: 'Cahaya', unit: 'lux', color: '#b8a85a' },
        co2: { label: 'CO2', unit: 'ppm', color: '#5fb587' },
        voc: { label: 'VOC', unit: 'ppb', color: '#a855f7' },
        air_quality: { label: 'Kualitas Udara', unit: 'AQI', color: '#3b82f6' },
    };

    const STORAGE_KEYS = {
        THEME: 'nexus-theme',
        GLOBAL_TIME: 'nexus-global-time',
        LAST_SECTION: 'nexus-last-section',
        BACK_URL: 'nexus_back_url',
        CURRENT_TAB: 'nexus-current-tab',
        CHART_LAYOUT_PREFIX: 'nexus-chart-layout-',
        CANVAS_HEIGHT: 'nexus-chart-canvas-height',
    };

    const DASHBOARD_SECTIONS = ['dashboard', 'map', 'graph', 'attendance', 'devices', 'alerts'];

    const $ = (id) => document.getElementById(id);
    const $$ = (sel) => document.querySelectorAll(sel);

    // ==========================================
    // HELPERS
    // ==========================================
    function escapeHtml(str) {
        return String(str ?? '')
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }
    function parseDate(iso) {
        if (!iso) return null;
        const s = String(iso).trim();
        if (/[+-]\d{2}:\d{2}$/.test(s) || s.endsWith('Z')) { const d = new Date(s); return isNaN(d.getTime()) ? null : d; }
        if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(s)) { const d = new Date(s.replace(' ', 'T') + '+07:00'); return isNaN(d.getTime()) ? null : d; }
        if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(s)) { const d = new Date(s + '+07:00'); return isNaN(d.getTime()) ? null : d; }
        if (/^\d{4}-\d{2}-\d{2}$/.test(s)) { const d = new Date(s + 'T00:00:00+07:00'); return isNaN(d.getTime()) ? null : d; }
        const d = new Date(s); return isNaN(d.getTime()) ? null : d;
    }
    function formatUptime(s) {
        if (!s && s !== 0) return '-';
        s = parseInt(s) || 0;
        if (s < 60) return `${s}s`;
        const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
        if (d > 0) return `${d}h ${h}j`;
        if (h > 0) return `${h}j ${m}m`;
        return `${m}m`;
    }
    function formatTime(iso) {
        const d = parseDate(iso); if (!d) return '-';
        try { return d.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Jakarta' }); } catch (e) { return '-'; }
    }
    function formatDateTimeSplit(iso) {
        const d = parseDate(iso); if (!d) return { date: '-', time: '-' };
        try {
            return {
                date: d.toLocaleDateString('id-ID', { day: '2-digit', month: 'short', timeZone: 'Asia/Jakarta' }),
                time: d.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'Asia/Jakarta' }),
            };
        } catch (e) { return { date: '-', time: '-' }; }
    }
    function formatRelativeTime(date) {
        if (!(date instanceof Date)) return '-';
        const diff = (Date.now() - date.getTime()) / 1000;
        if (diff < 0) return 'baru saja';
        if (diff < 60) return 'baru saja';
        if (diff < 3600) return `${Math.floor(diff / 60)} mnt lalu`;
        if (diff < 86400) return `${Math.floor(diff / 3600)} jam lalu`;
        if (diff < 604800) return `${Math.floor(diff / 86400)} hari lalu`;
        return date.toLocaleDateString('id-ID', { day: '2-digit', month: 'short' });
    }
    function formatTimeRange(minutes) {
        if (minutes <= 0) return '0 menit';
        if (minutes < 60) return `${minutes} menit`;
        if (minutes < 1440) return `${Math.round(minutes / 60)} jam`;
        if (minutes < 10080) return `${Math.round(minutes / 1440)} hari`;
        if (minutes < 43200) return `${Math.round(minutes / 10080)} minggu`;
        return `${Math.round(minutes / 43200)} bulan`;
    }
    function getChartColors() {
        const isLight = document.documentElement.getAttribute('data-theme') === 'light';
        return {
            gridColor: isLight ? 'rgba(0,0,0,0.08)' : 'rgba(255,255,255,0.06)',
            labelColor: isLight ? 'rgba(74,84,98,0.75)' : 'rgba(168,176,188,0.7)',
            legendColor: isLight ? 'rgba(74,84,98,0.9)' : 'rgba(168,176,188,0.9)',
            tooltipBg: isLight ? 'rgba(255,255,255,0.98)' : 'rgba(28,32,39,0.98)',
            tooltipBorder: isLight ? 'rgba(0,0,0,0.08)' : 'rgba(255,255,255,0.08)',
            tooltipTitleColor: isLight ? '#1a1d23' : '#e8ebef',
            tooltipBodyColor: isLight ? 'rgba(74,84,98,0.9)' : 'rgba(168,176,188,0.9)',
            pointBorderColor: isLight ? '#fff' : '#1c2027',
        };
    }
    function downsampleHistory(arr, max) {
        if (!Array.isArray(arr) || arr.length <= max) return arr;
        const step = arr.length / max;
        const out = [];
        for (let i = 0; i < max; i++) out.push(arr[Math.floor(i * step)]);
        if (out[out.length - 1] !== arr[arr.length - 1]) out.push(arr[arr.length - 1]);
        return out;
    }
    function showToast(msg, type) { if (window.showToast) window.showToast(msg, type); }
    function lockBodyScroll() { document.body.classList.add('modal-open'); }
    function unlockBodyScrollIfNoModal() {
        if (!document.querySelector('.modal.active')) document.body.classList.remove('modal-open');
    }
    function openModal(id) { const el = $(id); if (el) { el.classList.add('active'); lockBodyScroll(); } }
    function closeModal(id) { const el = $(id); if (el) el.classList.remove('active'); unlockBodyScrollIfNoModal(); }
    function registerMapInstance(map) {
        if (!window.__nexusMaps) window.__nexusMaps = [];
        if (!window.__nexusMaps.includes(map)) window.__nexusMaps.push(map);
    }
    function getSectionFromHash() {
        const hash = (window.location.hash || '').replace('#', '').trim();
        return DASHBOARD_SECTIONS.includes(hash) ? hash : 'dashboard';
    }
    function updateHash(section, replace = false) {
        if (!DASHBOARD_SECTIONS.includes(section)) return;
        const newHash = `#${section}`;
        if (window.location.hash === newHash) return;
        if (replace) history.replaceState(null, '', newHash);
        else history.pushState(null, '', newHash);
    }

    // ==========================================
    // SECTION NAV
    // ==========================================
    function showSection(section, skipHistory = false) {
        if (!DASHBOARD_SECTIONS.includes(section)) section = 'dashboard';
        state.currentSection = section;

        DASHBOARD_SECTIONS.forEach(s => {
            const el = $(s + 'Section');
            if (!el) return;
            if (s === section) { el.style.display = 'block'; el.removeAttribute('hidden'); }
            else { el.style.display = 'none'; el.setAttribute('hidden', ''); }
        });

        const titles = { dashboard: 'Dashboard', map: 'Peta Interaktif', graph: 'Analitik Sensor', devices: 'Manajemen Perangkat', attendance: 'Absensi', alerts: 'Alert Center' };
        const titleEl = $('pageTitle');
        if (titleEl) titleEl.textContent = titles[section] || 'Dashboard';

        $$('.sidebar-nav .nav-item[data-section]').forEach(item => {
            item.classList.toggle('active', item.getAttribute('data-section') === section);
        });

        const searchBox = document.querySelector('.search-box');
        const searchInput = $('searchInput');
        const noSearch = ['map', 'graph'];   // ← 'alerts' dihapus
        if (searchBox) searchBox.style.display = noSearch.includes(section) ? 'none' : '';
        if (searchInput) {
            if (section === 'alerts') {
                searchInput.value = state.alertSearchTerm || '';
                searchInput.placeholder = 'Cari alert...';
            } else if (section === 'attendance') {
                searchInput.value = state.deviceSearchTerm || '';
                searchInput.placeholder = 'Cari nama/UID/perangkat...';
            } else {
                searchInput.value = state.deviceSearchTerm || '';
                searchInput.placeholder = 'Cari perangkat...';
            }
        }

        if (section !== 'attendance') stopAttendancePolling();
        if (section === 'attendance') { loadAttendance(); startAttendancePolling(); }
        if (section === 'map') {
            setTimeout(() => {
                if (!state.mapFull) initFullMap();
                loadMarkers(state.mapFull, true);
                renderMapDeviceList();
                if (state.mapFull) state.mapFull.invalidateSize();
                updateMapSelectedBanner();
            }, 100);
        }
        if (section === 'dashboard') {
            setTimeout(() => { if (state.mapPreview) state.mapPreview.invalidateSize(); loadActivityFeed(); }, 100);
        }
        if (section === 'graph') {
            setTimeout(() => {
                loadAnalyticsTabs();
                refreshAllCharts();
                setTimeout(() => {
                    state.charts.forEach(c => { if (c.chartInstance) try { c.chartInstance.resize(); } catch (e) {} });
                }, 200);
            }, 100);
        }
        if (section === 'alerts' && window.NexusAlerts && typeof window.NexusAlerts.load === 'function') {
            if (window.NexusAlerts.setSearch) {
                window.NexusAlerts.setSearch(state.alertSearchTerm || '');
            }
            window.NexusAlerts.load();
        }

        try { sessionStorage.setItem(STORAGE_KEYS.LAST_SECTION, section); } catch (e) {}
        if (!skipHistory) updateHash(section);
    }

    function updateDateTime() {
        const now = new Date();
        const dateEl = $('currentDate'), timeEl = $('currentTime');
        if (dateEl) dateEl.textContent = now.toLocaleDateString('id-ID', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric', timeZone: 'Asia/Jakarta' });
        if (timeEl) timeEl.textContent = now.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'Asia/Jakarta' }) + ' WIB';
    }

    // ==========================================
    // DASHBOARD LOAD
    // ==========================================
    async function loadDashboard() {
        const result = await API.getDashboard();
        if (!result.success) {
            if (result.status === 401) { showToast('Session expired', 'warning'); setTimeout(() => window.location.href = '/login', 1500); return; }
            const tbody = $('deviceTableBody');
            if (tbody) tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:40px;color:var(--accent-crit);">Gagal memuat</td></tr>`;
            const tbodyFull = $('deviceTableBodyFull');
            if (tbodyFull) tbodyFull.innerHTML = `<tr><td colspan="9" style="text-align:center;padding:40px;color:var(--accent-crit);">Gagal memuat</td></tr>`;
            return;
        }
        const { summary, devices } = result.data;
        state.devices = Array.isArray(devices) ? devices : [];
        const setText = (id, val) => { const el = $(id); if (el) el.textContent = val; };
        setText('totalDevices', summary.total_devices);
        setText('onlineDevices', summary.online_devices);
        setText('offlineDevices', summary.offline_devices);
        setText('activeAlerts', summary.active_alerts || 0);
        setText('deviceBadge', summary.total_devices);
        setText('alertBadge', summary.active_alerts || 0);
        updateHealthRing(summary);
        loadMarkers(state.mapPreview);
        if (state.mapFull) loadMarkers(state.mapFull, true);
        updateFilterCounts();
        renderFilteredDevices();
        renderFilteredDevicesFull();
        renderMapDeviceList();
        loadActivityFeed();
    }

    function updateHealthRing(summary) {
        const healthy = summary.online_devices ?? 0;
        const total = summary.total_devices ?? 0;
        const pct = total > 0 ? Math.round((healthy / total) * 100) : 0;
        const circ = 2 * Math.PI * 63;
        const offset = circ - (pct / 100) * circ;
        const ring = $('healthRingProgress');
        if (!ring) return;
        ring.setAttribute('stroke-dasharray', circ.toFixed(1));
        ring.style.strokeDashoffset = offset;
        const pctEl = $('ringPct'); if (pctEl) pctEl.textContent = pct + '%';
        const capEl = $('ringCaption'); if (capEl) capEl.textContent = `${healthy} / ${total} perangkat online`;
    }

    // ==========================================
    // ACTIVITY FEED
    // ==========================================
    async function loadActivityFeed() {
        const container = $('activityList');
        if (!container) return;
        try {
            const alertsRes = await API.getAlertsAll({ limit: 20 });
            const events = [];
            if (alertsRes.success && Array.isArray(alertsRes.data.alerts)) {
                alertsRes.data.alerts.slice(0, 15).forEach(a => {
                    events.push({
                        type: 'alert', severity: a.severity || 'info',
                        title: a.device_name || a.device_id,
                        message: a.message || a.alert_type,
                        timestamp: a.created_at, deviceId: a.device_id,
                    });
                });
            }
            state.devices.forEach(d => {
                if (!d.last_seen) return;
                events.push({
                    type: d.status === 'online' ? 'online' : 'offline',
                    severity: d.status === 'online' ? 'online' : 'offline',
                    title: d.device_name,
                    message: d.status === 'online' ? 'Baru saja online' : 'Terakhir terlihat',
                    timestamp: d.last_seen, deviceId: d.device_id,
                });
            });
            events.sort((a, b) => {
                const da = parseDate(a.timestamp), db = parseDate(b.timestamp);
                if (!da || !db) return 0;
                return db - da;
            });
            const top = events.slice(0, 12);
            if (top.length === 0) { container.innerHTML = `<div class="activity-empty">Belum ada aktivitas</div>`; return; }
            const iconMap = {
                danger: 'fa-fire',
                warning: 'fa-triangle-exclamation',
                info: 'fa-circle-info',
                online: 'fa-circle-check',
                offline: 'fa-power-off',
                healthy: 'fa-circle-check'
            };
            container.innerHTML = top.map(ev => {
                const sev = ev.severity || 'info';
                const icon = iconMap[sev] || 'fa-bell';
                const dt = parseDate(ev.timestamp);
                const timeStr = dt ? formatRelativeTime(dt) : '-';
                const shortMsg = ev.type === 'alert' ? escapeHtml(String(ev.message).slice(0, 80)) : escapeHtml(ev.message);
                return `<div class="activity-item" data-device-id="${escapeHtml(ev.deviceId)}"><div class="activity-icon ${sev}"><i class="fa-solid ${icon}"></i></div><div class="activity-body"><div class="activity-text"><strong>${escapeHtml(ev.title)}</strong> — ${shortMsg}</div><div class="activity-time">${timeStr}</div></div></div>`;
            }).join('');
            container.querySelectorAll('.activity-item').forEach(item => {
                item.addEventListener('click', () => { const id = item.dataset.deviceId; if (id) viewDevice(id); });
            });
        } catch (e) { console.error(e); container.innerHTML = `<div class="activity-empty">Gagal memuat aktivitas</div>`; }
    }

    // ==========================================
    // MAP
    // ==========================================
    function initMapPreview() {
        if (state.mapPreview) return;
        const el = $('mapPreview'); if (!el) return;
        state.mapPreview = L.map('mapPreview', { zoomControl: true, attributionControl: false }).setView([-2.5489, 118.0149], 5);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(state.mapPreview);
        registerMapInstance(state.mapPreview);
    }
    function initFullMap() {
        if (state.mapFull) return;
        const el = $('mapFull'); if (!el) return;
        state.mapFull = L.map('mapFull').setView([-2.5489, 118.0149], 5);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(state.mapFull);
        if (typeof L.markerClusterGroup === 'function') {
            state.markerCluster = L.markerClusterGroup();
            state.mapFull.addLayer(state.markerCluster);
        }
        state.mapFull.on('click', (e) => {
            if (!state.selectedMapDeviceId) { showToast('Pilih device di list dulu', 'warning'); return; }
            placeMarkerAt(e.latlng.lat, e.latlng.lng);
        });
        registerMapInstance(state.mapFull);
    }
    function placeMarkerAt(lat, lng) {
        if (!state.mapFull) return;
        state.selectedLat = lat; state.selectedLng = lng;
        if (state.marker) { state.marker.setLatLng([lat, lng]); }
        else {
            state.marker = L.marker([lat, lng], { draggable: true }).addTo(state.mapFull);
            state.marker.on('dragstart', () => { state.mapHasUnsavedChange = true; });
            state.marker.on('dragend', (e) => {
                const pos = e.target.getLatLng();
                state.selectedLat = pos.lat; state.selectedLng = pos.lng;
                state.mapHasUnsavedChange = true;
                updateMapSelectedBanner();
            });
        }
        state.mapHasUnsavedChange = true;
        updateMapSelectedBanner();
    }
    function getDeviceMapStyle(d) {
        let color = '#6c7580'; let label = (d.status || 'offline').toUpperCase();
        if (d.status === 'offline') { color = '#c97a7a'; label = 'OFFLINE'; }
        else if (d.has_alert && d.top_alert_severity) {
            if (d.top_alert_severity === 'danger') color = '#c97a7a';
            else if (d.top_alert_severity === 'warning') color = '#d99a56';
            else if (d.top_alert_severity === 'info') color = '#7a9dc4';
            label = d.top_alert_severity.toUpperCase();
        } else if (d.status === 'online') { color = '#5fb587'; label = 'ONLINE'; }
        return { color, label };
    }
    function loadMarkers(map, useCluster = false) {
        if (!map) return;
        if (state.marker && !state.mapHasUnsavedChange) { map.removeLayer(state.marker); state.marker = null; }
        const validIds = new Set();
        state.devices.forEach(d => {
            if (d.latitude == null || d.longitude == null) return;
            if (d.latitude === 0 && d.longitude === 0) return;
            validIds.add(d.device_id);
        });
        const mapKey = useCluster ? 'cluster' : 'main';
        for (const [deviceId, entry] of state.markerMap.entries()) {
            if (entry.mapKey !== mapKey) continue;
            if (!validIds.has(deviceId)) {
                try {
                    if (useCluster && state.markerCluster) state.markerCluster.removeLayer(entry.marker);
                    else map.removeLayer(entry.marker);
                } catch (e) {}
                state.markerMap.delete(deviceId);
            }
        }
        state.devices.forEach(d => {
            if (!validIds.has(d.device_id)) return;
            const style = getDeviceMapStyle(d);
            const existing = state.markerMap.get(d.device_id);
            if (existing && existing.mapKey === mapKey) {
                try {
                    existing.marker.setLatLng([d.latitude, d.longitude]);
                    existing.marker.setStyle({ color: style.color, fillColor: style.color, radius: 8, fillOpacity: 0.8, weight: 2 });
                } catch (e) {}
                return;
            }
            const popup = `<div style="font-family:Inter,sans-serif;min-width:200px;"><div style="font-weight:700;margin-bottom:4px;">${escapeHtml(d.device_name)}</div><div style="font-size:11px;color:#888;margin-bottom:6px;font-family:monospace;">${escapeHtml(d.device_id)}</div><div style="font-size:11px;margin-bottom:8px;">Status: <b style="color:${style.color};">${style.label}</b></div><div style="display:flex;gap:6px;"><button onclick="window.__nexusMapSelect('${escapeHtml(d.device_id)}')" style="flex:1;padding:6px 10px;background:#e8ebef;color:#14171c;border:none;border-radius:6px;font-size:11px;cursor:pointer;">Pilih</button><button onclick="window.__nexusMapView('${escapeHtml(d.device_id)}')" style="flex:1;padding:6px 10px;background:#5fbb86;color:#fff;border:none;border-radius:6px;font-size:11px;cursor:pointer;">Detail</button></div></div>`;
            const marker = L.circleMarker([d.latitude, d.longitude], { radius: 8, color: style.color, fillColor: style.color, fillOpacity: 0.8, weight: 2 }).bindPopup(popup);
            marker.on('click', () => selectMapDevice(d.device_id, { zoom: false, placeMarker: false }));
            if (useCluster && state.markerCluster) state.markerCluster.addLayer(marker);
            else marker.addTo(map);
            state.markerMap.set(d.device_id, { marker, mapKey });
        });
    }
    function selectMapDevice(deviceId, opts = {}) {
        const device = state.devices.find(d => d.device_id === deviceId);
        if (!device) return;
        if (state.selectedMapDeviceId && state.selectedMapDeviceId !== deviceId && state.mapHasUnsavedChange) {
            if (!confirm('Ada perubahan lokasi belum disimpan. Lanjutkan?')) return;
        }
        state.selectedMapDeviceId = deviceId;
        state.mapHasUnsavedChange = false;
        state.selectedLat = null; state.selectedLng = null;
        const list = $('mapDeviceList');
        if (list) list.querySelectorAll('.map-device-item').forEach(el => el.classList.toggle('selected', el.dataset.deviceId === deviceId));
        const hasLoc = device.latitude && device.longitude && !(device.latitude === 0 && device.longitude === 0);
        if (hasLoc) {
            state.selectedLat = device.latitude; state.selectedLng = device.longitude;
            if (state.mapFull) {
                const targetZoom = opts.zoom ? 15 : Math.max(state.mapFull.getZoom(), 13);
                state.mapFull.flyTo([device.latitude, device.longitude], targetZoom, { duration: 1 });
            }
        } else if (opts.placeMarker && state.mapFull) {
            const c = state.mapFull.getCenter();
            placeMarkerAt(c.lat, c.lng);
        }
        updateMapSelectedBanner();
    }
    function updateMapSelectedBanner() {
        const banner = $('mapSelectedBanner'); const nameEl = $('mapSelectedName');
        const coordEl = $('mapSelectedCoord'); const dotEl = $('mapSelectedDot');
        const saveBtn = $('saveLocationBtn');
        if (!state.selectedMapDeviceId) { if (banner) banner.style.display = 'none'; return; }
        const device = state.devices.find(d => d.device_id === state.selectedMapDeviceId);
        if (!device) { if (banner) banner.style.display = 'none'; return; }
        const style = getDeviceMapStyle(device);
        if (banner) banner.style.display = 'flex';
        if (nameEl) nameEl.textContent = device.device_name;
        if (dotEl) dotEl.style.background = style.color;
        if (coordEl) {
            if (state.selectedLat != null && state.selectedLng != null) {
                coordEl.innerHTML = `${state.selectedLat.toFixed(5)}, ${state.selectedLng.toFixed(5)}` + (state.mapHasUnsavedChange ? ' <span style="color:var(--accent-warn);font-weight:700;">• belum disimpan</span>' : '');
            } else coordEl.textContent = 'Belum ada koordinat';
        }
        if (saveBtn) saveBtn.disabled = !(state.selectedLat != null && state.selectedLng != null && state.mapHasUnsavedChange);
    }
    function renderMapDeviceList() {
        const container = $('mapDeviceList'); if (!container) return;
        const filter = state.mapFilter || 'all';
        const term = (state.mapSearchTerm || '').toLowerCase().trim();
        let list = state.devices.slice();
        if (filter === 'online') list = list.filter(d => d.status === 'online');
        else if (filter === 'offline') list = list.filter(d => d.status === 'offline');
        else if (filter === 'alert') list = list.filter(d => d.has_alert === true);
        if (term) list = list.filter(d => (d.device_name || '').toLowerCase().includes(term) || (d.device_id || '').toLowerCase().includes(term) || (d.location || '').toLowerCase().includes(term));
        const countEl = $('mapListCount'); if (countEl) countEl.textContent = list.length;
        if (list.length === 0) { container.innerHTML = `<div class="map-empty-list">${term ? 'Tidak ada device yang cocok' : 'Tidak ada device di filter ini'}</div>`; return; }
        container.innerHTML = list.map(d => {
            const style = getDeviceMapStyle(d);
            const hasLoc = d.latitude && d.longitude && !(d.latitude === 0 && d.longitude === 0);
            const isSelected = state.selectedMapDeviceId === d.device_id;
            return `<button class="map-device-item ${isSelected ? 'selected' : ''}" data-device-id="${escapeHtml(d.device_id)}"><span class="device-dot" style="background:${style.color};"></span><div class="device-info"><div class="device-name">${escapeHtml(d.device_name)}</div><div class="device-id">${escapeHtml(d.device_id)}${!hasLoc ? '<span style="color:var(--accent-warn);margin-left:4px;font-size:9px;">• belum ada lokasi</span>' : ''}</div></div><span class="device-status" style="background:${style.color}20;color:${style.color};">${escapeHtml(style.label)}</span></button>`;
        }).join('');
        container.querySelectorAll('.map-device-item').forEach(item => {
            item.addEventListener('click', () => selectMapDevice(item.dataset.deviceId, { zoom: true, placeMarker: true }));
        });
    }
    async function saveLocation() {
        const deviceId = state.selectedMapDeviceId;
        if (!deviceId) { showToast('Pilih perangkat dulu', 'error'); return; }
        if (!Number.isFinite(state.selectedLat) || !Number.isFinite(state.selectedLng)) { showToast('Atur lokasi dulu', 'error'); return; }
        const result = await API.updateDevice(deviceId, { latitude: state.selectedLat, longitude: state.selectedLng });
        if (result.success) {
            showToast(`Lokasi ${deviceId} tersimpan`, 'success');
            const device = state.devices.find(d => d.device_id === deviceId);
            if (device) { device.latitude = state.selectedLat; device.longitude = state.selectedLng; }
            state.mapHasUnsavedChange = false;
            updateMapSelectedBanner();
            loadDashboard();
        } else showToast(result.error || 'Gagal menyimpan', 'error');
    }
    function clearMapSelection() {
        if (state.mapHasUnsavedChange && !confirm('Ada perubahan belum disimpan. Yakin batal?')) return;
        state.selectedMapDeviceId = null;
        state.selectedLat = null; state.selectedLng = null;
        state.mapHasUnsavedChange = false;
        if (state.marker && state.mapFull) { state.mapFull.removeLayer(state.marker); state.marker = null; }
        const list = $('mapDeviceList');
        if (list) list.querySelectorAll('.map-device-item').forEach(el => el.classList.remove('selected'));
        updateMapSelectedBanner();
    }
    window.__nexusMapSelect = function(id) { if (state.mapFull) state.mapFull.closePopup(); selectMapDevice(id, { zoom: false, placeMarker: true }); };
    window.__nexusMapView = function(id) { viewDevice(id); };

    // ==========================================
    // DEVICE FILTERS
    // ==========================================
    function setDeviceFilter(filter) {
        state.deviceFilter = filter;
        $$('#deviceFilterBar .filter-btn').forEach(btn => btn.classList.toggle('active', btn.dataset.filter === filter));
        renderFilteredDevices();
    }
    function setDeviceFilterFull(filter) {
        state.deviceFilterFull = filter;
        $$('#deviceFilterBarFull .filter-btn').forEach(btn => btn.classList.toggle('active', btn.dataset.filter === filter));
        renderFilteredDevicesFull();
    }
    function filterDevicesByStatus(devices, filter) {
        switch (filter) {
            case 'online': return devices.filter(d => d.status === 'online');
            case 'offline': return devices.filter(d => d.status === 'offline');
            case 'alert': return devices.filter(d => d.has_alert === true);
            default: return devices;
        }
    }
    function renderFilteredDevices() { renderTable(filterDevicesByStatus(state.devices, state.deviceFilter), 'deviceTableBody', false); }
    function renderFilteredDevicesFull() { renderTable(filterDevicesByStatus(state.devices, state.deviceFilterFull), 'deviceTableBodyFull', true); }
    function updateFilterCounts() {
        const setText = (id, v) => { const el = $(id); if (el) el.textContent = v; };
        setText('filterCountAll', state.devices.length);
        setText('filterCountOnline', state.devices.filter(d => d.status === 'online').length);
        setText('filterCountOffline', state.devices.filter(d => d.status === 'offline').length);
        setText('filterCountAlert', state.devices.filter(d => d.has_alert === true).length);
    }
    function renderTable(devices, tbodyId, full) {
        const tbody = $(tbodyId); if (!tbody) return;
        if (devices.length === 0) { tbody.innerHTML = `<tr><td colspan="${full ? 9 : 7}" style="text-align:center;padding:40px;color:var(--text-3);">Tidak ada perangkat</td></tr>`; return; }
        tbody.innerHTML = devices.map(d => {
            const lastSeen = formatTime(d.last_seen);
            const uptime = formatUptime(d.latest_uptime_seconds || 0);
            const wifi = escapeHtml(d.latest_wifi_ssid || '-');
            let statusClass, statusLabel;
            if (d.status === 'offline') { statusClass = 'offline'; statusLabel = 'OFFLINE'; }
            else if (d.has_alert && d.top_alert_severity) {
                statusClass = d.top_alert_severity;
                statusLabel = d.top_alert_severity === 'danger' ? 'BAHAYA' : d.top_alert_severity === 'warning' ? 'PERINGATAN' : d.top_alert_severity.toUpperCase();
            } else { statusClass = d.status || 'online'; statusLabel = (d.status || 'online').toUpperCase(); }
            return `<tr data-device-id="${escapeHtml(d.device_id)}"><td><span class="status-badge ${statusClass}"><span class="status-dot-inline"></span>${escapeHtml(statusLabel)}</span></td><td><span class="device-id">${escapeHtml(d.device_id)}</span></td><td><span class="device-name">${escapeHtml(d.device_name)}</span></td>${full ? `<td>${escapeHtml(d.device_type || '-')}</td>` : ''}<td>${wifi}</td><td>${uptime}</td>${full ? `<td>${escapeHtml(d.location || '-')}</td>` : ''}<td>${lastSeen}</td><td><div class="device-actions"><button class="action-btn view" data-action="view" data-device-id="${escapeHtml(d.device_id)}" title="Detail"><i class="fa-solid fa-eye"></i></button><button class="action-btn config" data-action="config" data-device-id="${escapeHtml(d.device_id)}" title="Konfigurasi"><i class="fa-solid fa-sliders"></i></button><button class="action-btn regenerate" data-action="regenerate-key" data-device-id="${escapeHtml(d.device_id)}" title="Regen Key"><i class="fa-solid fa-key"></i></button><button class="action-btn delete" data-action="delete" data-device-id="${escapeHtml(d.device_id)}" title="Hapus"><i class="fa-solid fa-trash"></i></button></div></td></tr>`;
        }).join('');
        tbody.querySelectorAll('[data-action="view"]').forEach(b => b.addEventListener('click', () => viewDevice(b.dataset.deviceId)));
        tbody.querySelectorAll('[data-action="config"]').forEach(b => b.addEventListener('click', () => openEditDeviceConfig(b.dataset.deviceId)));
        tbody.querySelectorAll('[data-action="regenerate-key"]').forEach(b => b.addEventListener('click', () => regenerateApiKey(b.dataset.deviceId)));
        tbody.querySelectorAll('[data-action="delete"]').forEach(b => b.addEventListener('click', () => openDeleteModal(b.dataset.deviceId)));
    }
    function filterDevices() {
        const term = (state.deviceSearchTerm || '').toLowerCase().trim();
        const searched = term ? state.devices.filter(d => d.device_id.toLowerCase().includes(term) || d.device_name.toLowerCase().includes(term) || (d.location && d.location.toLowerCase().includes(term))) : state.devices;
        renderTable(filterDevicesByStatus(searched, state.deviceFilter), 'deviceTableBody', false);
        renderTable(filterDevicesByStatus(searched, state.deviceFilterFull), 'deviceTableBodyFull', true);
    }

    // ==========================================
    // ATTENDANCE
    // ==========================================
    async function loadAttendanceStats() {
        const result = await API.getAttendanceStats();
        if (!result.success) return;
        const s = result.data.stats || {};
        const setVal = (id, v) => { const el = $(id); if (el) el.textContent = v ?? 0; };
        setVal('statHadirHariIni', s.hadir_hari_ini);
        setVal('statTotalKartu', s.total_kartu_aktif);
        setVal('statBelumTerdaftar', s.kartu_belum_terdaftar);
    }
    function setAttendanceView(view) {
        state.attendanceView = view;
        document.querySelectorAll('.attendance-tab').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === view);
        });
        loadAttendance();
    }
    async function loadAttendance() {
        const tbody = $('attendanceTableBody'); const thead = $('attendanceThead');
        if (!tbody) return;
        const startVal = ($('attendanceStartDate') || {}).value || '';
        const endVal = ($('attendanceEndDate') || {}).value || '';
        if (state.attendanceView === 'report') {
            const params = new URLSearchParams();
            if (startVal) params.set('start', startVal);
            if (endVal) params.set('end', endVal);
            const res = await API.call(`/api/v1/attendance/report?${params}`);
            if (!res.success) { tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:30px;color:var(--accent-crit);">Gagal memuat</td></tr>`; return; }
            if (thead) thead.innerHTML = `<tr><th>Tanggal</th><th>Nama</th><th>UID</th><th>Check-in</th><th>Check-out</th></tr>`;
            const rows = res.data.report || [];
            if (rows.length === 0) { tbody.innerHTML = `<tr><td colspan="5"><div class="empty-state"><i class="fa-solid fa-clipboard-list"></i><h3>Belum Ada Laporan</h3></div></td></tr>`; return; }
            tbody.innerHTML = rows.map(r => {
            // Strip microseconds: "08:16:33.149472" → "08:16:33"
            const cleanTime = (s) => s ? String(s).split(' ')[1]?.split('.')[0] || '-' : '-';
            const ci = cleanTime(r.check_in);
            const co = (r.check_out && r.check_out !== r.check_in) ? cleanTime(r.check_out) : '-';
                return `<tr><td><span style="font-family:var(--mono);font-size:12px;">${escapeHtml(r.day)}</span></td><td>${escapeHtml(r.nama)}</td><td><span class="device-id">${escapeHtml(r.uid)}</span></td><td><span style="color:var(--accent-ok);font-weight:600;font-family:var(--mono);font-size:12px;">${ci}</span></td><td><span style="color:var(--accent-warn);font-weight:600;font-family:var(--mono);font-size:12px;">${co}</span></td></tr>`;
            }).join('');
        } else {
            const result = await API.getAttendance();
            if (!result.success) { tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;padding:30px;color:var(--accent-crit);">Gagal memuat</td></tr>`; return; }
            if (thead) thead.innerHTML = `<tr><th>Nama</th><th>UID</th><th>Perangkat</th><th>Waktu</th></tr>`;
            let rows = result.data.attendance || [];
            if (startVal || endVal) {
                const startTs = startVal ? new Date(startVal + 'T00:00:00+07:00').getTime() : 0;
                const endTs = endVal ? new Date(endVal + 'T23:59:59+07:00').getTime() : Infinity;
                rows = rows.filter(r => { const d = parseDate(r.timestamp); if (!d) return true; const t = d.getTime(); return t >= startTs && t <= endTs; });
            }
            if (rows.length === 0) { tbody.innerHTML = `<tr><td colspan="4"><div class="empty-state"><i class="fa-solid fa-id-card"></i><h3>Belum Ada Aktivitas</h3></div></td></tr>`; return; }
            tbody.innerHTML = rows.map(r => {
                const dt = formatDateTimeSplit(r.timestamp);
                return `<tr data-timestamp="${escapeHtml(String(r.timestamp))}"><td>${escapeHtml(r.nama)}</td><td><span class="device-id">${escapeHtml(r.uid)}</span></td><td>${escapeHtml(r.device_id)}</td><td><div class="datetime-display"><div class="date">${dt.date}</div><div class="time">${dt.time}</div></div></td></tr>`;
            }).join('');
        }
        loadAttendanceStats();
    }
    function startAttendancePolling() {
        stopAttendancePolling();
        state.attendanceInterval = setInterval(() => { if (state.currentSection === 'attendance') loadAttendance(); }, 5000);
    }
    function stopAttendancePolling() { if (state.attendanceInterval) { clearInterval(state.attendanceInterval); state.attendanceInterval = null; } }

    // ==========================================
    // CARDHOLDER / STAT DETAIL
    // ==========================================
    function openCardholderModal() {
        const uidEl = $('cardholderUid'); const namaEl = $('cardholderNama');
        if (uidEl) uidEl.value = ''; if (namaEl) namaEl.value = '';
        openModal('cardholderModal');
    }
    async function captureLastTap() {
        const result = await API.getLastUnknownTap();
        if (!result.success) { showToast('Gagal', 'error'); return; }
        if (!result.data.uid) { showToast('Belum ada kartu asing', 'error'); return; }
        const uidEl = $('cardholderUid'); if (uidEl) uidEl.value = result.data.uid;
    }
    async function submitCardholder() {
        const uid = ($('cardholderUid') || {}).value?.trim() || '';
        const nama = ($('cardholderNama') || {}).value?.trim() || '';
        if (!uid || !nama) { showToast('UID dan Nama wajib', 'error'); return; }
        const result = await API.addCardholder({ uid, nama });
        if (result.success) { closeModal('cardholderModal'); showToast('Kartu terdaftar!', 'success'); loadAttendance(); }
        else showToast(result.error || 'Gagal', 'error');
    }
    async function openStatDetailModal(type) {
        const titleEl = $('statDetailTitle'); const thead = $('statDetailThead'); const tbody = $('statDetailBody');
        if (!tbody) return;
        tbody.innerHTML = `<tr><td colspan="3" style="text-align:center;padding:30px;color:var(--text-3);">Memuat...</td></tr>`;
        openModal('statDetailModal');
        if (type === 'hadir') {
            if (titleEl) titleEl.textContent = 'Hadir Hari Ini';
            if (thead) thead.innerHTML = `<tr><th>Nama</th><th>UID</th><th style="text-align:right;">Tap Pertama</th></tr>`;
            const result = await API.getAttendanceToday();
            const rows = result.success ? (result.data.hadir || []) : [];
            if (rows.length === 0) { tbody.innerHTML = `<tr><td colspan="3" style="text-align:center;padding:30px;color:var(--text-3);">Belum ada tap</td></tr>`; return; }
            tbody.innerHTML = rows.map(r => `<tr><td>${escapeHtml(r.nama)}</td><td><span class="device-id">${escapeHtml(r.uid)}</span></td><td style="text-align:right;">${formatDateTimeSplit(r.pertama_tap).time}</td></tr>`).join('');
        } else if (type === 'total') {
            if (titleEl) titleEl.textContent = 'Total Kartu Aktif';
            if (thead) thead.innerHTML = `<tr><th>Nama</th><th>UID</th><th>Terdaftar</th><th style="text-align:right;">Aksi</th></tr>`;
            const result = await API.getCardholders();
            const rows = result.success ? (result.data.cardholders || []) : [];
            if (rows.length === 0) { tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;padding:30px;color:var(--text-3);">Belum ada kartu</td></tr>`; return; }
            tbody.innerHTML = rows.map(r => `<tr><td>${escapeHtml(r.nama)}</td><td><span class="device-id">${escapeHtml(r.uid)}</span></td><td>${formatDateTimeSplit(r.created_at).date}</td><td style="text-align:right;"><button class="action-btn delete" data-action="hapus-cardholder" data-uid="${escapeHtml(r.uid)}" data-nama="${escapeHtml(r.nama)}"><i class="fa-solid fa-trash"></i></button></td></tr>`).join('');
            tbody.querySelectorAll('[data-action="hapus-cardholder"]').forEach(btn => btn.addEventListener('click', () => openDeleteCardholderModal(btn.dataset.uid, btn.dataset.nama)));
        } else if (type === 'belum-terdaftar') {
            if (titleEl) titleEl.textContent = 'Kartu Belum Terdaftar';
            if (thead) thead.innerHTML = `<tr><th>UID</th><th>Tap Terakhir</th><th style="text-align:right;">Aksi</th></tr>`;
            const result = await API.getUnregisteredCards();
            const rows = result.success ? (result.data.kartu || []) : [];
            if (rows.length === 0) { tbody.innerHTML = `<tr><td colspan="3" style="text-align:center;padding:30px;color:var(--text-3);">Semua kartu terdaftar</td></tr>`; return; }
            tbody.innerHTML = rows.map(r => { const dt = formatDateTimeSplit(r.terakhir_tap); return `<tr><td><span class="device-id">${escapeHtml(r.uid)}</span></td><td>${dt.date} ${dt.time}</td><td style="text-align:right;"><button class="btn btn-secondary" style="padding:6px 12px;font-size:12px;" data-action="daftarkan-from-detail" data-uid="${escapeHtml(r.uid)}">Daftarkan</button></td></tr>`; }).join('');
            tbody.querySelectorAll('[data-action="daftarkan-from-detail"]').forEach(btn => btn.addEventListener('click', () => {
                closeModal('statDetailModal');
                const uidEl = $('cardholderUid'); const namaEl = $('cardholderNama');
                if (uidEl) uidEl.value = btn.dataset.uid;
                if (namaEl) namaEl.value = '';
                openModal('cardholderModal');
            }));
        }
    }

    // ==========================================
    // DEVICE CRUD
    // ==========================================
    function viewDevice(id) {
        const backUrl = `/${window.location.hash || '#dashboard'}`;
        try { sessionStorage.setItem(STORAGE_KEYS.BACK_URL, backUrl); } catch (e) {}
        window.location.href = `/device/${encodeURIComponent(id)}`;
    }
    async function regenerateApiKey(deviceId) {
        if (!confirm(`Regenerate API key ${deviceId}?`)) return;
        const result = await API.regenerateKey(deviceId);
        if (result.success) {
            const display = $('apiKeyDisplay'); if (display) display.textContent = result.data.api_key;
            openModal('apiKeyModal'); loadDashboard();
        } else showToast(result.error || 'Gagal', 'error');
    }
    function openAddDeviceModal() {
        if (window.populateAlertRules) window.populateAlertRules('add', null);
        const setVal = (id, val) => { const el = $(id); if (el) el.value = val; };
        setVal('addDeviceId', '');
        setVal('addDeviceName', '');
        setVal('addDeviceLocation', '');
        // Interval auto-detect — tidak ada input
        setVal('addDeviceOfflineTimeout', '');
        openModal('addDeviceModal');
    }
    async function addDevice() {
        const idEl = $('addDeviceId'); const nameEl = $('addDeviceName');
        const deviceId = idEl ? idEl.value.trim() : '';
        const deviceName = nameEl ? nameEl.value.trim() : '';
        if (!deviceId || !deviceName) { showToast('ID dan Nama wajib', 'error'); return; }
        const alertRules = window.collectAlertRules ? window.collectAlertRules('add') : null;

        // expected_interval TIDAK dikirim — server akan auto-detect dari data
        const payload = {
            device_id: deviceId,
            device_name: deviceName,
            device_type: ($('addDeviceType') || {}).value,
            location: (($('addDeviceLocation') || {}).value || '').trim(),
        };

        // Offline timeout OPSIONAL — kalau kosong, server hitung 2x interval
        const offlineTimeout = ($('addDeviceOfflineTimeout') || {}).value;
        if (offlineTimeout) payload.offline_timeout = parseInt(offlineTimeout);

        if (alertRules) payload.alert_rules = alertRules;

        const result = await API.addDevice(payload);
        if (result.success) {
            closeModal('addDeviceModal');
            const display = $('apiKeyDisplay'); if (display) display.textContent = result.data.device.api_key;
            openModal('apiKeyModal');
            if (idEl) idEl.value = '';
            if (nameEl) nameEl.value = '';
            const locEl = $('addDeviceLocation'); if (locEl) locEl.value = '';
            const toEl = $('addDeviceOfflineTimeout'); if (toEl) toEl.value = '';
            if (window.populateAlertRules) window.populateAlertRules('add', null);
            loadDashboard();
        } else {
            const errMsg = typeof result.error === 'object' ? Object.values(result.error).flat().join(', ') : result.error;
            showToast(errMsg || 'Gagal', 'error');
        }
    }
    function copyApiKey() {
        const display = $('apiKeyDisplay'); if (!display) return;
        navigator.clipboard.writeText(display.textContent).then(() => showToast('Tersalin!', 'success')).catch(() => showToast('Gagal', 'error'));
    }
    async function openEditDeviceConfig(deviceId) {
        const result = await API.getDevice(deviceId);
        if (!result.success) { showToast('Gagal memuat', 'error'); return; }
        const device = result.data.device;
        const setVal = (id, val) => { const el = $(id); if (el) el.value = val; };
        setVal('editConfigDeviceId', deviceId);

        // Display interval (read-only, auto-detected)
        const intervalDisplay = $('editDeviceIntervalDisplay');
        if (intervalDisplay) {
            const interval = device.expected_interval;
            intervalDisplay.textContent = interval ? `${interval} detik` : 'Menunggu data...';
        }

        // Offline timeout: kosong kalau NULL (auto mode)
        setVal('editDeviceOfflineTimeout', device.offline_timeout || '');

        if (window.populateAlertRules) window.populateAlertRules('edit', device.alert_rules);
        openModal('editDeviceConfigModal');
    }
    async function saveDeviceConfig() {
        const deviceId = ($('editConfigDeviceId') || {}).value;
        if (!deviceId) return;
        const alertRules = window.collectAlertRules ? window.collectAlertRules('edit') : null;

        // expected_interval TIDAK dikirim — server maintain auto-detected value
        const payload = {
            alert_rules: alertRules,
        };

        // Offline timeout: kalau kosong, kirim 0 untuk reset ke auto
        const offlineTimeout = ($('editDeviceOfflineTimeout') || {}).value;
        if (offlineTimeout) {
            payload.offline_timeout = parseInt(offlineTimeout);
        } else {
            payload.offline_timeout = null;  // reset ke auto
        }

        const result = await API.updateDevice(deviceId, payload);
        if (result.success) { closeModal('editDeviceConfigModal'); showToast('Tersimpan', 'success'); loadDashboard(); }
        else showToast(result.error || 'Gagal', 'error');
    }
    function updateDeleteButtonState() {
        const btn = $('confirmDeleteBtn'); const input = $('deleteConfirmInput');
        if (!btn || !input) return;
        const target = state.deleteTarget;
        if (!target) { btn.disabled = true; return; }
        btn.disabled = input.value.trim() !== target.confirmKey;
    }
    function openDeleteModal(id) {
        const device = state.devices.find(d => d.device_id === id);
        const deviceName = device ? device.device_name : id;
        state.deleteTarget = { type: 'device', id, confirmKey: id };
        const setVal = (elId, val) => { const el = $(elId); if (el) el.value = val; };
        setVal('deleteType', 'device'); setVal('deleteDeviceId', id);
        const titleEl = $('deleteModalTitle'); const textEl = $('deleteModalText');
        const labelEl = $('deleteConfirmLabel'); const inputEl = $('deleteConfirmInput');
        if (titleEl) titleEl.textContent = 'Hapus Perangkat';
        if (textEl) textEl.textContent = `Perangkat "${deviceName}" (${id}) akan dihapus permanen.`;
        if (labelEl) labelEl.innerHTML = `Ketik <code style="background:var(--surface-2);padding:2px 6px;border-radius:4px;font-family:var(--mono);font-size:12px;">${escapeHtml(id)}</code> untuk konfirmasi`;
        if (inputEl) { inputEl.value = ''; inputEl.placeholder = `Ketik ${id}...`; }
        updateDeleteButtonState();
        openModal('deleteModal');
    }
    function openDeleteCardholderModal(uid, nama) {
        state.deleteTarget = { type: 'cardholder', id: uid, confirmKey: nama };
        const setVal = (elId, val) => { const el = $(elId); if (el) el.value = val; };
        setVal('deleteType', 'cardholder'); setVal('deleteDeviceId', uid);
        const titleEl = $('deleteModalTitle'); const textEl = $('deleteModalText');
        const labelEl = $('deleteConfirmLabel'); const inputEl = $('deleteConfirmInput');
        if (titleEl) titleEl.textContent = 'Hapus Kartu';
        if (textEl) textEl.textContent = `Kartu "${nama}" (${uid}) akan dihapus.`;
        if (labelEl) labelEl.innerHTML = `Ketik nama <code style="background:var(--surface-2);padding:2px 6px;border-radius:4px;font-family:var(--mono);font-size:12px;">${escapeHtml(nama)}</code> untuk konfirmasi`;
        if (inputEl) { inputEl.value = ''; inputEl.placeholder = `Ketik ${nama}...`; }
        updateDeleteButtonState();
        openModal('deleteModal');
    }
    async function confirmDelete() {
        const target = state.deleteTarget; if (!target) return;
        const input = $('deleteConfirmInput'); const value = input ? input.value.trim() : '';
        if (value !== target.confirmKey) { showToast(`Ketik "${target.confirmKey}" dengan benar`, 'error'); return; }
        const result = target.type === 'cardholder' ? await API.deleteCardholder(target.id) : await API.deleteDevice(target.id);
        if (result.success) {
            closeModal('deleteModal');
            state.deleteTarget = null;
            if (target.type === 'cardholder') { showToast('Kartu dihapus', 'success'); openStatDetailModal('total'); loadAttendance(); }
            else { showToast('Perangkat dihapus', 'success'); loadDashboard(); }
        } else showToast(result.error || 'Gagal', 'error');
    }

    // ==========================================
    // ANALYTICS TABS
    // ==========================================
    async function loadAnalyticsTabs() {
        const store = window.DashboardStore;
        if (!store) return;
        let targetDashboard = null;
        if (state.dashboardSlug) {
            const res = await API.call(`/api/v1/dashboards/slug/${encodeURIComponent(state.dashboardSlug)}`);
            if (res.success) targetDashboard = res.data.dashboard;
        }
        if (!targetDashboard) {
            await store.loadDashboards();
            targetDashboard = store.state.dashboards.find(d => d.is_default) || store.state.dashboards[0];
        }
        if (!targetDashboard) return;
        await store.loadDashboard(targetDashboard.id);
        const res = await API.call(`/api/v1/dashboards/${targetDashboard.id}/analytics-tabs`);
        state.analyticsTabs = res.success ? (res.data.tabs || []) : [];
        let savedTabId = null;
        try { const raw = sessionStorage.getItem(STORAGE_KEYS.CURRENT_TAB); if (raw) savedTabId = parseInt(raw); } catch (e) {}
        const validIds = new Set(state.analyticsTabs.map(t => t.id));
        if (savedTabId && validIds.has(savedTabId)) state.currentTabId = savedTabId;
        else if (state.currentTabId !== null && validIds.has(state.currentTabId)) {}
        else state.currentTabId = state.analyticsTabs.length > 0 ? state.analyticsTabs[0].id : null;
        renderAnalyticsTabs();
        if (state.currentTabId) await loadTabCharts(state.currentTabId);
    }
    function renderAnalyticsTabs() {
        const trigger = $('tabDropdownTrigger'); const label = $('tabDropdownLabel'); const menu = $('tabDropdownMenu');
        if (!trigger || !label || !menu) return;
        const currentTab = state.analyticsTabs.find(t => t.id === state.currentTabId);
        label.textContent = currentTab ? currentTab.name : 'Pilih Tab';
        let html = '';
        state.analyticsTabs.forEach(tab => {
            html += `<div class="tab-dropdown-item ${state.currentTabId === tab.id ? 'active' : ''}" data-tab-id="${tab.id}"><i class="fa-solid ${escapeHtml(tab.icon || 'fa-chart-line')}"></i><span>${escapeHtml(tab.name)}</span><div class="tab-actions"><button class="tab-action-btn" data-action="rename-tab" data-tab-id="${tab.id}" title="Rename"><i class="fa-solid fa-pen"></i></button><button class="tab-action-btn" data-action="delete-tab" data-tab-id="${tab.id}" title="Hapus"><i class="fa-solid fa-trash"></i></button></div></div>`;
        });
        html += `<div class="tab-dropdown-divider"></div><div class="tab-dropdown-add" data-action="new-tab"><i class="fa-solid fa-plus"></i><span>Tambah Tab Analitik</span></div>`;
        menu.innerHTML = html;
        menu.querySelectorAll('[data-tab-id]').forEach(item => {
            const tabId = parseInt(item.dataset.tabId);
            item.addEventListener('click', (e) => {
                if (e.target.closest('[data-action]')) return;
                switchAnalyticsTab(tabId);
                menu.classList.remove('active');
            });
        });
        menu.querySelectorAll('[data-action="rename-tab"], [data-action="delete-tab"]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const tabId = parseInt(btn.dataset.tabId);
                const tab = state.analyticsTabs.find(t => t.id === tabId);
                if (tab) openAnalyticsTabModal('edit', tab.id, tab.name);
                menu.classList.remove('active');
            });
        });
        const addBtn = menu.querySelector('[data-action="new-tab"]');
        if (addBtn) addBtn.addEventListener('click', () => { openAnalyticsTabModal('new'); menu.classList.remove('active'); });
    }
    async function switchAnalyticsTab(tabId) {
        state.currentTabId = tabId;
        try { sessionStorage.setItem(STORAGE_KEYS.CURRENT_TAB, String(tabId)); } catch (e) {}
        renderAnalyticsTabs();
        await loadTabCharts(tabId);
    }
    function openAnalyticsTabModal(mode, tabId, currentName) {
        const titleEl = $('analyticsTabModalTitle'); const modeEl = $('analyticsTabMode');
        const idEl = $('analyticsTabId'); const nameEl = $('analyticsTabName');
        const delBtn = $('analyticsTabDeleteBtn');
        if (titleEl) titleEl.textContent = mode === 'edit' ? 'Edit Tab Analitik' : 'Tambah Tab Analitik';
        if (modeEl) modeEl.value = mode;
        if (idEl) idEl.value = tabId || '';
        if (nameEl) nameEl.value = currentName || '';
        if (delBtn) delBtn.style.display = mode === 'edit' ? 'inline-flex' : 'none';
        openModal('analyticsTabModal');
    }
    async function saveAnalyticsTab() {
        const mode = ($('analyticsTabMode') || {}).value;
        const tabId = ($('analyticsTabId') || {}).value;
        const name = ($('analyticsTabName') || {}).value?.trim() || '';
        if (!name) { showToast('Nama tab wajib', 'error'); return; }
        const store = window.DashboardStore;
        const dashboardId = store.state.currentDashboardId;
        if (mode === 'edit' && tabId) {
            const res = await API.call(`/api/v1/analytics-tabs/${tabId}`, { method: 'PUT', body: JSON.stringify({ name }) });
            if (res.success) { closeModal('analyticsTabModal'); showToast('Tab diupdate', 'success'); await loadAnalyticsTabs(); }
            else showToast(res.error || 'Gagal', 'error');
        } else {
            const res = await API.call(`/api/v1/dashboards/${dashboardId}/analytics-tabs`, { method: 'POST', body: JSON.stringify({ name, icon: 'fa-chart-line' }) });
            if (res.success) { closeModal('analyticsTabModal'); showToast('Tab dibuat', 'success'); await loadAnalyticsTabs(); switchAnalyticsTab(res.data.id); }
            else showToast(res.error || 'Gagal', 'error');
        }
    }
    async function deleteAnalyticsTab() {
        const tabId = ($('analyticsTabId') || {}).value;
        if (!tabId || !confirm('Hapus tab ini beserta diagramnya?')) return;
        const res = await API.call(`/api/v1/analytics-tabs/${tabId}`, { method: 'DELETE' });
        if (res.success) {
            closeModal('analyticsTabModal');
            showToast('Tab dihapus', 'success');
            if (state.currentTabId === parseInt(tabId)) {
                state.currentTabId = null;
                try { sessionStorage.removeItem(STORAGE_KEYS.CURRENT_TAB); } catch (e) {}
            }
            await loadAnalyticsTabs();
            if (state.analyticsTabs.length > 0) switchAnalyticsTab(state.analyticsTabs[0].id);
            else {
                state.charts.forEach(c => { if (c.chartInstance) try { c.chartInstance.destroy(); } catch (e) {} });
                state.charts = [];
                const grid = $('chartsGrid');
                if (grid) grid.innerHTML = `<div class="empty-charts" style="text-align:center;padding:40px;color:var(--text-3);"><i class="fa-solid fa-chart-column" style="font-size:40px;margin-bottom:12px;display:block;opacity:.4;"></i><p style="font-size:14px;font-weight:600;">Belum ada diagram di tab ini</p></div>`;
            }
        } else showToast(res.error || 'Gagal', 'error');
    }

    // ==========================================
    // CHART ENGINE — v4.8
    // ==========================================
    function layoutKey() { return STORAGE_KEYS.CHART_LAYOUT_PREFIX + (state.currentTabId || 'default'); }

    function saveChartLayout() {
        const layout = state.charts.map(c => ({
            id: c.id, widgetId: c.widgetId, title: c.title, deviceId: c.deviceId,
            chartType: c.chartType, showData: c.showData,
            x: c.x, y: c.y, w: c.w, h: c.h,
        }));
        try { localStorage.setItem(layoutKey(), JSON.stringify(layout)); } catch (e) {}
        try { localStorage.setItem(STORAGE_KEYS.CANVAS_HEIGHT, String(state.canvasHeight)); } catch (e) {}
    }

    function loadChartLayout() {
        try { return JSON.parse(localStorage.getItem(layoutKey()) || 'null'); } catch (e) { return null; }
    }

    function loadCanvasHeight() {
        try {
            const h = parseInt(localStorage.getItem(STORAGE_KEYS.CANVAS_HEIGHT));
            if (h && h >= 300 && h <= 3000) state.canvasHeight = h;
        } catch (e) {}
    }

    function applyChartGeom(c) {
        const el = document.getElementById(c.id);
        if (!el) return;
        el.style.left = c.x + 'px';
        el.style.top = c.y + 'px';
        el.style.width = c.w + 'px';
        el.style.height = c.h + 'px';
    }

    function applyAllGeom() {
        state.charts.forEach(applyChartGeom);
    }

    function getRect(c) {
        return { left: c.x, top: c.y, right: c.x + c.w, bottom: c.y + c.h };
    }

    function rectsOverlap(a, b) {
        return !(a.right <= b.left || a.left >= b.right || a.bottom <= b.top || a.top >= b.bottom);
    }

    // ANTI-TUMPUK: push yang bawah turun
    function resolveCollisions() {
        if (state.charts.length < 2) return;
        const sorted = [...state.charts].sort((a, b) => a.y - b.y);
        let changed = true;
        let iter = 0;
        while (changed && iter < 30) {
            changed = false;
            iter++;
            for (let i = 0; i < sorted.length; i++) {
                const a = sorted[i];
                const aRect = getRect(a);
                for (let j = i + 1; j < sorted.length; j++) {
                    const b = sorted[j];
                    const bRect = getRect(b);
                    if (rectsOverlap(aRect, bRect)) {
                        b.y = aRect.bottom + GAP;
                        bRect.top = b.y;
                        bRect.bottom = b.y + bRect.height;
                        changed = true;
                    }
                }
            }
        }
    }

    // CLAMP: batasi chart ke dalam canvas
    function clampChartsToCanvas() {
        const grid = $('chartsGrid');
        if (!grid) return;
        const canvasW = grid.clientWidth;
        const maxW = Math.max(MIN_W, canvasW - PADDING * 2);
        const limit = canvasW - PADDING;

        state.charts.forEach(c => {
            if (c.w > maxW) c.w = maxW;
            if (c.x < PADDING) c.x = PADDING;
            if (c.x + c.w > limit) c.x = Math.max(PADDING, limit - c.w);
            if (c.y < PADDING) c.y = PADDING;
        });
    }

    function autoGrowCanvas() {
        const grid = $('chartsGrid');
        if (!grid) return;
        let maxBottom = 0;
        state.charts.forEach(c => {
            maxBottom = Math.max(maxBottom, c.y + c.h);
        });
        const needed = maxBottom + PADDING * 2;
        if (needed > state.canvasHeight) {
            state.canvasHeight = needed;
            grid.style.height = needed + 'px';
        }
    }

    async function loadTabCharts(tabId) {
        if (!tabId) return;
        const store = window.DashboardStore;
        const dashboardId = store.state.currentDashboardId;
        if (!dashboardId) return;
        const res = await API.call(`/api/v1/dashboards/${dashboardId}/analytics-tabs/${tabId}/widgets`);
        const widgets = res.success ? (res.data.widgets || []) : [];

        state.charts.forEach(c => {
            if (c.chartInstance) try { c.chartInstance.destroy(); } catch (e) {}
            const el = document.getElementById(c.id);
            if (el) { try { interact(el).unset(); } catch (e) {} el.remove(); }
        });
        state.charts = [];

        const grid = $('chartsGrid');
        if (grid) {
            grid.innerHTML = '';
            grid.style.height = state.canvasHeight + 'px';
        }

        if (widgets.length === 0) {
            if (grid) grid.innerHTML = `<div class="empty-charts" style="text-align:center;padding:40px;color:var(--text-3);"><i class="fa-solid fa-chart-column" style="font-size:40px;margin-bottom:12px;display:block;opacity:.4;"></i><p style="font-size:14px;font-weight:600;">Belum ada diagram di tab ini</p></div>`;
            return;
        }

        const savedLayout = loadChartLayout() || {};
        const savedMap = {};
        if (Array.isArray(savedLayout)) savedLayout.forEach(s => { savedMap[s.id] = s; });

        widgets.forEach((w, idx) => {
            const saved = savedMap[`chart_${w.id}`];
            let x, y, cw, ch;
            if (saved && typeof saved.x === 'number') {
                x = saved.x; y = saved.y;
                cw = saved.w || DEFAULT_W;
                ch = saved.h || DEFAULT_H;
            } else {
                const col = idx % 2;
                const row = Math.floor(idx / 2);
                x = PADDING + col * (DEFAULT_W + GAP);
                y = PADDING + row * (DEFAULT_H + GAP);
                cw = DEFAULT_W;
                ch = DEFAULT_H;
            }
            const wConfig = w.config || {};
            const deviceIds = Array.isArray(wConfig.devices) && wConfig.devices.length > 0
                ? wConfig.devices
                : (w.device_id ? [w.device_id] : []);

            const config = {
                id: `chart_${w.id}`,
                widgetId: w.id,
                title: w.title,
                deviceIds,
                chartType: store.mapWidgetTypeToChartType(w.widget_type),
                showData: wConfig.show_data || {},
                x, y, w: cw, h: ch,
                chartInstance: null,
            };
            state.charts.push(config);
            state.chartIdCounter = Math.max(state.chartIdCounter, w.id);
        });

        state.charts.forEach(c => renderChartCard(c));
        clampChartsToCanvas();
        resolveCollisions();
        applyAllGeom();
        autoGrowCanvas();
        await loadAllChartDataBatched();
    }

    function renderChartCard(config) {
        const grid = $('chartsGrid');
        if (!grid) return;
        const emptyEl = grid.querySelector('.empty-charts');
        if (emptyEl) emptyEl.remove();

        const card = document.createElement('div');
        card.className = 'chart-card';
        card.id = config.id;
        card.style.left = config.x + 'px';
        card.style.top = config.y + 'px';
        card.style.width = config.w + 'px';
        card.style.height = config.h + 'px';

        const dataLabels = Object.entries(config.showData).filter(([_, v]) => v).map(([k]) => DATA_KEYS[k]?.label || k).join(', ');
        const deviceNamesStr = (config.deviceIds || []).map(did => state.devices.find(d => d.device_id === did)?.device_name || did).join(', ');

        card.innerHTML = `
            <div class="chart-card-header">
                <div class="chart-card-title">
                    <i class="fa-solid fa-chart-line"></i>
                    <span>${escapeHtml(config.title)}</span>
                    <span class="chart-meta">(${escapeHtml(deviceNamesStr)} - ${escapeHtml(dataLabels)})</span>
                </div>
                <div class="chart-actions">
                    <button class="chart-action-btn" data-action="edit" title="Edit"><i class="fa-solid fa-pen"></i></button>
                    <button class="chart-action-btn remove" data-action="remove" title="Hapus"><i class="fa-solid fa-trash"></i></button>
                </div>
            </div>
            <div class="chart-card-body">
                <div class="chart-canvas-container">
                    <canvas id="${config.id}_canvas"></canvas>
                </div>
            </div>
            <div class="chart-card-resize"></div>
        `;

        grid.appendChild(card);

        card.querySelector('[data-action="edit"]').addEventListener('click', e => { e.stopPropagation(); e.preventDefault(); openEditChartModal(config.id); });
        card.querySelector('[data-action="remove"]').addEventListener('click', e => { e.stopPropagation(); e.preventDefault(); removeChart(config.id); });

        initializeDragResize(config.id);
    }

    function initializeDragResize(chartId) {
        const el = document.getElementById(chartId);
        if (!el || typeof interact === 'undefined') return;

        let dragState = null;
        let autoScrollRAF = null;

        function stopAutoScroll() {
            if (autoScrollRAF) {
                cancelAnimationFrame(autoScrollRAF);
                autoScrollRAF = null;
            }
        }

        function startAutoScroll() {
            stopAutoScroll();

            function loop() {
                autoScrollRAF = null;
                if (!dragState) return;

                const grid = $('chartsGrid');
                const c = state.charts.find(x => x.id === chartId);
                if (!grid || !c) {
                    autoScrollRAF = requestAnimationFrame(loop);
                    return;
                }

                const gridRect = grid.getBoundingClientRect();
                const y = dragState.lastY;
                const margin = 70;
                const maxSpeed = 16;

                let scrollDelta = 0;

                if (y > gridRect.bottom - margin) {
                    const t = Math.min(1, (y - (gridRect.bottom - margin)) / margin);
                    scrollDelta = maxSpeed * t;
                } else if (y < gridRect.top + margin) {
                    const t = Math.min(1, ((gridRect.top + margin) - y) / margin);
                    scrollDelta = -maxSpeed * t;
                }

                if (scrollDelta !== 0) {
                    const before = grid.scrollTop;
                    grid.scrollTop += scrollDelta;
                    const actual = grid.scrollTop - before;

                    if (actual !== 0) {
                        c.y = Math.max(PADDING, c.y + actual);
                        el.style.top = c.y + 'px';

                        if (c.y + c.h + PADDING > state.canvasHeight) {
                            state.canvasHeight = c.y + c.h + PADDING;
                            grid.style.height = state.canvasHeight + 'px';
                        }
                    }
                }

                autoScrollRAF = requestAnimationFrame(loop);
            }

            autoScrollRAF = requestAnimationFrame(loop);
        }

        interact(el)
            .draggable({
                allowFrom: '.chart-card-header',
                ignoreFrom: '.chart-actions',
                inertia: false,
                listeners: {
                    start(event) {
                        el.classList.add('dragging');

                        const elRect = el.getBoundingClientRect();
                        dragState = {
                            offsetX: event.clientX - elRect.left,
                            offsetY: event.clientY - elRect.top,
                            lastY: event.clientY,
                        };

                        startAutoScroll();
                    },
                    move(event) {
                        const c = state.charts.find(x => x.id === chartId);
                        if (!c || !dragState) return;

                        const grid = $('chartsGrid');
                        const gridRect = grid.getBoundingClientRect();

                        const newLeft = event.clientX - dragState.offsetX - gridRect.left + grid.scrollLeft;
                        const newTop = event.clientY - dragState.offsetY - gridRect.top + grid.scrollTop;

                        c.x = Math.max(PADDING, newLeft);
                        c.y = Math.max(PADDING, newTop);

                        el.style.left = c.x + 'px';
                        el.style.top = c.y + 'px';

                        dragState.lastY = event.clientY;
                    },
                    end() {
                        el.classList.remove('dragging');
                        stopAutoScroll();
                        dragState = null;

                        clampChartsToCanvas();
                        resolveCollisions();
                        applyAllGeom();
                        autoGrowCanvas();
                        saveChartLayout();
                    }
                }
            })
            .resizable({
                edges: { right: true, bottom: true, left: false, top: false },
                inertia: false,
                modifiers: [interact.modifiers.restrictSize({ min: { width: MIN_W, height: MIN_H } })],
                listeners: {
                    start() { el.classList.add('resizing'); },
                    move(event) {
                        const c = state.charts.find(x => x.id === chartId);
                        if (!c) return;
                        const grid = $('chartsGrid');
                        const canvasW = grid ? grid.clientWidth : 1000;
                        const maxW = Math.max(MIN_W, canvasW - c.x - PADDING);
                        c.w = Math.min(event.rect.width, maxW);
                        c.h = event.rect.height;
                        el.style.width = c.w + 'px';
                        el.style.height = c.h + 'px';
                        if (c.chartInstance) try { c.chartInstance.resize(); } catch (e) {}
                    },
                    end() {
                        el.classList.remove('resizing');
                        clampChartsToCanvas();
                        resolveCollisions();
                        applyAllGeom();
                        autoGrowCanvas();
                        saveChartLayout();
                    }
                }
            });
    }

    function bindGridResize() {
        const handle = document.querySelector('.charts-grid-resize-handle');
        const grid = $('chartsGrid');
        if (!handle || !grid) return;

        grid.style.height = state.canvasHeight + 'px';

        let startY = 0, startH = 0;

        function start(clientY) {
            startY = clientY;
            startH = grid.clientHeight;
            handle.classList.add('dragging');
            document.body.style.cursor = 'ns-resize';
            document.body.style.userSelect = 'none';
        }
        function move(clientY) {
            const delta = clientY - startY;
            const newH = Math.min(Math.max(startH + delta, 300), 3000);
            grid.style.height = newH + 'px';
            state.canvasHeight = newH;
        }
        function end() {
            handle.classList.remove('dragging');
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            saveChartLayout();
        }

        handle.addEventListener('mousedown', e => {
            e.preventDefault();
            start(e.clientY);
            const onMove = ev => move(ev.clientY);
            const onUp = () => { end(); document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        });
        handle.addEventListener('touchstart', e => {
            start(e.touches[0].clientY);
            const onMove = ev => move(ev.touches[0].clientY);
            const onEnd = () => { end(); document.removeEventListener('touchmove', onMove); document.removeEventListener('touchend', onEnd); };
            document.addEventListener('touchmove', onMove, { passive: true });
            document.addEventListener('touchend', onEnd);
        }, { passive: true });
    }

    function generateDeviceCheckboxes(selectedDeviceIds = []) {
        const container = $('chartDeviceCheckboxes');
        if (!container) return;
        if (state.devices.length === 0) {
            container.innerHTML = '<div style="padding:12px;color:var(--text-3);font-size:12px;grid-column:1/-1;">Belum ada perangkat. Tambah dulu di menu Perangkat.</div>';
            return;
        }
        const selectedSet = new Set(selectedDeviceIds);
        container.innerHTML = state.devices.map(d => `
            <label class="checkbox-item">
                <input type="checkbox" class="chart-device-checkbox"
                       data-device-id="${escapeHtml(d.device_id)}"
                       ${selectedSet.has(d.device_id) ? 'checked' : ''}>
                <span>${escapeHtml(d.device_name)}
                    <span style="color:var(--text-3);font-family:var(--mono);font-size:10px;">(${escapeHtml(d.device_id)})</span>
                </span>
            </label>
        `).join('');
    }

    function generateDataCheckboxes(selected = {}) {
        const container = $('chartDataCheckboxes'); if (!container) return;
        container.innerHTML = Object.entries(DATA_KEYS).map(([key, info]) => `<label class="checkbox-item"><input type="checkbox" class="chart-data-checkbox" data-key="${key}" ${selected[key] ? 'checked' : ''}><span class="data-color" style="background:${info.color};"></span><span>${escapeHtml(info.label)} (${escapeHtml(info.unit)})</span></label>`).join('');
    }

    function openAddChartModal() {
        if (!state.currentTabId) { showToast('Buat tab analitik dulu', 'warning'); return; }
        const titleEl = $('chartModalTitle');
        const editEl = $('editChartId');
        const chartTitleEl = $('chartTitle');
        if (titleEl) titleEl.textContent = 'Tambah Diagram';
        if (editEl) editEl.value = '';
        if (chartTitleEl) chartTitleEl.value = '';
        generateDeviceCheckboxes([]);
        const typeEl = $('chartTypeSelect'); if (typeEl) typeEl.value = 'line';
        generateDataCheckboxes({ temperature: true });
        openModal('chartModal');
    }

    function openEditChartModal(chartId) {
        const chart = state.charts.find(c => c.id === chartId);
        if (!chart) return;
        const titleEl = $('chartModalTitle');
        const editEl = $('editChartId');
        const chartTitleEl = $('chartTitle');
        if (titleEl) titleEl.textContent = 'Edit Diagram';
        if (editEl) editEl.value = chartId;
        if (chartTitleEl) chartTitleEl.value = chart.title;
        generateDeviceCheckboxes(chart.deviceIds || []);
        const typeEl = $('chartTypeSelect'); if (typeEl) typeEl.value = chart.chartType;
        generateDataCheckboxes(chart.showData);
        openModal('chartModal');
    }

    async function saveChart() {
        const editId = ($('editChartId') || {}).value;
        const title = (($('chartTitle') || {}).value || '').trim() || 'Diagram';
        const chartType = ($('chartTypeSelect') || {}).value;

        const deviceIds = [];
        document.querySelectorAll('#chartDeviceCheckboxes .chart-device-checkbox').forEach(cb => {
            if (cb.checked) deviceIds.push(cb.dataset.deviceId);
        });

        const showData = {};
        document.querySelectorAll('#chartDataCheckboxes .chart-data-checkbox').forEach(cb => {
            showData[cb.dataset.key] = cb.checked;
        });

        if (deviceIds.length === 0) { showToast('Pilih minimal 1 perangkat', 'error'); return; }
        if (!Object.values(showData).some(v => v)) { showToast('Pilih minimal 1 jenis data', 'error'); return; }

        const store = window.DashboardStore;
        const dashboardId = store.state.currentDashboardId;
        const widgetType = store.mapChartTypeToWidgetType(chartType);

        const widgetConfig = {
            show_data: showData,
            devices: deviceIds,
        };

        if (editId) {
            const chart = state.charts.find(c => c.id === editId);
            if (!chart) return;

            const res = await API.call(`/api/v1/widgets/${chart.widgetId}`, {
                method: 'PUT',
                body: JSON.stringify({
                    title,
                    device_id: deviceIds[0],
                    widget_type: widgetType,
                    config: widgetConfig,
                }),
            });
            if (!res.success) { showToast(res.error || 'Gagal', 'error'); return; }

            chart.title = title;
            chart.deviceIds = deviceIds;
            chart.chartType = chartType;
            chart.showData = showData;

            if (chart.chartInstance) { try { chart.chartInstance.destroy(); } catch (e) {} chart.chartInstance = null; }

            const card = document.getElementById(editId);
            if (card) {
                const dataLabels = Object.entries(showData).filter(([_, v]) => v).map(([k]) => DATA_KEYS[k]?.label || k).join(', ');
                const deviceNamesStr = deviceIds.map(did => state.devices.find(d => d.device_id === did)?.device_name || did).join(', ');
                card.querySelector('.chart-card-title').innerHTML =
                    `<i class="fa-solid fa-chart-line"></i><span>${escapeHtml(title)}</span><span class="chart-meta">(${escapeHtml(deviceNamesStr)} - ${escapeHtml(dataLabels)})</span>`;
            }
            await loadDynamicChartData(chart);
            showToast('Diagram diupdate', 'success');
        } else {
            const res = await API.call(`/api/v1/dashboards/${dashboardId}/widgets`, {
                method: 'POST',
                body: JSON.stringify({
                    widget_type: widgetType,
                    title,
                    device_id: deviceIds[0],
                    config: widgetConfig,
                    grid_x: 0, grid_y: 0, grid_w: 6, grid_h: 2,
                    analytics_tab_id: state.currentTabId,
                }),
            });
            if (!res.success) { showToast(res.error || 'Gagal', 'error'); return; }
            await loadTabCharts(state.currentTabId);
            showToast('Diagram ditambahkan', 'success');
        }
        closeModal('chartModal');
    }

    async function loadDynamicChartData(config) {
        const deviceIds = config.deviceIds || [];
        if (deviceIds.length === 0) { showChartEmpty(config.id, 'Belum ada device dipilih'); return; }
        const hours = Math.max(1, Math.ceil(state.globalTimeMinutes / 60));
        const limit = Math.min(Math.max(hours * 60, 500), 5000);
        try {
            const results = await Promise.all(deviceIds.map(did =>
                API.getDeviceHistory(did, { hours, limit }).then(r => ({ did, result: r }))
            ));
            const historyByDevice = {};
            results.forEach(({ did, result }) => {
                historyByDevice[did] = result.success ? (result.data.history || []) : [];
            });
            renderChartDataSync(config, historyByDevice);
        } catch (e) { console.error('[Chart]', e); }
    }

    async function loadAllChartDataBatched() {
        if (state.charts.length === 0) return;

        const uniqueDevices = new Set();
        state.charts.forEach(c => {
            (c.deviceIds || []).forEach(did => uniqueDevices.add(did));
        });
        if (uniqueDevices.size === 0) return;

        const hours = Math.max(1, Math.ceil(state.globalTimeMinutes / 60));
        const limit = Math.min(Math.max(hours * 60, 500), 5000);

        const fetchResults = await Promise.all(
            Array.from(uniqueDevices).map(did =>
                API.getDeviceHistory(did, { hours, limit }).then(r => ({ did, result: r }))
            )
        );
        const historyByDevice = {};
        fetchResults.forEach(({ did, result }) => {
            historyByDevice[did] = result.success ? (result.data.history || []) : [];
        });

        state.charts.forEach(c => {
            const chartHistory = {};
            (c.deviceIds || []).forEach(did => { chartHistory[did] = historyByDevice[did] || []; });
            try { renderChartDataSync(c, chartHistory); } catch (e) { console.error(e); }
        });
    }

    function renderChartDataSync(config, historyByDevice) {
        const canvas = document.getElementById(`${config.id}_canvas`);
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const colors = getChartColors();
        if (config.chartInstance) { try { config.chartInstance.destroy(); } catch (e) {} config.chartInstance = null; }

        const deviceIds = config.deviceIds || [];
        const activeKeys = Object.entries(config.showData).filter(([_, v]) => v).map(([k]) => k);

        // Doughnut / Pie / Polar / Radar → 1 slice per device × key
        if (['doughnut', 'pie', 'polarArea', 'radar'].includes(config.chartType)) {
            const gaugeLabels = [];
            const gaugeValues = [];
            deviceIds.forEach(did => {
                const hist = historyByDevice[did] || [];
                if (hist.length === 0) return;
                const latest = hist[hist.length - 1];
                const dname = state.devices.find(d => d.device_id === did)?.device_name || did;
                activeKeys.forEach(key => {
                    const info = DATA_KEYS[key];
                    if (!info) return;
                    const val = latest.data?.[key];
                    if (val !== null && val !== undefined) {
                        gaugeLabels.push(deviceIds.length > 1 ? `${dname} — ${info.label}` : info.label);
                        gaugeValues.push(val);
                    }
                });
            });
            if (gaugeValues.length === 0) { showChartEmpty(config.id, 'Tidak ada data terbaru'); return; }
            config.chartInstance = new Chart(ctx, {
                type: config.chartType,
                data: {
                    labels: gaugeLabels,
                    datasets: [{
                        data: gaugeValues,
                        backgroundColor: gaugeValues.map((_, i) => CHART_COLORS[i % CHART_COLORS.length] + '80'),
                        borderColor: gaugeValues.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]),
                        borderWidth: 2,
                    }],
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'right',
                            labels: { color: colors.legendColor, font: { size: 11, family: CHART_FONT }, usePointStyle: true, padding: 12 },
                        },
                    },
                },
            });
            return;
        }

        // Time-series (line/bar/area)
        const timestampSet = new Set();
        deviceIds.forEach(did => {
            (historyByDevice[did] || []).forEach(item => timestampSet.add(item.timestamp));
        });
        if (timestampSet.size === 0) { showChartEmpty(config.id, 'Menunggu data sensor...'); return; }

        const now = Date.now();
        const cutoff = now - state.globalTimeMinutes * 60 * 1000;
        const allTs = Array.from(timestampSet).sort();
        const inRange = allTs.filter(ts => {
            const d = parseDate(ts);
            return d && d.getTime() >= cutoff;
        });
        const usedTs = downsampleHistory(inRange.length > 0 ? inRange : allTs, 500);

        if (usedTs.length === 0) { showChartEmpty(config.id, 'Menunggu data sensor...'); return; }

        const labels = usedTs.map(ts => {
            const d = parseDate(ts);
            if (!d) return '';
            try {
                return d.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'Asia/Jakarta' });
            } catch (e) { return ''; }
        });

        const datasets = [];
        let colorIdx = 0;

        deviceIds.forEach(did => {
            const hist = historyByDevice[did] || [];
            if (hist.length === 0) return;
            const dname = state.devices.find(d => d.device_id === did)?.device_name || did;

            // Map timestamp → data object
            const tsMap = {};
            hist.forEach(item => { tsMap[item.timestamp] = item.data || {}; });

            activeKeys.forEach(key => {
                const info = DATA_KEYS[key];
                if (!info) return;
                const values = usedTs.map(ts => {
                    const obj = tsMap[ts];
                    if (!obj) return null;
                    return obj[key] ?? obj[key.toLowerCase()] ?? obj[key.toUpperCase()] ?? null;
                });
                if (!values.some(v => v !== null && v !== undefined)) return;

                const color = CHART_COLORS[colorIdx % CHART_COLORS.length];
                colorIdx++;

                const isArea = config.chartType === 'area' || config.chartType === 'stackedArea';
                const isStacked = config.chartType === 'stackedBar' || config.chartType === 'stackedArea';

                const label = deviceIds.length > 1
                    ? `${dname} — ${info.label}`
                    : `${info.label} (${info.unit})`;

                datasets.push({
                    label,
                    data: values,
                    borderColor: color,
                    backgroundColor: isArea ? color + '30' : color + '80',
                    fill: isArea,
                    tension: 0.35,
                    pointRadius: 2, pointHoverRadius: 5,
                    pointBackgroundColor: color,
                    pointBorderColor: colors.pointBorderColor,
                    pointBorderWidth: 1, borderWidth: 2,
                    spanGaps: true,  // ← sambung null biar tidak putus
                    stack: isStacked ? 'stack1' : undefined,
                });
            });
        });

        if (datasets.length === 0) { showChartEmpty(config.id, 'Tidak ada data sensor yang cocok'); return; }

        let type = config.chartType;
        if (type === 'area' || type === 'stackedArea') type = 'line';
        if (type === 'horizontalBar' || type === 'stackedBar') type = 'bar';

        config.chartInstance = new Chart(ctx, {
            type,
            data: { labels, datasets },
            options: {
                responsive: true, maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                indexAxis: config.chartType === 'horizontalBar' ? 'y' : 'x',
                animation: { duration: 400, easing: 'easeOutQuart' },
                plugins: {
                    legend: { labels: { color: colors.legendColor, font: { size: 11, family: CHART_FONT }, usePointStyle: true, pointStyle: 'circle', padding: 12 } },
                    tooltip: { backgroundColor: colors.tooltipBg, titleColor: colors.tooltipTitleColor, bodyColor: colors.tooltipBodyColor, borderColor: colors.tooltipBorder, borderWidth: 1, padding: 12, cornerRadius: 10, displayColors: true, boxPadding: 5 },
                },
                scales: {
                    x: { grid: { color: colors.gridColor }, ticks: { color: colors.labelColor, font: { family: CHART_FONT }, maxTicksLimit: 10, maxRotation: 45, autoSkip: true }, stacked: config.chartType === 'stackedBar' || config.chartType === 'stackedArea' },
                    y: { grid: { color: colors.gridColor }, ticks: { color: colors.labelColor, font: { family: CHART_FONT } }, stacked: config.chartType === 'stackedBar' || config.chartType === 'stackedArea', beginAtZero: true },
                },
            },
        });
    }

    function showChartEmpty(chartId, message) {
        const card = document.getElementById(chartId); if (!card) return;
        const container = card.querySelector('.chart-canvas-container'); if (!container) return;
        container.innerHTML = `<div style="text-align:center;padding:20px;color:var(--text-3);font-size:12px;display:flex;flex-direction:column;align-items:center;gap:8px;height:100%;justify-content:center;"><i class="fa-solid fa-satellite-dish" style="font-size:20px;opacity:0.5;"></i><span>${escapeHtml(message)}</span></div>`;
    }

    function refreshAllCharts() {
        if (state.refreshTimeout) clearTimeout(state.refreshTimeout);
        state.refreshTimeout = setTimeout(() => { loadAllChartDataBatched(); }, 300);
    }
    function startAutoRefresh() {
        if (state.autoRefreshInterval) clearInterval(state.autoRefreshInterval);
        state.autoRefreshInterval = setInterval(() => {
            const graph = $('graphSection');
            if (graph && graph.style.display !== 'none') refreshAllCharts();
        }, 15000);
    }
    function setGlobalTimeRange(minutes) {
        state.globalTimeMinutes = minutes;
        localStorage.setItem(STORAGE_KEYS.GLOBAL_TIME, minutes);
        $$('.time-range-item').forEach(item => item.classList.toggle('active', parseInt(item.dataset.minutes) === minutes));
        const labelEl = $('timeRangeLabel'); if (labelEl) labelEl.textContent = formatTimeRange(minutes);
        refreshAllCharts();
    }
    function loadGlobalTimeRange() {
        const saved = localStorage.getItem(STORAGE_KEYS.GLOBAL_TIME);
        if (saved) state.globalTimeMinutes = parseInt(saved);
        $$('.time-range-item').forEach(item => item.classList.toggle('active', parseInt(item.dataset.minutes) === state.globalTimeMinutes));
        const labelEl = $('timeRangeLabel'); if (labelEl) labelEl.textContent = formatTimeRange(state.globalTimeMinutes);
    }

    async function removeChart(chartId) {
        const idx = state.charts.findIndex(c => c.id === chartId); if (idx === -1) return;
        const chart = state.charts[idx];
        if (!confirm(`Hapus diagram "${chart.title}"?`)) return;
        await API.call(`/api/v1/widgets/${chart.widgetId}`, { method: 'DELETE' });
        if (chart.chartInstance) try { chart.chartInstance.destroy(); } catch (e) {}
        state.charts.splice(idx, 1);
        const card = document.getElementById(chartId);
        if (card) { try { interact(card).unset(); } catch (e) {} card.remove(); }
        if (state.charts.length === 0) {
            const grid = $('chartsGrid');
            if (grid) grid.innerHTML = `<div class="empty-charts" style="text-align:center;padding:40px;color:var(--text-3);"><i class="fa-solid fa-chart-column" style="font-size:40px;margin-bottom:12px;display:block;opacity:.4;"></i><p style="font-size:14px;font-weight:600;">Belum ada diagram di tab ini</p></div>`;
        }
        resolveCollisions();
        applyAllGeom();
        saveChartLayout();
        showToast('Diagram dihapus', 'success');
    }

    function resetChartLayout() {
        state.charts.forEach((c, i) => {
            const col = i % 2;
            const row = Math.floor(i / 2);
            c.x = PADDING + col * (DEFAULT_W + GAP);
            c.y = PADDING + row * (DEFAULT_H + GAP);
            c.w = DEFAULT_W;
            c.h = DEFAULT_H;
        });
        state.canvasHeight = 720;
        const grid = $('chartsGrid');
        if (grid) grid.style.height = '720px';
        clampChartsToCanvas();
        resolveCollisions();
        applyAllGeom();
        state.charts.forEach(c => { if (c.chartInstance) try { c.chartInstance.resize(); } catch (e) {} });
        try { localStorage.removeItem(layoutKey()); localStorage.removeItem(STORAGE_KEYS.CANVAS_HEIGHT); } catch (e) {}
        showToast('Layout direset', 'success');
    }

    // ==========================================
    // DROPDOWNS & BINDINGS
    // ==========================================
    function bindTimeRangeDropdown() {
        const trigger = $('timeRangeTrigger'); const menu = $('timeRangeMenu');
        if (!trigger || !menu) return;
        trigger.addEventListener('click', e => { e.stopPropagation(); menu.classList.toggle('active'); });
        menu.querySelectorAll('.time-range-item').forEach(item => {
            item.addEventListener('click', () => { setGlobalTimeRange(parseInt(item.dataset.minutes)); menu.classList.remove('active'); });
        });
        document.addEventListener('click', e => {
            if (!menu.classList.contains('active')) return;
            if (!menu.contains(e.target) && !trigger.contains(e.target)) menu.classList.remove('active');
        });
    }
    function bindTabDropdown() {
        const trigger = $('tabDropdownTrigger'); const menu = $('tabDropdownMenu');
        if (!trigger || !menu) return;
        trigger.addEventListener('click', e => { e.stopPropagation(); menu.classList.toggle('active'); });
        document.addEventListener('click', e => {
            if (!menu.classList.contains('active')) return;
            if (!menu.contains(e.target) && !trigger.contains(e.target)) menu.classList.remove('active');
        });
    }
    function bindSidebarNav() {
        document.querySelectorAll('.sidebar-nav .nav-item').forEach(item => {
            item.addEventListener('click', e => {
                const href = (item.getAttribute('href') || '').trim();
                if (href.startsWith('#')) {
                    e.preventDefault();
                    const targetSection = href.replace('#', '');
                    if (DASHBOARD_SECTIONS.includes(targetSection)) showSection(targetSection);
                }
            });
        });
    }
    function bindLogout() {
        const logoutBtn = $('logoutBtn');
        if (logoutBtn) logoutBtn.addEventListener('click', e => { e.preventDefault(); window.location.href = '/logout'; });
    }
    function bindModals() {
        document.querySelectorAll('.modal-close').forEach(btn => {
            btn.addEventListener('click', () => {
                const modal = btn.closest('.modal'); if (modal) modal.classList.remove('active');
                unlockBodyScrollIfNoModal();
            });
        });
        document.querySelectorAll('.modal').forEach(modal => {
            modal.addEventListener('click', e => {
                if (e.target === modal) { modal.classList.remove('active'); unlockBodyScrollIfNoModal(); }
            });
        });
        const deleteInput = $('deleteConfirmInput');
        if (deleteInput) {
            deleteInput.addEventListener('input', updateDeleteButtonState);
            deleteInput.addEventListener('keydown', e => { if (e.key === 'Enter') { const btn = $('confirmDeleteBtn'); if (btn && !btn.disabled) btn.click(); } });
        }
    }
    function bindActionButtons() {
        const map = {
            'open-cardholder-modal': openCardholderModal,
            'capture-last-tap': captureLastTap,
            'submit-cardholder': submitCardholder,
            'add-device': openAddDeviceModal,
            'add-chart': openAddChartModal,
            'refresh-charts': refreshAllCharts,
            'reset-layout': resetChartLayout,
            'submit-add-device': addDevice,
            'save-device-config': saveDeviceConfig,
            'copy-api-key': copyApiKey,
            'confirm-delete': confirmDelete,
            'save-chart': saveChart,
            'save-analytics-tab': saveAnalyticsTab,
            'delete-analytics-tab': deleteAnalyticsTab,
        };
        Object.entries(map).forEach(([action, handler]) => {
            document.querySelectorAll(`[data-action="${action}"]`).forEach(btn => btn.addEventListener('click', handler));
        });
        const delTabBtn = $('analyticsTabDeleteBtn');
        if (delTabBtn) delTabBtn.addEventListener('click', deleteAnalyticsTab);
        document.querySelectorAll('.stat-card.clickable[data-stat-type]').forEach(card => {
            card.addEventListener('click', () => openStatDetailModal(card.dataset.statType));
        });
        document.querySelectorAll('.stat-card.clickable[data-goto]').forEach(card => {
            card.addEventListener('click', () => {
                const target = card.dataset.goto; const filter = card.dataset.filter;
                if (filter && target === 'devices') { state.deviceFilter = filter; setDeviceFilter(filter); }
                showSection(target);
            });
        });
        const activityRefresh = $('activityRefreshBtn');
        if (activityRefresh) activityRefresh.addEventListener('click', loadActivityFeed);
        document.querySelectorAll('.attendance-tab').forEach(btn => btn.addEventListener('click', () => setAttendanceView(btn.dataset.tab)));
    }
    function bindFilters() {
        const searchInput = $('searchInput');
        if (searchInput) {
            searchInput.addEventListener('input', () => {
                const value = searchInput.value;
                if (state.currentSection === 'alerts') {
                    state.alertSearchTerm = value;
                    if (window.NexusAlerts && window.NexusAlerts.setSearch) {
                        window.NexusAlerts.setSearch(value);
                    }
                } else if (state.currentSection === 'attendance') {
                    state.deviceSearchTerm = value;
                    loadAttendance();
                } else {
                    state.deviceSearchTerm = value;
                    filterDevices();
                }
            });
        }
        document.querySelectorAll('#deviceFilterBar .filter-btn').forEach(btn => btn.addEventListener('click', () => setDeviceFilter(btn.dataset.filter)));
        document.querySelectorAll('#deviceFilterBarFull .filter-btn').forEach(btn => btn.addEventListener('click', () => setDeviceFilterFull(btn.dataset.filter)));
    }
    function bindMapControls() {
        const saveBtn = $('saveLocationBtn'); if (saveBtn) saveBtn.addEventListener('click', saveLocation);
        const clearBtn = $('clearMapSelectionBtn'); if (clearBtn) clearBtn.addEventListener('click', clearMapSelection);
        const resetBtn = $('resetMapViewBtn'); if (resetBtn) resetBtn.addEventListener('click', () => { if (state.mapFull) state.mapFull.flyTo([-2.5489, 118.0149], 5, { duration: 1 }); });
        const searchInput = $('mapSearchInput');
        if (searchInput) {
            let t;
            searchInput.addEventListener('input', e => {
                clearTimeout(t);
                t = setTimeout(() => { state.mapSearchTerm = e.target.value.trim(); renderMapDeviceList(); }, 150);
            });
        }
        const chips = $('mapFilterChips');
        if (chips) chips.querySelectorAll('.map-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                chips.querySelectorAll('.map-chip').forEach(c => c.classList.remove('active'));
                chip.classList.add('active');
                state.mapFilter = chip.dataset.filter;
                renderMapDeviceList();
            });
        });
    }
    function bindKeyboard() {
        document.addEventListener('keydown', e => {
            if (e.key === 'Escape') {
                document.querySelectorAll('.modal.active').forEach(m => m.classList.remove('active'));
                unlockBodyScrollIfNoModal();
                const trMenu = $('timeRangeMenu'); if (trMenu) trMenu.classList.remove('active');
                const tabMenu = $('tabDropdownMenu'); if (tabMenu) tabMenu.classList.remove('active');
            }
        });
    }
    function bindNavigation() {
        window.addEventListener('popstate', () => { const s = getSectionFromHash(); showSection(s, true); });
        window.addEventListener('hashchange', () => { const s = getSectionFromHash(); if (state.currentSection !== s) showSection(s, true); });
    }
    function bindEvents() {
        bindSidebarNav(); bindLogout(); bindModals(); bindActionButtons();
        bindFilters(); bindMapControls(); bindTimeRangeDropdown(); bindTabDropdown();
        bindGridResize();
        bindKeyboard(); bindNavigation();
        const themeBtn = $('themeToggleBtn');
        if (themeBtn) themeBtn.addEventListener('click', () => { const t = window.ThemeManager.toggle(); updateThemeUI(t); setTimeout(refreshAllCharts, 100); });
        window.addEventListener('sidebar-toggle', () => {
            setTimeout(() => {
                if (window.__nexusMaps) window.__nexusMaps.forEach(m => { try { m.invalidateSize(); } catch (e) {} });
            }, 400);
        });

        // Auto-clamp saat window resize
        window.addEventListener('resize', () => {
            clearTimeout(window.__nexusResizeTO);
            window.__nexusResizeTO = setTimeout(() => {
                clampChartsToCanvas();
                resolveCollisions();
                applyAllGeom();
                state.charts.forEach(c => {
                    if (c.chartInstance) try { c.chartInstance.resize(); } catch (e) {}
                });
            }, 150);
        });

        window.ThemeManager.onChange(() => setTimeout(refreshAllCharts, 100));
    }
    function updateThemeUI(theme) {
        const icon = $('themeIcon'); const label = $('themeLabel');
        if (icon) icon.className = theme === 'light' ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
        if (label) label.textContent = theme === 'light' ? 'Tema Terang' : 'Tema Gelap';
    }
    function bindCleanup() {
        window.addEventListener('beforeunload', () => {
            if (state.dashboardInterval) clearInterval(state.dashboardInterval);
            if (state.autoRefreshInterval) clearInterval(state.autoRefreshInterval);
            if (state.attendanceInterval) clearInterval(state.attendanceInterval);
            if (state.activityRefreshInterval) clearInterval(state.activityRefreshInterval);
            state.charts.forEach(c => { if (c.chartInstance) try { c.chartInstance.destroy(); } catch (e) {} });
        });
    }
    function readDashboardSlug() {
        const meta = document.querySelector('meta[name="dashboard-slug"]');
        if (meta && meta.content) return meta.content.trim() || null;
        const body = document.body;
        if (body && body.dataset && body.dataset.dashboardSlug) return body.dataset.dashboardSlug.trim() || null;
        const m = window.location.pathname.match(/^\/d\/([a-z0-9\-]+)/i);
        return m ? m[1] : null;
    }

    // ==========================================
    // INIT
    // ==========================================
    async function init() {
        if (state.isInitialized) return;
        state.isInitialized = true;
        state.dashboardSlug = readDashboardSlug();
        loadCanvasHeight();
        bindEvents(); bindCleanup();
        updateThemeUI(window.ThemeManager.get());
        loadGlobalTimeRange();
        updateDateTime(); setInterval(updateDateTime, 1000);
        let initialSection = getSectionFromHash();
        if (!window.location.hash) {
            try {
                const saved = sessionStorage.getItem(STORAGE_KEYS.LAST_SECTION);
                if (saved && DASHBOARD_SECTIONS.includes(saved)) { initialSection = saved; history.replaceState(null, '', `#${saved}`); }
            } catch (e) {}
        }
        state.currentSection = initialSection;
        initMapPreview();
        await loadDashboard();
        await loadAnalyticsTabs();
        showSection(initialSection, true);
        state.dashboardInterval = setInterval(loadDashboard, 30000);
        startAutoRefresh();
        state.activityRefreshInterval = setInterval(() => { if (state.currentSection === 'dashboard') loadActivityFeed(); }, 60000);
        console.log('[Dashboard] Ready v4.8');
    }

    window.__nexusRefreshAttendance = () => loadAttendance();
    window.__nexusLoadAttendance = () => loadAttendance();

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();