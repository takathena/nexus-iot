/* ==========================================
   NEXUS IoT - Dashboard Logic (v6 FINAL)
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
    };

    const CHART_FONT = "'Inter', -apple-system, sans-serif";
    const CHART_COLORS = ['#ff453a', '#bf5af2', '#30d158', '#ff9f0a', '#0a84ff', '#ff375f', '#64d2ff', '#a3e635'];

    const DATA_KEYS = {
        temperature: { label: 'Suhu', unit: '°C', color: '#ff453a' },
        humidity: { label: 'Kelembaban', unit: '%', color: '#bf5af2' },
        gas_level: { label: 'Gas', unit: '%', color: '#ff9f0a' },
        smoke: { label: 'Asap', unit: 'ppm', color: '#ff6482' },
        motion: { label: 'Gerakan', unit: '', color: '#40c4ff' },
        rfid: { label: 'RFID', unit: '', color: '#a3e635' },
        moisture: { label: 'K. Tanah', unit: '%', color: '#64d2ff' },
        lux: { label: 'Cahaya', unit: 'lux', color: '#ffd60a' },
        co2: { label: 'CO2', unit: 'ppm', color: '#30d158' },
    };

    const STORAGE_KEYS = {
        THEME: 'nexus-theme',
        CHARTS: 'nexus-dynamic-charts',
        GLOBAL_TIME: 'nexus-global-time',
        LAST_SECTION: 'nexus-last-section',
        BACK_URL: 'nexus_back_url',
    };

    const DASHBOARD_SECTIONS = ['dashboard', 'map', 'graph', 'attendance', 'devices'];

    function $(id) { return document.getElementById(id); }
    function $$(sel) { return document.querySelectorAll(sel); }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = String(str ?? '');
        return div.innerHTML;
    }

    function parseDate(iso) {
        if (!iso) return null;
        const s = String(iso).trim();
        if (/[+-]\d{2}:\d{2}$/.test(s) || s.endsWith('Z')) {
            const d = new Date(s);
            return isNaN(d.getTime()) ? null : d;
        }
        if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(s)) {
            const d = new Date(s.replace(' ', 'T') + '+07:00');
            return isNaN(d.getTime()) ? null : d;
        }
        if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(s)) {
            const d = new Date(s + '+07:00');
            return isNaN(d.getTime()) ? null : d;
        }
        const d = new Date(s);
        return isNaN(d.getTime()) ? null : d;
    }

    function formatUptime(seconds) {
        if (!seconds && seconds !== 0) return '-';
        seconds = parseInt(seconds) || 0;
        if (seconds < 60) return `${seconds}s`;
        const d = Math.floor(seconds / 86400);
        const h = Math.floor((seconds % 86400) / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        if (d > 0) return `${d}h ${h}j`;
        if (h > 0) return `${h}j ${m}m`;
        return `${m}m`;
    }

    function formatTime(iso) {
        const d = parseDate(iso);
        if (!d) return '-';
        try {
            return d.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Jakarta' });
        } catch (e) { return '-'; }
    }

    function formatDateTimeSplit(iso) {
        const d = parseDate(iso);
        if (!d) return { date: '-', time: '-' };
        try {
            return {
                date: d.toLocaleDateString('id-ID', { day: '2-digit', month: 'short', timeZone: 'Asia/Jakarta' }),
                time: d.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'Asia/Jakarta' }),
            };
        } catch (e) { return { date: '-', time: '-' }; }
    }

    function formatTimeRange(minutes) {
        if (minutes < 60) return `${minutes} menit`;
        if (minutes < 1440) return `${minutes / 60} jam`;
        if (minutes < 10080) return `${minutes / 1440} hari`;
        return `${minutes / 10080} minggu`;
    }

    function getChartColors() {
        const isLight = document.documentElement.getAttribute('data-theme') === 'light';
        return {
            gridColor: isLight ? 'rgba(0,0,0,0.10)' : 'rgba(255,255,255,0.08)',
            labelColor: isLight ? 'rgba(60,60,67,0.60)' : 'rgba(235,235,245,0.45)',
            legendColor: isLight ? 'rgba(60,60,67,0.70)' : 'rgba(235,235,245,0.6)',
            tooltipBg: isLight ? 'rgba(255,255,255,0.95)' : 'rgba(28,28,30,0.95)',
            tooltipBorder: isLight ? 'rgba(0,0,0,0.1)' : 'rgba(255,255,255,0.1)',
            tooltipTitleColor: isLight ? '#1c1c1e' : '#f5f5f7',
            tooltipBodyColor: isLight ? 'rgba(60,60,67,0.75)' : 'rgba(235,235,245,0.72)',
            pointBorderColor: isLight ? '#fff' : '#000',
        };
    }

    function toggleSidebar() {
        const sidebar = $('sidebar');
        const main = $('mainContent');
        if (sidebar) sidebar.classList.toggle('collapsed');
        if (main) main.classList.toggle('expanded');
        setTimeout(() => {
            if (state.mapPreview) state.mapPreview.invalidateSize();
            if (state.mapFull) state.mapFull.invalidateSize();
        }, 380);
    }

    // ==========================================
    // NAVIGATION
    // ==========================================
    function getSectionFromHash() {
        const hash = (window.location.hash || '').replace('#', '').trim();
        if (DASHBOARD_SECTIONS.includes(hash)) return hash;
        return 'dashboard';
    }

    function updateHash(section, replace = false) {
        if (!DASHBOARD_SECTIONS.includes(section)) return;
        const newHash = `#${section}`;
        if (window.location.hash === newHash) return;
        if (replace) {
            history.replaceState(null, '', newHash);
        } else {
            history.pushState(null, '', newHash);
        }
    }

    function showSection(section, skipHistory = false) {
        if (!DASHBOARD_SECTIONS.includes(section)) section = 'dashboard';

        state.currentSection = section;

        ['dashboard', 'map', 'graph', 'attendance', 'devices'].forEach(s => {
            const el = $(s + 'Section');
            if (el) el.style.display = s === section ? 'block' : 'none';
        });

        const titles = {
            dashboard: 'Dashboard',
            map: 'Peta Interaktif',
            graph: 'Analitik Sensor',
            devices: 'Manajemen Perangkat',
            attendance: 'Absensi',
        };
        const titleEl = $('pageTitle');
        if (titleEl) titleEl.textContent = titles[section] || 'Dashboard';

        $$('.sidebar-nav .nav-item[data-section]').forEach((item) => {
            const sec = item.getAttribute('data-section');
            item.classList.toggle('active', sec === section);
        });

        const searchBox = document.querySelector('.search-box');
        const searchInput = $('searchInput');
        const noSearchSections = ['map', 'graph'];
        if (searchBox) searchBox.style.display = noSearchSections.includes(section) ? 'none' : '';
        if (searchInput) {
            searchInput.value = state.deviceSearchTerm || '';
            searchInput.placeholder = section === 'attendance'
                ? 'Cari nama/UID/perangkat...'
                : 'Cari perangkat...';
        }

        if (section === 'attendance') {
            loadAttendance();
            startAttendancePolling();
        } else {
            stopAttendancePolling();
        }

        if (section === 'map' && !state.mapFull) {
            setTimeout(initFullMap, 100);
            setTimeout(populateMapDeviceSelect, 150);
        }
        if (section === 'map' && state.mapFull) {
            setTimeout(() => state.mapFull.invalidateSize(), 100);
        }
        if (section === 'dashboard') {
            setTimeout(() => { if (state.mapPreview) state.mapPreview.invalidateSize(); }, 100);
        }
        if (section === 'graph') {
            setTimeout(refreshAllCharts, 100);
        }

        try { sessionStorage.setItem(STORAGE_KEYS.LAST_SECTION, section); } catch (e) {}

        if (!skipHistory) updateHash(section);
    }

    function updateDateTime() {
        const now = new Date();
        const dateEl = $('currentDate'), timeEl = $('currentTime');
        if (dateEl) dateEl.textContent = now.toLocaleDateString('id-ID', {
            weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
            timeZone: 'Asia/Jakarta',
        });
        if (timeEl) timeEl.textContent = now.toLocaleTimeString('id-ID', {
            hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'Asia/Jakarta',
        }) + ' WIB';
    }

    // ==========================================
    // ATTENDANCE (LENGKAP)
    // ==========================================
    async function loadAttendanceStats() {
        const result = await API.getAttendanceStats();
        if (!result.success) return;
        const s = result.data.stats || {};
        const setVal = (id, val) => { const el = $(id); if (el) el.textContent = val ?? 0; };
        setVal('statHadirHariIni', s.hadir_hari_ini);
        setVal('statTotalKartu', s.total_kartu_aktif);
        setVal('statBelumTerdaftar', s.kartu_belum_terdaftar);
    }

    async function loadAttendance() {
        const tbody = $('attendanceTableBody');
        if (!tbody) return;

        const result = await API.getAttendance();
        if (!result.success) {
            tbody.innerHTML = `<tr><td colspan="4"><div class="empty-state"><i class="fa-solid fa-triangle-exclamation"></i><h3>Gagal Memuat</h3><p>Coba muat ulang halaman</p></div></td></tr>`;
            return;
        }

        const rows = result.data.attendance || [];
        const previousLastId = state.attendanceLastId;
        const maxId = rows.length ? Math.max(...rows.map(r => r.id || 0)) : previousLastId;

        state.attendance = rows;
        state.attendanceLastId = maxId;

        renderAttendanceFiltered(previousLastId);
        loadAttendanceStats();
    }

    function renderAttendanceFiltered(previousLastId) {
        const term = (state.deviceSearchTerm || '').toLowerCase().trim();
        const rows = term
            ? state.attendance.filter(r =>
                (r.nama || '').toLowerCase().includes(term) ||
                (r.uid || '').toLowerCase().includes(term) ||
                (r.device_id || '').toLowerCase().includes(term)
              )
            : state.attendance;
        renderAttendanceTable(rows, previousLastId);
    }

    function renderAttendanceTable(rows, previousLastId) {
        const tbody = $('attendanceTableBody');
        if (!tbody) return;

        if (state.attendance.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4"><div class="empty-state"><i class="fa-solid fa-id-card"></i><h3>Belum Ada Aktivitas</h3><p>Belum ada kartu yang ter-tap</p></div></td></tr>`;
            return;
        }
        if (rows.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4"><div class="empty-state"><i class="fa-solid fa-magnifying-glass"></i><h3>Tidak Ditemukan</h3></div></td></tr>`;
            return;
        }

        tbody.innerHTML = rows.map(r => {
            const dt = formatDateTimeSplit(r.timestamp);
            const isNew = previousLastId > 0 && r.id > previousLastId;
            return `
            <tr class="${isNew ? 'row-flash' : ''}">
                <td>${escapeHtml(r.nama)}</td>
                <td><span class="device-id">${escapeHtml(r.uid)}</span></td>
                <td>${escapeHtml(r.device_id)}</td>
                <td><div class="datetime-display"><div class="date">${dt.date}</div><div class="time">${dt.time}</div></div></td>
            </tr>`;
        }).join('');
    }

    function filterAttendance() { renderAttendanceFiltered(0); }

    // ✅ FUNGSI INI YANG HILANG — SEKARANG DITAMBAHKAN
    function startAttendancePolling() {
        stopAttendancePolling();
        state.attendanceInterval = setInterval(loadAttendance, 4000);
    }

    // ✅ FUNGSI INI YANG HILANG — SEKARANG DITAMBAHKAN
    function stopAttendancePolling() {
        if (state.attendanceInterval) {
            clearInterval(state.attendanceInterval);
            state.attendanceInterval = null;
        }
    }

    function openCardholderModal() {
        $('cardholderUid').value = '';
        $('cardholderNama').value = '';
        openModal('cardholderModal');
    }

    async function captureLastTap() {
        const result = await API.getLastUnknownTap();
        if (!result.success) { showToast('Gagal mengambil tap terakhir', 'error'); return; }
        if (!result.data.uid) { showToast('Belum ada kartu asing yang ke-tap', 'error'); return; }
        $('cardholderUid').value = result.data.uid;
    }

    async function submitCardholder() {
        const uid = $('cardholderUid').value.trim();
        const nama = $('cardholderNama').value.trim();
        if (!uid || !nama) { showToast('UID dan Nama wajib diisi!', 'error'); return; }
        const result = await API.addCardholder({ uid, nama });
        if (result.success) {
            closeModal('cardholderModal');
            showToast('Kartu berhasil didaftarkan!', 'success');
            loadAttendance();
        } else {
            showToast(result.error || 'Gagal mendaftarkan kartu', 'error');
        }
    }

    async function openStatDetailModal(type) {
        const titleEl = $('statDetailTitle');
        const thead = $('statDetailThead');
        const tbody = $('statDetailBody');
        tbody.innerHTML = `<tr><td colspan="3" style="text-align:center;padding:30px;color:var(--text-3);">Memuat...</td></tr>`;
        openModal('statDetailModal');

        if (type === 'hadir') {
            titleEl.textContent = 'Hadir Hari Ini';
            thead.innerHTML = `<tr><th>Nama</th><th>UID</th><th style="text-align:right;">Tap Pertama</th></tr>`;
            const result = await API.getAttendanceToday();
            const rows = result.success ? (result.data.hadir || []) : [];
            if (rows.length === 0) {
                tbody.innerHTML = `<tr><td colspan="3" style="text-align:center;padding:30px;color:var(--text-3);">Belum ada yang tap hari ini</td></tr>`;
                return;
            }
            tbody.innerHTML = rows.map(r => `
                <tr><td>${escapeHtml(r.nama)}</td><td><span class="device-id">${escapeHtml(r.uid)}</span></td><td style="text-align:right;">${formatDateTimeSplit(r.pertama_tap).time}</td></tr>
            `).join('');
        } else if (type === 'total') {
            titleEl.textContent = 'Total Kartu Aktif';
            thead.innerHTML = `<tr><th>Nama</th><th>UID</th><th>Terdaftar Sejak</th><th style="text-align:right;">Aksi</th></tr>`;
            const result = await API.getCardholders();
            const rows = result.success ? (result.data.cardholders || []) : [];
            if (rows.length === 0) {
                tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;padding:30px;color:var(--text-3);">Belum ada kartu terdaftar</td></tr>`;
                return;
            }
            tbody.innerHTML = rows.map(r => `
                <tr>
                    <td>${escapeHtml(r.nama)}</td>
                    <td><span class="device-id">${escapeHtml(r.uid)}</span></td>
                    <td>${formatDateTimeSplit(r.created_at).date}</td>
                    <td style="text-align:right;"><button class="action-btn delete" data-action="hapus-cardholder" data-uid="${escapeHtml(r.uid)}" data-nama="${escapeHtml(r.nama)}"><i class="fa-solid fa-trash"></i></button></td>
                </tr>`).join('');
            tbody.querySelectorAll('[data-action="hapus-cardholder"]').forEach(btn => {
                btn.addEventListener('click', () => openDeleteCardholderModal(btn.dataset.uid, btn.dataset.nama));
            });
        } else if (type === 'belum-terdaftar') {
            titleEl.textContent = 'Kartu Belum Terdaftar';
            thead.innerHTML = `<tr><th>UID</th><th>Tap Terakhir</th><th style="text-align:right;">Aksi</th></tr>`;
            const result = await API.getUnregisteredCards();
            const rows = result.success ? (result.data.kartu || []) : [];
            if (rows.length === 0) {
                tbody.innerHTML = `<tr><td colspan="3" style="text-align:center;padding:30px;color:var(--text-3);">Semua kartu sudah terdaftar</td></tr>`;
                return;
            }
            tbody.innerHTML = rows.map(r => {
                const dt = formatDateTimeSplit(r.terakhir_tap);
                return `
                <tr>
                    <td><span class="device-id">${escapeHtml(r.uid)}</span></td>
                    <td>${dt.date} ${dt.time}</td>
                    <td style="text-align:right;"><button class="btn btn-secondary" style="padding:6px 12px;font-size:12px;" data-action="daftarkan-from-detail" data-uid="${escapeHtml(r.uid)}">Daftarkan</button></td>
                </tr>`;
            }).join('');
            tbody.querySelectorAll('[data-action="daftarkan-from-detail"]').forEach(btn => {
                btn.addEventListener('click', () => {
                    closeModal('statDetailModal');
                    $('cardholderUid').value = btn.dataset.uid;
                    $('cardholderNama').value = '';
                    openModal('cardholderModal');
                });
            });
        }
    }

    // ==========================================
    // MAPS
    // ==========================================
    function initMapPreview() {
        if (state.mapPreview) return;
        const el = $('mapPreview');
        if (!el) return;
        state.mapPreview = L.map('mapPreview', {
            zoomControl: true, attributionControl: false,
        }).setView([-2.5489, 118.0149], 5);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 })
            .addTo(state.mapPreview);
    }

    function initFullMap() {
        if (state.mapFull) return;
        const el = $('mapFull');
        if (!el) return;
        state.mapFull = L.map('mapFull').setView([-2.5489, 118.0149], 5);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 })
            .addTo(state.mapFull);

        if (typeof L.markerClusterGroup === 'function') {
            state.markerCluster = L.markerClusterGroup();
            state.mapFull.addLayer(state.markerCluster);
        }

        state.mapFull.on('click', e => {
            state.selectedLat = e.latlng.lat;
            state.selectedLng = e.latlng.lng;

            if (state.marker) state.marker.setLatLng(e.latlng);
            else state.marker = L.marker(e.latlng).addTo(state.mapFull);

            const btn = $('saveLocationBtn');
            if (btn) {
                btn.style.display = 'inline-flex';
                btn.textContent = `Simpan Lokasi ke ${state.selectedMapDeviceId || 'perangkat'}`;
            }

            const info = $('mapSelectedInfo');
            if (info && state.selectedMapDeviceId) {
                info.textContent = `Klik peta untuk memilih lokasi untuk: ${state.selectedMapDeviceId}`;
            }
        });
    }

    function loadMarkers(map, useCluster = false) {
        if (!map) return;

        map.eachLayer(layer => {
            if (layer instanceof L.CircleMarker || layer instanceof L.Marker) {
                map.removeLayer(layer);
            }
        });

        state.devices.forEach(d => {
            if (!d.latitude || !d.longitude) return;

            let color = '#ff453a';
            if (d.status === 'online' && !d.has_alert) color = '#30d158';
            if (d.has_alert) {
                if (d.top_alert_severity === 'danger') color = '#ff453a';
                else if (d.top_alert_severity === 'warning') color = '#ff9f0a';
                else if (d.top_alert_severity === 'info') color = '#0a84ff';
            }

            const popup = `
                <div style="font-family:Inter,sans-serif;min-width:180px;">
                    <div style="font-weight:700;margin-bottom:4px;">${escapeHtml(d.device_name)}</div>
                    <div style="font-size:11px;color:#666;margin-bottom:6px;">ID: ${escapeHtml(d.device_id)}</div>
                    ${d.location ? `<div style="font-size:11px;color:#666;">${escapeHtml(d.location)}</div>` : ''}
                    <div style="font-size:11px;color:#666;">Status: <b style="color:${color};">${escapeHtml(d.status)}</b></div>
                    ${d.has_alert ? `<div style="font-size:11px;color:${color};margin-top:4px;">${escapeHtml(d.top_alert_message || '')}</div>` : ''}
                </div>
            `;

            const marker = L.circleMarker([d.latitude, d.longitude], {
                radius: 8, color, fillColor: color, fillOpacity: 0.75, weight: 2,
            }).bindPopup(popup);

            if (useCluster && state.markerCluster) {
                state.markerCluster.addLayer(marker);
            } else {
                marker.addTo(map);
            }
        });
    }

    function populateMapDeviceSelect() {
        const select = $('mapDeviceSelect');
        if (!select) return;

        const currentValue = select.value || state.selectedMapDeviceId;

        select.innerHTML = '<option value="">Pilih Perangkat...</option>';
        state.devices.forEach(d => {
            select.innerHTML += `<option value="${escapeHtml(d.device_id)}">${escapeHtml(d.device_name)} (${escapeHtml(d.device_id)})</option>`;
        });

        if (currentValue && state.devices.some(d => d.device_id === currentValue)) {
            select.value = currentValue;
            state.selectedMapDeviceId = currentValue;
        } else if (state.devices.length > 0) {
            select.value = state.devices[0].device_id;
            state.selectedMapDeviceId = state.devices[0].device_id;
        } else {
            state.selectedMapDeviceId = null;
        }
        updateMapDeviceInfo();
    }

    function updateMapDeviceInfo() {
        const info = $('mapSelectedInfo');
        if (!info) return;
        const btn = $('saveLocationBtn');
        if (state.selectedMapDeviceId) {
            info.textContent = `Perangkat terpilih: ${state.selectedMapDeviceId}`;
            if (btn) btn.textContent = `Simpan Lokasi ke ${state.selectedMapDeviceId}`;
        } else {
            info.textContent = 'Pilih perangkat terlebih dahulu';
            if (btn) btn.textContent = 'Simpan Lokasi';
        }
    }

    async function saveLocation() {
        const deviceId = state.selectedMapDeviceId;
        if (!deviceId) { showToast('Pilih perangkat terlebih dahulu!', 'error'); return; }
        if (!Number.isFinite(state.selectedLat) || !Number.isFinite(state.selectedLng)) {
            showToast('Klik peta untuk memilih lokasi!', 'error');
            return;
        }

        const result = await API.updateDevice(deviceId, {
            latitude: state.selectedLat,
            longitude: state.selectedLng,
        });

        if (result.success) {
            showToast(`Lokasi untuk ${deviceId} berhasil disimpan!`, 'success');
            loadDashboard();
            if (state.marker) { state.marker.remove(); state.marker = null; }
            state.selectedLat = null;
            state.selectedLng = null;
            const btn = $('saveLocationBtn');
            if (btn) btn.style.display = 'none';
        } else {
            showToast(result.error || 'Gagal menyimpan lokasi', 'error');
        }
    }

    // ==========================================
    // DEVICE FILTER
    // ==========================================
    function setDeviceFilter(filter) {
        state.deviceFilter = filter;
        $$('#deviceFilterBar .filter-btn').forEach(btn =>
            btn.classList.toggle('active', btn.dataset.filter === filter)
        );
        renderFilteredDevices();
    }

    function setDeviceFilterFull(filter) {
        state.deviceFilterFull = filter;
        $$('#deviceFilterBarFull .filter-btn').forEach(btn =>
            btn.classList.toggle('active', btn.dataset.filter === filter)
        );
        renderFilteredDevicesFull();
    }

    function filterDevicesByStatus(devices, filter) {
        switch (filter) {
            case 'online': return devices.filter(d => d.status === 'online' && !d.has_alert);
            case 'offline': return devices.filter(d => d.status === 'offline');
            case 'alert': return devices.filter(d => d.has_alert === true);
            default: return devices;
        }
    }

    function renderFilteredDevices() {
        const filtered = filterDevicesByStatus(state.devices, state.deviceFilter);
        renderTable(filtered, 'deviceTableBody', false);
    }

    function renderFilteredDevicesFull() {
        const filtered = filterDevicesByStatus(state.devices, state.deviceFilterFull);
        renderTable(filtered, 'deviceTableBodyFull', true);
    }

    function updateFilterCounts() {
        const onlineCount = state.devices.filter(d => d.status === 'online' && !d.has_alert).length;
        const offlineCount = state.devices.filter(d => d.status === 'offline').length;
        const alertCount = state.devices.filter(d => d.has_alert === true).length;

        const setText = (id, val) => { const el = $(id); if (el) el.textContent = val; };
        setText('filterCountAll', state.devices.length);
        setText('filterCountOnline', onlineCount);
        setText('filterCountOffline', offlineCount);
        setText('filterCountAlert', alertCount);
    }

    function renderTable(devices, tbodyId, full) {
        const tbody = $(tbodyId);
        if (!tbody) return;

        if (devices.length === 0) {
            tbody.innerHTML = `<tr><td colspan="${full ? 9 : 7}" style="text-align:center;padding:40px;color:var(--text-3);">Tidak ada perangkat</td></tr>`;
            return;
        }

        tbody.innerHTML = devices.map(d => {
            const lastSeen = formatTime(d.last_seen);
            const uptime = formatUptime(d.latest_uptime_seconds || 0);
            const wifi = escapeHtml(d.latest_wifi_ssid || '-');

            let statusClass = d.status || 'offline';
            let statusLabel = d.status || 'offline';

            if (d.has_alert && d.top_alert_severity) {
                statusClass = d.top_alert_severity;
                statusLabel = d.top_alert_severity === 'danger' ? 'BAHAYA'
                            : d.top_alert_severity === 'warning' ? 'PERINGATAN'
                            : d.top_alert_severity.toUpperCase();
            }

            const intervalInfo = d.expected_interval
                ? `<span style="font-size:10px;color:var(--text-3);margin-left:6px;" title="Interval kirim data">${formatUptime(d.expected_interval)}</span>`
                : '';

            const alertCount = d.total_active_alerts > 1
                ? `<span style="font-size:10px;background:rgba(255,69,58,.2);color:var(--red);padding:2px 6px;border-radius:8px;margin-left:6px;">${d.total_active_alerts} alert</span>`
                : '';

            return `
                <tr data-device-id="${escapeHtml(d.device_id)}">
                    <td><span class="status-badge ${statusClass}"><span class="status-dot-inline"></span>${escapeHtml(statusLabel)}</span></td>
                    <td><span class="device-id">${escapeHtml(d.device_id)}</span></td>
                    <td>
                        <span class="device-name">${escapeHtml(d.device_name)}</span>
                        ${intervalInfo}
                        ${alertCount}
                    </td>
                    ${full ? `<td>${escapeHtml(d.device_type || '-')}</td>` : ''}
                    <td>${wifi}</td>
                    <td>${uptime}</td>
                    ${full ? `<td>${escapeHtml(d.location || '-')}</td>` : ''}
                    <td>${lastSeen}</td>
                    <td>
                        <div class="device-actions">
                            <button class="action-btn view" data-action="view" data-device-id="${escapeHtml(d.device_id)}" title="Detail">
                                <i class="fa-solid fa-eye"></i>
                            </button>
                            <button class="action-btn config" data-action="config" data-device-id="${escapeHtml(d.device_id)}" title="Konfigurasi">
                                <i class="fa-solid fa-sliders"></i>
                            </button>
                            <button class="action-btn regenerate" data-action="regenerate-key" data-device-id="${escapeHtml(d.device_id)}" title="Regenerate API Key">
                                <i class="fa-solid fa-key"></i>
                            </button>
                            <button class="action-btn delete" data-action="delete" data-device-id="${escapeHtml(d.device_id)}" title="Hapus">
                                <i class="fa-solid fa-trash"></i>
                            </button>
                        </div>
                    </td>
                </tr>`;
        }).join('');

        tbody.querySelectorAll('[data-action="view"]').forEach(btn =>
            btn.addEventListener('click', () => viewDevice(btn.dataset.deviceId))
        );
        tbody.querySelectorAll('[data-action="config"]').forEach(btn =>
            btn.addEventListener('click', () => openEditDeviceConfig(btn.dataset.deviceId))
        );
        tbody.querySelectorAll('[data-action="regenerate-key"]').forEach(btn =>
            btn.addEventListener('click', () => regenerateApiKey(btn.dataset.deviceId))
        );
        tbody.querySelectorAll('[data-action="delete"]').forEach(btn =>
            btn.addEventListener('click', () => openDeleteModal(btn.dataset.deviceId))
        );
    }

    function filterDevices() {
        const term = (state.deviceSearchTerm || '').toLowerCase().trim();
        const searched = term
            ? state.devices.filter(d =>
                d.device_id.toLowerCase().includes(term) ||
                d.device_name.toLowerCase().includes(term) ||
                (d.location && d.location.toLowerCase().includes(term))
              )
            : state.devices;

        renderTable(filterDevicesByStatus(searched, state.deviceFilter), 'deviceTableBody', false);
        renderTable(filterDevicesByStatus(searched, state.deviceFilterFull), 'deviceTableBodyFull', true);
    }

    function updateHealthRing(summary) {
        const healthy = summary.healthy_devices ?? summary.online_devices ?? 0;
        const total = summary.total_devices ?? 0;
        const pct = total > 0 ? Math.round((healthy / total) * 100) : 0;
        const circumference = 2 * Math.PI * 63;
        const offset = circumference - (pct / 100) * circumference;

        const ring = $('healthRingProgress');
        if (!ring) return;
        ring.setAttribute('stroke-dasharray', circumference.toFixed(1));
        ring.style.strokeDashoffset = offset;

        const pctEl = $('ringPct');
        if (pctEl) pctEl.textContent = pct + '%';

        const captionEl = $('ringCaption');
        if (captionEl) captionEl.textContent = `${healthy} / ${total} perangkat sehat`;
    }

    async function loadDashboard() {
        const result = await API.getDashboard();
        if (!result.success) {
            console.error('[Dashboard] Load failed:', result.error);
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
        populateMapDeviceSelect();
        updateFilterCounts();
        renderFilteredDevices();
        renderFilteredDevicesFull();

        if (state.charts.length === 0) loadChartsFromStorage();
    }

    function viewDevice(id) {
        const backUrl = `/${window.location.hash || '#dashboard'}`;
        try { sessionStorage.setItem(STORAGE_KEYS.BACK_URL, backUrl); } catch (e) {}
        window.location.href = `/device/${encodeURIComponent(id)}`;
    }

    async function regenerateApiKey(deviceId) {
        if (!confirm(`Regenerate API key untuk ${deviceId}?\n\nKey lama tidak akan berfungsi lagi.`)) {
            return;
        }
        const result = await API.regenerateKey(deviceId);
        if (result.success) {
            const display = $('apiKeyDisplay');
            if (display) display.textContent = result.data.api_key;
            openModal('apiKeyModal');
            loadDashboard();
        } else {
            showToast(result.error || 'Gagal regenerate API key', 'error');
        }
    }

    function openAddDeviceModal() {
        if (window.populateAlertRules) window.populateAlertRules('add', null);
        const setVal = (id, val) => { const el = $(id); if (el) el.value = val; };
        setVal('addDeviceId', '');
        setVal('addDeviceName', '');
        setVal('addDeviceLocation', '');
        setVal('addDeviceInterval', '60');
        setVal('addDeviceOfflineTimeout', '');
        setVal('addDeviceOfflineSeverity', 'danger');
        openModal('addDeviceModal');
    }

    async function addDevice() {
        const deviceId = $('addDeviceId').value.trim();
        const deviceName = $('addDeviceName').value.trim();
        if (!deviceId || !deviceName) { showToast('ID dan Nama wajib diisi!', 'error'); return; }

        const alertRules = window.collectAlertRules ? window.collectAlertRules('add') : null;

        const payload = {
            device_id: deviceId,
            device_name: deviceName,
            device_type: $('addDeviceType').value,
            location: $('addDeviceLocation').value.trim(),
            expected_interval: parseInt($('addDeviceInterval')?.value) || 60,
            offline_alert_severity: $('addDeviceOfflineSeverity')?.value || 'danger',
        };

        const offlineTimeout = $('addDeviceOfflineTimeout')?.value;
        if (offlineTimeout) payload.offline_timeout = parseInt(offlineTimeout);
        if (alertRules) payload.alert_rules = alertRules;

        const result = await API.addDevice(payload);

        if (result.success) {
            closeModal('addDeviceModal');
            const display = $('apiKeyDisplay');
            if (display) display.textContent = result.data.device.api_key;
            openModal('apiKeyModal');

            $('addDeviceId').value = '';
            $('addDeviceName').value = '';
            $('addDeviceLocation').value = '';
            if ($('addDeviceInterval')) $('addDeviceInterval').value = '60';
            if ($('addDeviceOfflineTimeout')) $('addDeviceOfflineTimeout').value = '';
            if ($('addDeviceOfflineSeverity')) $('addDeviceOfflineSeverity').value = 'danger';
            if (window.populateAlertRules) window.populateAlertRules('add', null);

            loadDashboard();
        } else {
            const errMsg = typeof result.error === 'object'
                ? Object.values(result.error).flat().join(', ')
                : result.error;
            showToast(errMsg || 'Gagal menambahkan perangkat', 'error');
        }
    }

    function copyApiKey() {
        const text = $('apiKeyDisplay').textContent;
        navigator.clipboard.writeText(text)
            .then(() => showToast('API Key disalin!', 'success'))
            .catch(() => showToast('Gagal menyalin', 'error'));
    }

    async function openEditDeviceConfig(deviceId) {
        const result = await API.getDevice(deviceId);
        if (!result.success) { showToast('Gagal memuat konfigurasi device', 'error'); return; }

        const device = result.data.device;
        $('editConfigDeviceId').value = deviceId;
        $('editDeviceInterval').value = device.expected_interval || 60;
        $('editDeviceOfflineTimeout').value = device.offline_timeout || 900;
        $('editDeviceOfflineSeverity').value = device.offline_alert_severity || 'danger';

        if (window.populateAlertRules) window.populateAlertRules('edit', device.alert_rules);
        openModal('editDeviceConfigModal');
    }

    async function saveDeviceConfig() {
        const deviceId = $('editConfigDeviceId').value;
        if (!deviceId) return;

        const alertRules = window.collectAlertRules ? window.collectAlertRules('edit') : null;

        const payload = {
            expected_interval: parseInt($('editDeviceInterval').value) || 60,
            offline_timeout: parseInt($('editDeviceOfflineTimeout').value) || 900,
            offline_alert_severity: $('editDeviceOfflineSeverity').value,
            alert_rules: alertRules,
        };

        const result = await API.updateDevice(deviceId, payload);
        if (result.success) {
            closeModal('editDeviceConfigModal');
            showToast('Konfigurasi berhasil disimpan', 'success');
            loadDashboard();
        } else {
            const errMsg = typeof result.error === 'object'
                ? Object.values(result.error).flat().join(', ')
                : result.error;
            showToast(errMsg || 'Gagal menyimpan konfigurasi', 'error');
        }
    }

    function openDeleteModal(id) {
        $('deleteType').value = 'device';
        $('deleteDeviceId').value = id;
        $('deleteModalTitle').textContent = 'Hapus Perangkat';
        $('deleteModalText').textContent = `Ketik nama device "${id}" untuk konfirmasi:`;
        const confirmInput = $('deleteConfirmInput');
        if (confirmInput) confirmInput.value = '';
        openModal('deleteModal');
    }

    function openDeleteCardholderModal(uid, nama) {
        $('deleteType').value = 'cardholder';
        $('deleteDeviceId').value = uid;
        $('deleteModalTitle').textContent = 'Hapus Kartu';
        $('deleteModalText').textContent = `Kartu "${nama}" (${uid}) akan dihapus. Riwayat tap lamanya tetap tersimpan.`;
        const confirmInput = $('deleteConfirmInput');
        if (confirmInput) confirmInput.value = '';
        openModal('deleteModal');
    }

    async function confirmDelete() {
        const id = $('deleteDeviceId').value;
        const type = $('deleteType').value;
        if (!id) return;

        if (type === 'device') {
            const confirmInput = $('deleteConfirmInput');
            if (confirmInput && confirmInput.value.trim() !== id) {
                showToast(`Ketik "${id}" untuk konfirmasi`, 'error');
                return;
            }
        }

        const result = type === 'cardholder'
            ? await API.deleteCardholder(id)
            : await API.deleteDevice(id);

        if (result.success) {
            closeModal('deleteModal');
            if (type === 'cardholder') {
                showToast('Kartu dihapus', 'success');
                openStatDetailModal('total');
                loadAttendance();
            } else {
                showToast('Perangkat dihapus', 'success');
                loadDashboard();
            }
        } else {
            showToast(result.error || 'Gagal menghapus', 'error');
        }
    }

    // ==========================================
    // CHARTS
    // ==========================================
    function saveChartsToStorage() {
        const toSave = state.charts.map(chart => {
            const el = document.getElementById(chart.id);
            return {
                id: chart.id, title: chart.title, deviceId: chart.deviceId,
                chartType: chart.chartType, showData: chart.showData,
                width: el?.style.width || '100%',
                height: el?.style.height || '350px',
                x: el?.getAttribute('data-x') || '0',
                y: el?.getAttribute('data-y') || '0',
            };
        });
        localStorage.setItem(STORAGE_KEYS.CHARTS, JSON.stringify(toSave));
    }

    function loadChartsFromStorage() {
        const saved = localStorage.getItem(STORAGE_KEYS.CHARTS);
        if (!saved) return;

        try {
            const list = JSON.parse(saved);
            list.forEach(data => {
                const config = {
                    id: data.id, title: data.title, deviceId: data.deviceId,
                    deviceName: state.devices.find(d => d.device_id === data.deviceId)?.device_name || data.deviceId,
                    chartType: data.chartType, showData: data.showData,
                    chartInstance: null, isLoading: false,
                };
                state.charts.push(config);
                renderChartCard(config, data.width, data.height, data.x, data.y);
                loadDynamicChartData(config);
                initializeDragResize(data.id);
                state.chartIdCounter = Math.max(state.chartIdCounter, parseInt(String(data.id).split('_')[1]) || 0);
            });
        } catch (e) { console.error('[Charts] Load failed:', e); }
    }

    function generateDataCheckboxes(selectedData = {}) {
        const container = $('chartDataCheckboxes');
        if (!container) return;
        container.innerHTML = Object.entries(DATA_KEYS).map(([key, info]) => `
            <label class="checkbox-item">
                <input type="checkbox" class="chart-data-checkbox" data-key="${key}" ${selectedData[key] ? 'checked' : ''}>
                <span class="data-color" style="background:${info.color};"></span>
                <span>${escapeHtml(info.label)} (${escapeHtml(info.unit)})</span>
            </label>
        `).join('');
    }

    function openAddChartModal() {
        $('chartModalTitle').textContent = 'Tambah Diagram';
        $('editChartId').value = '';
        $('chartTitle').value = '';

        const select = $('chartDeviceSelect');
        select.innerHTML = '<option value="">Pilih Perangkat...</option>' +
            state.devices.map(d => `<option value="${escapeHtml(d.device_id)}">${escapeHtml(d.device_name)} (${escapeHtml(d.device_id)})</option>`).join('');

        $('chartTypeSelect').value = 'line';
        generateDataCheckboxes({ temperature: true });
        openModal('chartModal');
    }

    function openEditChartModal(chartId) {
        const chart = state.charts.find(c => c.id === chartId);
        if (!chart) return;

        $('chartModalTitle').textContent = 'Edit Diagram';
        $('editChartId').value = chartId;
        $('chartTitle').value = chart.title;

        const select = $('chartDeviceSelect');
        select.innerHTML = '<option value="">Pilih Perangkat...</option>' +
            state.devices.map(d =>
                `<option value="${escapeHtml(d.device_id)}" ${d.device_id === chart.deviceId ? 'selected' : ''}>${escapeHtml(d.device_name)} (${escapeHtml(d.device_id)})</option>`
            ).join('');

        $('chartTypeSelect').value = chart.chartType;
        generateDataCheckboxes(chart.showData);
        openModal('chartModal');
    }

    function saveChart() {
        const editId = $('editChartId').value;
        const title = $('chartTitle').value.trim() || 'Diagram';
        const deviceId = $('chartDeviceSelect').value;
        const chartType = $('chartTypeSelect').value;

        const showData = {};
        $$('.chart-data-checkbox').forEach(cb => { showData[cb.dataset.key] = cb.checked; });

        if (!deviceId) { showToast('Pilih perangkat terlebih dahulu!', 'error'); return; }
        if (!Object.values(showData).some(v => v)) { showToast('Pilih minimal satu jenis data!', 'error'); return; }

        if (editId) {
            const chart = state.charts.find(c => c.id === editId);
            if (!chart) return;
            chart.title = title;
            chart.deviceId = deviceId;
            chart.deviceName = state.devices.find(d => d.device_id === deviceId)?.device_name || deviceId;
            chart.chartType = chartType;
            chart.showData = showData;

            if (chart.chartInstance) { chart.chartInstance.destroy(); chart.chartInstance = null; }

            const card = document.getElementById(editId);
            if (card) {
                const dataLabels = Object.entries(showData).filter(([_, v]) => v)
                    .map(([k]) => DATA_KEYS[k]?.label || k).join(', ');
                card.querySelector('.chart-card-title').innerHTML = `
                    <i class="fa-solid fa-chart-line"></i> ${escapeHtml(title)}
                    <span style="font-size:10px;color:var(--text-3);font-weight:500;">(${escapeHtml(chart.deviceName)} - ${escapeHtml(dataLabels)})</span>
                `;
            }
            loadDynamicChartData(chart);
            showToast('Diagram berhasil diperbarui', 'success');
        } else {
            const chartId = `chart_${++state.chartIdCounter}`;
            const config = {
                id: chartId, title, deviceId,
                deviceName: state.devices.find(d => d.device_id === deviceId)?.device_name || deviceId,
                chartType, showData, chartInstance: null, isLoading: false,
            };
            state.charts.push(config);
            renderChartCard(config);
            loadDynamicChartData(config);
            initializeDragResize(chartId);
            showToast('Diagram berhasil ditambahkan', 'success');
        }

        saveChartsToStorage();
        closeModal('chartModal');
    }

    function renderChartCard(config, width = '100%', height = '350px', x = '0', y = '0') {
        const grid = $('chartsGrid');
        if (!grid) return;
        const emptyState = grid.querySelector('.empty-charts');
        if (emptyState) emptyState.remove();

        const card = document.createElement('div');
        card.className = 'chart-card';
        card.id = config.id;
        card.style.width = width;
        card.style.height = height;
        card.setAttribute('data-x', x);
        card.setAttribute('data-y', y);
        if (x !== '0' || y !== '0') card.style.transform = `translate(${x}px, ${y}px)`;

        const dataLabels = Object.entries(config.showData).filter(([_, v]) => v)
            .map(([k]) => DATA_KEYS[k]?.label || k).join(', ');

        card.innerHTML = `
            <div class="chart-card-header">
                <div class="chart-card-title">
                    <i class="fa-solid fa-chart-line"></i> ${escapeHtml(config.title)}
                    <span style="font-size:10px;color:var(--text-3);font-weight:500;">(${escapeHtml(config.deviceName)} - ${escapeHtml(dataLabels)})</span>
                </div>
                <div class="chart-actions">
                    <button class="chart-edit-btn" data-action="download" data-chart-id="${config.id}" title="Download PNG"><i class="fa-solid fa-download"></i></button>
                    <button class="chart-edit-btn" data-action="edit" data-chart-id="${config.id}" title="Edit"><i class="fa-solid fa-pen"></i></button>
                    <button class="chart-remove-btn" data-action="remove" data-chart-id="${config.id}" title="Hapus"><i class="fa-solid fa-trash"></i></button>
                </div>
            </div>
            <div class="chart-card-body">
                <div class="chart-canvas-container"><canvas id="${config.id}_canvas"></canvas></div>
            </div>
            <div class="chart-resize-handle"></div>
        `;

        grid.appendChild(card);

        const header = card.querySelector('.chart-card-header');
        header.style.touchAction = 'none';
        header.style.webkitUserSelect = 'none';
        header.style.userSelect = 'none';

        card.querySelector('[data-action="download"]').addEventListener('click', e => {
            e.stopPropagation(); e.preventDefault();
            downloadChartImage(config.id);
        });
        card.querySelector('[data-action="edit"]').addEventListener('click', e => {
            e.stopPropagation(); e.preventDefault();
            openEditChartModal(config.id);
        });
        card.querySelector('[data-action="remove"]').addEventListener('click', e => {
            e.stopPropagation(); e.preventDefault();
            removeChart(config.id);
        });
    }

    function downloadChartImage(chartId) {
        const chart = state.charts.find(c => c.id === chartId);
        if (!chart || !chart.chartInstance) {
            showToast('Chart belum siap', 'error');
            return;
        }
        try {
            const url = chart.chartInstance.toBase64Image('image/png', 1.0);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${chart.title.replace(/[^a-zA-Z0-9]/g, '_')}_${Date.now()}.png`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            showToast('Chart diunduh', 'success');
        } catch (e) {
            showToast('Gagal mengunduh chart', 'error');
        }
    }

    function initializeDragResize(chartId) {
        const el = document.getElementById(chartId);
        if (!el || typeof interact === 'undefined') return;

        interact(el)
            .draggable({
                allowFrom: '.chart-card-header', ignoreFrom: '.chart-actions',
                inertia: true,
                modifiers: [interact.modifiers.restrictRect({ restriction: '#chartsGrid', endOnly: false })],
                autoScroll: true,
                listeners: {
                    start() { el.classList.add('dragging'); },
                    move(event) {
                        const target = event.target;
                        const x = (parseFloat(target.getAttribute('data-x')) || 0) + event.dx;
                        const y = (parseFloat(target.getAttribute('data-y')) || 0) + event.dy;
                        target.style.transform = `translate(${x}px, ${y}px)`;
                        target.setAttribute('data-x', x);
                        target.setAttribute('data-y', y);
                    },
                    end() { el.classList.remove('dragging'); saveChartsToStorage(); },
                },
            })
            .resizable({
                edges: { right: true, bottom: true, left: false, top: false },
                inertia: true,
                modifiers: [interact.modifiers.restrictSize({ min: { width: 280, height: 200 } })],
                listeners: {
                    start() { el.classList.add('resizing'); },
                    move(event) {
                        Object.assign(el.style, {
                            width: `${event.rect.width}px`,
                            height: `${event.rect.height}px`,
                        });
                        const chart = state.charts.find(c => c.id === chartId);
                        if (chart?.chartInstance) chart.chartInstance.resize();
                    },
                    end() {
                        el.classList.remove('resizing');
                        const chart = state.charts.find(c => c.id === chartId);
                        if (chart?.chartInstance) chart.chartInstance.resize();
                        saveChartsToStorage();
                    },
                },
            });
    }

    function initializeChartsGridResize() {
        const wrapper = document.querySelector('.charts-grid-wrapper');
        const grid = $('chartsGrid');
        if (!wrapper || !grid || typeof interact === 'undefined') return;

        interact(wrapper).resizable({
            edges: { right: false, bottom: true, left: false, top: false },
            inertia: false,
            modifiers: [interact.modifiers.restrictSize({ min: { width: 0, height: 400 } })],
            listeners: {
                move(event) {
                    grid.style.height = `${event.rect.height}px`;
                    grid.style.width = '100%';
                    grid.style.minWidth = '100%';
                    grid.style.maxWidth = '100%';
                },
                end() {
                    state.charts.forEach(c => { if (c.chartInstance) c.chartInstance.resize(); });
                },
            },
        });
    }

    function removeChart(chartId) {
        const idx = state.charts.findIndex(c => c.id === chartId);
        if (idx !== -1) {
            if (state.charts[idx].chartInstance) {
                try { state.charts[idx].chartInstance.destroy(); } catch (e) {}
            }
            state.charts.splice(idx, 1);
        }
        const card = document.getElementById(chartId);
        if (card) {
            try { interact(card).unset(); } catch (e) {}
            card.remove();
        }

        if (state.charts.length === 0) {
            const grid = $('chartsGrid');
            if (grid) grid.innerHTML = `
                <div class="empty-charts" style="text-align:center;padding:40px;color:var(--text-3);grid-column:1/-1;">
                    <i class="fa-solid fa-chart-column" style="font-size:40px;margin-bottom:12px;display:block;"></i>
                    <p style="font-size:14px;font-weight:600;">Belum ada diagram</p>
                    <p style="font-size:12px;margin-top:4px;">Klik "Tambah Diagram" untuk membuat visualisasi baru</p>
                </div>`;
        }
        saveChartsToStorage();
        showToast('Diagram dihapus', 'success');
    }

    function resetChartLayout() {
        state.charts.forEach(chart => {
            const el = document.getElementById(chart.id);
            if (el) {
                el.style.transform = '';
                el.setAttribute('data-x', 0);
                el.setAttribute('data-y', 0);
                el.style.width = '100%';
                el.style.height = '350px';
                if (chart.chartInstance) chart.chartInstance.resize();
            }
        });
        saveChartsToStorage();
        showToast('Layout diagram direset', 'success');
    }

    async function loadDynamicChartData(config) {
        if (config.isLoading) return;
        config.isLoading = true;

        try {
            const hours = Math.max(1, Math.ceil(state.globalTimeMinutes / 60));
            const result = await API.getDeviceHistory(config.deviceId, { hours });

            if (!result.success || !result.data.history?.length) {
                showChartEmpty(config.id, 'Menunggu data sensor...');
                return;
            }

            const now = Date.now();
            const cutoffTime = now - state.globalTimeMinutes * 60 * 1000;
            const filtered = result.data.history.filter(item => {
                const d = parseDate(item.timestamp);
                return d && d.getTime() >= cutoffTime;
            });

            if (filtered.length === 0) {
                if (result.data.history.length > 0) await renderChartData(config, result.data.history);
                else showChartEmpty(config.id, 'Menunggu data...');
                return;
            }
            await renderChartData(config, filtered);
        } catch (e) {
            console.error('[Chart] Load failed:', e);
        } finally {
            config.isLoading = false;
        }
    }

    async function renderChartData(config, historyData) {
        const canvas = document.getElementById(`${config.id}_canvas`);
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        const colors = getChartColors();

        if (config.chartInstance) {
            try { config.chartInstance.destroy(); } catch (e) {}
            config.chartInstance = null;
        }

        const labels = historyData.map(item => {
            const d = parseDate(item.timestamp);
            if (!d) return '';
            try {
                return d.toLocaleTimeString('id-ID', {
                    hour: '2-digit', minute: '2-digit', second: '2-digit',
                    timeZone: 'Asia/Jakarta',
                });
            } catch (e) { return ''; }
        });

        const activeKeys = Object.entries(config.showData).filter(([_, v]) => v).map(([k]) => k);

        const datasets = [];
        for (let i = 0; i < activeKeys.length; i++) {
            const key = activeKeys[i];
            const info = DATA_KEYS[key];
            if (!info) continue;

            const values = historyData.map(item => {
                const d = item.data || {};
                return d[key] ?? d[key.toLowerCase()] ?? d[key.toUpperCase()] ?? null;
            });

            if (!values.some(v => v !== null && v !== undefined)) continue;

            const color = CHART_COLORS[i % CHART_COLORS.length];
            const isArea = config.chartType === 'area' || config.chartType === 'stackedArea';
            const isStacked = config.chartType === 'stackedBar' || config.chartType === 'stackedArea';

            datasets.push({
                label: `${info.label} (${info.unit})`,
                data: values,
                borderColor: color,
                backgroundColor: isArea ? color + '30' : color + '80',
                fill: isArea, tension: 0.35, pointRadius: 2, pointHoverRadius: 5,
                pointBackgroundColor: color, pointBorderColor: colors.pointBorderColor,
                pointBorderWidth: 1, borderWidth: 2,
                stack: isStacked ? 'stack1' : undefined,
            });
        }

        if (datasets.length === 0) {
            showChartEmpty(config.id, 'Tidak ada data sensor yang cocok');
            return;
        }

        if (['doughnut', 'pie', 'polarArea', 'radar'].includes(config.chartType)) {
            const latest = historyData[historyData.length - 1];
            const gaugeLabels = [], gaugeValues = [];
            activeKeys.forEach(key => {
                const info = DATA_KEYS[key];
                if (!info) return;
                const val = latest.data?.[key];
                if (val !== null && val !== undefined) {
                    gaugeLabels.push(info.label);
                    gaugeValues.push(val);
                }
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
                animation: { duration: 750, easing: 'easeOutQuart' },
                plugins: {
                    legend: {
                        labels: {
                            color: colors.legendColor, font: { size: 11, family: CHART_FONT },
                            usePointStyle: true, pointStyle: 'circle', padding: 12,
                        },
                    },
                    tooltip: {
                        backgroundColor: colors.tooltipBg, titleColor: colors.tooltipTitleColor,
                        bodyColor: colors.tooltipBodyColor, borderColor: colors.tooltipBorder,
                        borderWidth: 1, padding: 12, cornerRadius: 10, displayColors: true, boxPadding: 5,
                    },
                },
                scales: {
                    x: {
                        grid: { color: colors.gridColor },
                        ticks: { color: colors.labelColor, font: { family: CHART_FONT }, maxTicksLimit: 10, maxRotation: 45, autoSkip: true },
                        stacked: config.chartType === 'stackedBar' || config.chartType === 'stackedArea',
                    },
                    y: {
                        grid: { color: colors.gridColor },
                        ticks: { color: colors.labelColor, font: { family: CHART_FONT } },
                        stacked: config.chartType === 'stackedBar' || config.chartType === 'stackedArea',
                        beginAtZero: true,
                    },
                },
            },
        });
    }

    function showChartEmpty(chartId, message) {
        const container = document.querySelector(`#${chartId} .chart-canvas-container`);
        if (!container) return;
        container.innerHTML = `
            <div style="text-align:center;padding:40px;color:var(--text-3);font-size:13px;display:flex;flex-direction:column;align-items:center;gap:10px;">
                <i class="fa-solid fa-satellite-dish" style="font-size:24px;opacity:0.5;"></i>
                <span>${escapeHtml(message)}</span>
                <span style="font-size:11px;">Data akan muncul otomatis saat tersedia</span>
            </div>`;
    }

    function refreshAllCharts() {
        if (state.refreshTimeout) clearTimeout(state.refreshTimeout);
        state.refreshTimeout = setTimeout(() => {
            state.charts.forEach(c => loadDynamicChartData(c));
        }, 300);
    }

    function startAutoRefresh() {
        if (state.autoRefreshInterval) clearInterval(state.autoRefreshInterval);
        state.autoRefreshInterval = setInterval(() => {
            const graph = $('graphSection');
            if (graph && graph.style.display !== 'none') refreshAllCharts();
        }, 15000);
    }

    function openModal(id) { const el = $(id); if (el) el.classList.add('active'); }
    function closeModal(id) { const el = $(id); if (el) el.classList.remove('active'); }

    function setGlobalTimeRange(minutes) {
        state.globalTimeMinutes = minutes;
        $$('.time-range-btn').forEach(btn =>
            btn.classList.toggle('active', parseInt(btn.dataset.minutes) === minutes)
        );
        localStorage.setItem(STORAGE_KEYS.GLOBAL_TIME, minutes);
        refreshAllCharts();
        showToast(`Rentang waktu: ${formatTimeRange(minutes)}`, 'success');
    }

    function loadGlobalTimeRange() {
        const saved = localStorage.getItem(STORAGE_KEYS.GLOBAL_TIME);
        if (saved) {
            state.globalTimeMinutes = parseInt(saved);
            $$('.time-range-btn').forEach(btn =>
                btn.classList.toggle('active', parseInt(btn.dataset.minutes) === state.globalTimeMinutes)
            );
        }
    }

    function showToast(message, type) {
        if (window.showToast) window.showToast(message, type);
    }

    function bindSidebarNav() {
        document.querySelectorAll('.sidebar-nav .nav-item').forEach((item) => {
            item.addEventListener('click', (e) => {
                const href = (item.getAttribute('href') || '').trim();

                if (href.startsWith('#')) {
                    e.preventDefault();
                    const targetSection = href.replace('#', '');
                    if (DASHBOARD_SECTIONS.includes(targetSection)) {
                        showSection(targetSection);
                    }
                    return;
                }

                return;
            });
        });
    }

    function bindLogout() {
        const logoutBtn = $('logoutBtn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', (e) => {
                e.preventDefault();
                window.location.href = '/logout';
            });
        }
    }

    function bindEvents() {
        const logo = document.querySelector('.logo-ring');
        if (logo) logo.addEventListener('click', toggleSidebar);

        bindSidebarNav();
        bindLogout();

        const themeBtn = $('themeToggleBtn');
        if (themeBtn) {
            themeBtn.addEventListener('click', () => {
                // ✅ P0 FIX: ThemeManager hanya global via window
                const newTheme = window.ThemeManager.toggle();
                updateThemeUI(newTheme);
                setTimeout(refreshAllCharts, 100);
            });
        }

        document.querySelectorAll('[data-action="open-cardholder-modal"]').forEach(btn =>
            btn.addEventListener('click', openCardholderModal)
        );
        document.querySelectorAll('[data-action="capture-last-tap"]').forEach(btn =>
            btn.addEventListener('click', captureLastTap)
        );
        document.querySelectorAll('[data-action="submit-cardholder"]').forEach(btn =>
            btn.addEventListener('click', submitCardholder)
        );
        document.querySelectorAll('.stat-card.clickable').forEach(card => {
            card.addEventListener('click', () => openStatDetailModal(card.dataset.statType));
        });

        const searchInput = $('searchInput');
        if (searchInput) {
            searchInput.addEventListener('input', () => {
                state.deviceSearchTerm = searchInput.value;
                if (state.currentSection === 'attendance') filterAttendance();
                else filterDevices();
            });
        }

        document.querySelectorAll('[data-action="add-device"]').forEach(btn =>
            btn.addEventListener('click', openAddDeviceModal)
        );
        document.querySelectorAll('[data-action="add-chart"]').forEach(btn =>
            btn.addEventListener('click', openAddChartModal)
        );
        document.querySelectorAll('[data-action="refresh-charts"]').forEach(btn =>
            btn.addEventListener('click', refreshAllCharts)
        );
        document.querySelectorAll('[data-action="reset-layout"]').forEach(btn =>
            btn.addEventListener('click', resetChartLayout)
        );

        const saveBtn = $('saveLocationBtn');
        if (saveBtn) saveBtn.addEventListener('click', saveLocation);

        const mapSelect = $('mapDeviceSelect');
        if (mapSelect) {
            mapSelect.addEventListener('change', function() {
                state.selectedMapDeviceId = this.value;
                updateMapDeviceInfo();
                if (state.marker) { state.marker.remove(); state.marker = null; }
                state.selectedLat = null;
                state.selectedLng = null;
                if (saveBtn) saveBtn.style.display = 'none';
            });
        }

        document.querySelectorAll('.time-range-btn').forEach(btn => {
            btn.addEventListener('click', () => setGlobalTimeRange(parseInt(btn.dataset.minutes)));
        });

        document.querySelectorAll('#deviceFilterBar .filter-btn').forEach(btn => {
            btn.addEventListener('click', () => setDeviceFilter(btn.dataset.filter));
        });
        document.querySelectorAll('#deviceFilterBarFull .filter-btn').forEach(btn => {
            btn.addEventListener('click', () => setDeviceFilterFull(btn.dataset.filter));
        });

        document.querySelectorAll('.modal-close').forEach(btn => {
            btn.addEventListener('click', () => {
                const modal = btn.closest('.modal');
                if (modal) modal.classList.remove('active');
            });
        });

        document.querySelectorAll('.modal').forEach(modal => {
            modal.addEventListener('click', e => {
                if (e.target === modal) modal.classList.remove('active');
            });
        });

        document.querySelectorAll('[data-action="submit-add-device"]').forEach(btn =>
            btn.addEventListener('click', addDevice)
        );
        document.querySelectorAll('[data-action="save-device-config"]').forEach(btn =>
            btn.addEventListener('click', saveDeviceConfig)
        );
        document.querySelectorAll('[data-action="copy-api-key"]').forEach(btn =>
            btn.addEventListener('click', copyApiKey)
        );
        document.querySelectorAll('[data-action="confirm-delete"]').forEach(btn =>
            btn.addEventListener('click', confirmDelete)
        );
        document.querySelectorAll('[data-action="save-chart"]').forEach(btn =>
            btn.addEventListener('click', saveChart)
        );

        document.addEventListener('keydown', e => {
            if (e.key === 'Escape') {
                document.querySelectorAll('.modal.active').forEach(m => m.classList.remove('active'));
            }
        });

        window.addEventListener('popstate', () => {
            const section = getSectionFromHash();
            showSection(section, true);
        });

        window.addEventListener('hashchange', () => {
            const section = getSectionFromHash();
            if (state.currentSection !== section) {
                showSection(section, true);
            }
        });

        window.ThemeManager.onChange(() => setTimeout(refreshAllCharts, 100));
    }

    function updateThemeUI(theme) {
        const icon = $('themeIcon');
        const label = $('themeLabel');
        if (icon) icon.className = theme === 'light' ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
        if (label) label.textContent = theme === 'light' ? 'Tema Terang' : 'Tema Gelap';
    }

        async function init() {
        bindEvents();
        updateThemeUI(window.ThemeManager.get());
        loadGlobalTimeRange();
        updateDateTime();
        setInterval(updateDateTime, 1000);

        // ✅ FIX: Tentukan section SEBELUM apapun — biar tidak flash dashboard dulu
        let initialSection = getSectionFromHash();

        if (!window.location.hash) {
            try {
                const savedSection = sessionStorage.getItem(STORAGE_KEYS.LAST_SECTION);
                if (savedSection && DASHBOARD_SECTIONS.includes(savedSection)) {
                    initialSection = savedSection;
                    history.replaceState(null, '', `#${savedSection}`);
                }
            } catch (e) {}
        }

        // ✅ FIX: Set visibility section PALING AWAL — sebelum apapun dirender
        // Ini bikin dashboard langsung "hilang" dan section yang benar tampil
        ['dashboard', 'map', 'graph', 'attendance', 'devices'].forEach(s => {
            const el = $(s + 'Section');
            if (el) el.style.display = s === initialSection ? 'block' : 'none';
        });

        // Update sidebar active state juga sebelum render
        $$('.sidebar-nav .nav-item[data-section]').forEach((item) => {
            const sec = item.getAttribute('data-section');
            item.classList.toggle('active', sec === initialSection);
        });

        // Update page title juga
        const titles = {
            dashboard: 'Dashboard',
            map: 'Peta Interaktif',
            graph: 'Analitik Sensor',
            devices: 'Manajemen Perangkat',
            attendance: 'Absensi',
        };
        const titleEl = $('pageTitle');
        if (titleEl) titleEl.textContent = titles[initialSection] || 'Dashboard';

        state.currentSection = initialSection;

        initMapPreview();

        // ✅ Sekarang baru load data (setelah section visible)
        await loadDashboard();
        showSection(initialSection, true);

        state.dashboardInterval = setInterval(loadDashboard, 30000);
        startAutoRefresh();
        initializeChartsGridResize();

        console.log('[Dashboard] Ready, section:', initialSection);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else init();
})();