/* ==========================================
   NEXUS IoT - Dashboard Logic
   ========================================== */

(function() {
    'use strict';

    // ==========================================
    // STATE
    // ==========================================
    const state = {
        devices: [],
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
        dashboardInterval: null
    };

    // ==========================================
    // CONSTANTS
    // ==========================================
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
        co2: { label: 'CO2', unit: 'ppm', color: '#30d158' }
    };

    const STORAGE_KEYS = {
        THEME: 'nexus-theme',
        CHARTS: 'nexus-dynamic-charts',
        GLOBAL_TIME: 'nexus-global-time'
    };

    // ==========================================
    // HELPERS
    // ==========================================
    function $(id) { return document.getElementById(id); }
    function $$(selector) { return document.querySelectorAll(selector); }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = String(str ?? '');
        return div.innerHTML;
    }

    function formatUptime(seconds) {
        if (!seconds) return '-';
        const d = Math.floor(seconds / 86400);
        const h = Math.floor((seconds % 86400) / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        if (d > 0) return `${d}h ${h}j`;
        if (h > 0) return `${h}j ${m}m`;
        return `${m}m`;
    }

    function formatTime(iso) {
        if (!iso) return '-';
        try {
            return new Date(iso).toLocaleTimeString('id-ID', {
                hour: '2-digit',
                minute: '2-digit',
                timeZone: 'Asia/Jakarta'
            });
        } catch (e) { return '-'; }
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
            pointBorderColor: isLight ? '#fff' : '#000'
        };
    }

    // ==========================================
    // SIDEBAR & NAVIGATION
    // ==========================================
    function toggleSidebar() {
        $('sidebar').classList.toggle('collapsed');
        $('mainContent').classList.toggle('expanded');
        setTimeout(() => {
            if (state.mapPreview) state.mapPreview.invalidateSize();
            if (state.mapFull) state.mapFull.invalidateSize();
        }, 380);
    }

    function showSection(section) {
        ['dashboard', 'map', 'graph', 'devices'].forEach(s => {
            const el = $(s + 'Section');
            if (el) el.style.display = s === section ? 'block' : 'none';
        });

        const titles = {
            dashboard: 'Dashboard',
            map: 'Peta Interaktif',
            graph: 'Analitik Sensor',
            devices: 'Manajemen Perangkat'
        };
        $('pageTitle').textContent = titles[section] || 'Dashboard';

        $$('.sidebar-nav .nav-item').forEach((item, i) => {
            const sections = ['dashboard', 'map', 'graph', 'devices'];
            item.classList.toggle('active', sections[i] === section);
        });

        if (section === 'map' && !state.mapFull) {
            setTimeout(initFullMap, 100);
            setTimeout(populateMapDeviceSelect, 150);
        }
        if (section === 'dashboard') {
            setTimeout(() => { if (state.mapPreview) state.mapPreview.invalidateSize(); }, 100);
        }
        if (section === 'graph') {
            setTimeout(refreshAllCharts, 100);
        }
    }

    // ==========================================
    // DATETIME
    // ==========================================
    function updateDateTime() {
        const now = new Date();
        $('currentDate').textContent = now.toLocaleDateString('id-ID', {
            weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
            timeZone: 'Asia/Jakarta'
        });
        $('currentTime').textContent = now.toLocaleTimeString('id-ID', {
            hour: '2-digit', minute: '2-digit', second: '2-digit',
            timeZone: 'Asia/Jakarta'
        }) + ' WIB';
    }

    // ==========================================
    // MAPS
    // ==========================================
    function initMapPreview() {
        state.mapPreview = L.map('mapPreview', {
            zoomControl: true,
            attributionControl: false
        }).setView([-2.5489, 118.0149], 5);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19
        }).addTo(state.mapPreview);
    }

    function initFullMap() {
        if (state.mapFull) return;
        state.mapFull = L.map('mapFull').setView([-2.5489, 118.0149], 5);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19
        }).addTo(state.mapFull);

        state.mapFull.on('click', e => {
            state.selectedLat = e.latlng.lat;
            state.selectedLng = e.latlng.lng;

            if (state.marker) {
                state.marker.setLatLng(e.latlng);
            } else {
                state.marker = L.marker(e.latlng).addTo(state.mapFull);
            }

            const btn = $('saveLocationBtn');
            btn.style.display = 'inline-flex';
            btn.textContent = `Simpan Lokasi ke ${state.selectedMapDeviceId || 'perangkat'}`;

            if (state.selectedMapDeviceId) {
                $('mapSelectedInfo').textContent = `📍 Klik peta untuk memilih lokasi untuk: ${state.selectedMapDeviceId}`;
            }
        });
    }

    function loadMarkers(map) {
        if (!map) return;
        // Hapus marker lama
        map.eachLayer(layer => {
            if (layer instanceof L.CircleMarker) map.removeLayer(layer);
        });

        state.devices.forEach(d => {
            if (d.latitude && d.longitude) {
                const color = d.status === 'online' ? '#30d158'
                    : d.status === 'alert' ? '#ff9f0a'
                    : '#ff453a';
                L.circleMarker([d.latitude, d.longitude], {
                    radius: 8,
                    color,
                    fillColor: color,
                    fillOpacity: 0.75,
                    weight: 2
                }).addTo(map).bindPopup(`<b>${escapeHtml(d.device_name)}</b><br>ID: ${escapeHtml(d.device_id)}`);
            }
        });
    }

    function populateMapDeviceSelect() {
        const select = $('mapDeviceSelect');
        if (!select) return;
        select.innerHTML = '<option value="">Pilih Perangkat…</option>';
        state.devices.forEach(d => {
            select.innerHTML += `<option value="${escapeHtml(d.device_id)}">${escapeHtml(d.device_name)} (${escapeHtml(d.device_id)})</option>`;
        });

        if (state.devices.length > 0) {
            select.value = state.devices[0].device_id;
            state.selectedMapDeviceId = state.devices[0].device_id;
            updateMapDeviceInfo();
        }
    }

    function updateMapDeviceInfo() {
        const info = $('mapSelectedInfo');
        if (state.selectedMapDeviceId) {
            info.textContent = `📍 Perangkat terpilih: ${state.selectedMapDeviceId}`;
            $('saveLocationBtn').textContent = `Simpan Lokasi ke ${state.selectedMapDeviceId}`;
        } else {
            info.textContent = '⚠️ Pilih perangkat terlebih dahulu';
            $('saveLocationBtn').textContent = 'Simpan Lokasi';
        }
    }

    async function saveLocation() {
        const deviceId = state.selectedMapDeviceId;
        if (!deviceId) {
            showToast('Pilih perangkat terlebih dahulu!', 'error');
            return;
        }
        if (!state.selectedLat || !state.selectedLng) {
            showToast('Klik peta untuk memilih lokasi!', 'error');
            return;
        }

        const result = await API.updateDevice(deviceId, {
            latitude: state.selectedLat,
            longitude: state.selectedLng
        });

        if (result.success) {
            showToast(`Lokasi untuk ${deviceId} berhasil disimpan!`, 'success');
            loadDashboard();
            if (state.marker) {
                state.marker.remove();
                state.marker = null;
            }
            state.selectedLat = null;
            state.selectedLng = null;
            $('saveLocationBtn').style.display = 'none';
        } else {
            showToast(result.error || 'Gagal menyimpan lokasi', 'error');
        }
    }

    // ==========================================
    // DEVICE FILTER
    // ==========================================
    function setDeviceFilter(filter) {
        state.deviceFilter = filter;
        $$('#deviceFilterBar .filter-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.filter === filter);
        });
        renderFilteredDevices();
    }

    function setDeviceFilterFull(filter) {
        state.deviceFilterFull = filter;
        $$('#deviceFilterBarFull .filter-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.filter === filter);
        });
        renderFilteredDevicesFull();
    }

    function getDeviceAlertStatus(device) {
        return device.status === 'alert';
    }

    function filterDevicesByStatus(devices, filter) {
        switch (filter) {
            case 'online': return devices.filter(d => d.status === 'online');
            case 'offline': return devices.filter(d => d.status === 'offline');
            case 'alert': return devices.filter(d => getDeviceAlertStatus(d));
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
        const onlineCount = state.devices.filter(d => d.status === 'online').length;
        const offlineCount = state.devices.filter(d => d.status === 'offline').length;
        const alertCount = state.devices.filter(d => getDeviceAlertStatus(d)).length;

        const setText = (id, val) => {
            const el = $(id);
            if (el) el.textContent = val;
        };

        setText('filterCountAll', state.devices.length);
        setText('filterCountOnline', onlineCount);
        setText('filterCountOffline', offlineCount);
        setText('filterCountAlert', alertCount);
    }

    // ==========================================
    // TABLE RENDERING
    // ==========================================
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
            const statusClass = getDeviceAlertStatus(d) ? 'alert' : (d.status || 'offline');

            return `
                <tr>
                    <td><span class="status-badge ${statusClass}"><span class="status-dot-inline"></span>${statusClass}</span></td>
                    <td><span class="device-id">${escapeHtml(d.device_id)}</span></td>
                    <td><span class="device-name">${escapeHtml(d.device_name)}</span></td>
                    ${full ? `<td>${escapeHtml(d.device_type || '-')}</td>` : ''}
                    <td>${wifi}</td>
                    <td>${uptime}</td>
                    ${full ? `<td>${escapeHtml(d.location || '-')}</td>` : ''}
                    <td>${lastSeen}</td>
                    <td>
                        <div class="device-actions">
                            <button class="action-btn view" data-action="view" data-device-id="${escapeHtml(d.device_id)}">
                                <i class="fa-solid fa-eye"></i>
                            </button>
                            <button class="action-btn delete" data-action="delete" data-device-id="${escapeHtml(d.device_id)}">
                                <i class="fa-solid fa-trash"></i>
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');

        // Attach event listeners
        tbody.querySelectorAll('[data-action="view"]').forEach(btn => {
            btn.addEventListener('click', () => viewDevice(btn.dataset.deviceId));
        });
        tbody.querySelectorAll('[data-action="delete"]').forEach(btn => {
            btn.addEventListener('click', () => openDeleteModal(btn.dataset.deviceId));
        });
    }

    function filterDevices() {
        const term = ($('searchInput')?.value || '').toLowerCase().trim();
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

    // ==========================================
    // HEALTH RING
    // ==========================================
    function updateHealthRing(online, total) {
        const pct = total > 0 ? Math.round((online / total) * 100) : 0;
        const circumference = 2 * Math.PI * 63;
        const offset = circumference - (pct / 100) * circumference;

        const ring = $('healthRingProgress');
        ring.setAttribute('stroke-dasharray', circumference.toFixed(1));
        ring.style.strokeDashoffset = offset;

        $('ringPct').textContent = pct + '%';
        $('ringCaption').textContent = `${online} / ${total} perangkat aktif`;
    }

    // ==========================================
    // LOAD DASHBOARD DATA
    // ==========================================
    async function loadDashboard() {
        const result = await API.getDashboard();
        if (!result.success) {
            console.error('[Dashboard] Load failed:', result.error);
            return;
        }

        const { summary, devices } = result.data;
        state.devices = devices;

        $('totalDevices').textContent = summary.total_devices;
        $('onlineDevices').textContent = summary.online_devices;
        $('offlineDevices').textContent = summary.offline_devices;
        $('deviceBadge').textContent = summary.total_devices;

        const alertsEl = $('activeAlerts');
        if (alertsEl) alertsEl.textContent = summary.active_alerts || 0;

        updateHealthRing(summary.online_devices, summary.total_devices);
        loadMarkers(state.mapPreview);
        if (state.mapFull) loadMarkers(state.mapFull);
        populateMapDeviceSelect();
        updateFilterCounts();
        renderFilteredDevices();
        renderFilteredDevicesFull();

        if (state.charts.length === 0) {
            loadChartsFromStorage();
        }
    }

    // ==========================================
    // DEVICE ACTIONS
    // ==========================================
    function viewDevice(id) {
        window.location.href = `/device/${encodeURIComponent(id)}`;
    }

    function openAddDeviceModal() {
        $('addDeviceModal').classList.add('active');
    }

    async function addDevice() {
        const deviceId = $('addDeviceId').value.trim();
        const deviceName = $('addDeviceName').value.trim();

        if (!deviceId || !deviceName) {
            showToast('ID dan Nama wajib diisi!', 'error');
            return;
        }

        const result = await API.addDevice({
            device_id: deviceId,
            device_name: deviceName,
            device_type: $('addDeviceType').value,
            location: $('addDeviceLocation').value.trim()
        });

        if (result.success) {
            closeModal('addDeviceModal');
            $('apiKeyDisplay').textContent = result.data.device.api_key;
            openModal('apiKeyModal');
            // Reset form
            $('addDeviceId').value = '';
            $('addDeviceName').value = '';
            $('addDeviceLocation').value = '';
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
        navigator.clipboard.writeText(text).then(() => {
            showToast('API Key disalin!', 'success');
        });
    }

    function openDeleteModal(id) {
        $('deleteDeviceId').value = id;
        openModal('deleteModal');
    }

    async function confirmDelete() {
        const id = $('deleteDeviceId').value;
        if (!id) return;

        const result = await API.deleteDevice(id);

        if (result.success) {
            closeModal('deleteModal');
            showToast('Perangkat dihapus', 'success');
            loadDashboard();
        } else {
            showToast(result.error || 'Gagal menghapus perangkat', 'error');
        }
    }

    // ==========================================
    // CHART MANAGEMENT
    // ==========================================
    function saveChartsToStorage() {
        const toSave = state.charts.map(chart => {
            const el = document.getElementById(chart.id);
            return {
                id: chart.id,
                title: chart.title,
                deviceId: chart.deviceId,
                chartType: chart.chartType,
                showData: chart.showData,
                width: el?.style.width || '100%',
                height: el?.style.height || '350px',
                x: el?.getAttribute('data-x') || '0',
                y: el?.getAttribute('data-y') || '0'
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
                    id: data.id,
                    title: data.title,
                    deviceId: data.deviceId,
                    deviceName: state.devices.find(d => d.device_id === data.deviceId)?.device_name || data.deviceId,
                    chartType: data.chartType,
                    showData: data.showData,
                    chartInstance: null,
                    isLoading: false
                };
                state.charts.push(config);
                renderChartCard(config, data.width, data.height, data.x, data.y);
                loadDynamicChartData(config);
                initializeDragResize(data.id);
                state.chartIdCounter = Math.max(
                    state.chartIdCounter,
                    parseInt(data.id.split('_')[1]) || 0
                );
            });
        } catch (e) {
            console.error('[Charts] Load failed:', e);
        }
    }

    function generateDataCheckboxes(selectedData = {}) {
        const container = $('chartDataCheckboxes');
        container.innerHTML = Object.entries(DATA_KEYS).map(([key, info]) => `
            <label class="checkbox-item">
                <input type="checkbox" class="chart-data-checkbox" data-key="${key}" ${selectedData[key] ? 'checked' : ''}>
                <span class="data-color" style="background:${info.color};"></span>
                <span>${info.label} (${info.unit})</span>
            </label>
        `).join('');
    }

    function openAddChartModal() {
        $('chartModalTitle').textContent = 'Tambah Diagram';
        $('editChartId').value = '';
        $('chartTitle').value = '';

        const select = $('chartDeviceSelect');
        select.innerHTML = '<option value="">Pilih Perangkat…</option>' +
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
        select.innerHTML = '<option value="">Pilih Perangkat…</option>' +
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
        $$('.chart-data-checkbox').forEach(cb => {
            showData[cb.dataset.key] = cb.checked;
        });

        if (!deviceId) {
            showToast('Pilih perangkat terlebih dahulu!', 'error');
            return;
        }
        if (!Object.values(showData).some(v => v)) {
            showToast('Pilih minimal satu jenis data!', 'error');
            return;
        }

        if (editId) {
            const chart = state.charts.find(c => c.id === editId);
            if (!chart) return;

            chart.title = title;
            chart.deviceId = deviceId;
            chart.deviceName = state.devices.find(d => d.device_id === deviceId)?.device_name || deviceId;
            chart.chartType = chartType;
            chart.showData = showData;

            // Destroy old chart
            if (chart.chartInstance) {
                chart.chartInstance.destroy();
                chart.chartInstance = null;
            }

            // Update header
            const card = document.getElementById(editId);
            if (card) {
                const dataLabels = Object.entries(showData)
                    .filter(([_, v]) => v)
                    .map(([k]) => DATA_KEYS[k]?.label || k)
                    .join(', ');

                card.querySelector('.chart-card-title').innerHTML = `
                    <i class="fa-solid fa-chart-line"></i>
                    ${escapeHtml(title)}
                    <span style="font-size:10px;color:var(--text-3);font-weight:500;">(${escapeHtml(chart.deviceName)} - ${escapeHtml(dataLabels)})</span>
                `;
            }

            loadDynamicChartData(chart);
            showToast('Diagram berhasil diperbarui', 'success');
        } else {
            const chartId = `chart_${++state.chartIdCounter}`;
            const config = {
                id: chartId,
                title,
                deviceId,
                deviceName: state.devices.find(d => d.device_id === deviceId)?.device_name || deviceId,
                chartType,
                showData,
                chartInstance: null,
                isLoading: false
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
        const emptyState = grid.querySelector('.empty-charts');
        if (emptyState) emptyState.remove();

        const card = document.createElement('div');
        card.className = 'chart-card';
        card.id = config.id;
        card.style.width = width;
        card.style.height = height;
        card.setAttribute('data-x', x);
        card.setAttribute('data-y', y);
        if (x !== '0' || y !== '0') {
            card.style.transform = `translate(${x}px, ${y}px)`;
        }

        const dataLabels = Object.entries(config.showData)
            .filter(([_, v]) => v)
            .map(([k]) => DATA_KEYS[k]?.label || k)
            .join(', ');

        card.innerHTML = `
            <div class="chart-card-header">
                <div class="chart-card-title">
                    <i class="fa-solid fa-chart-line"></i>
                    ${escapeHtml(config.title)}
                    <span style="font-size:10px;color:var(--text-3);font-weight:500;">(${escapeHtml(config.deviceName)} - ${escapeHtml(dataLabels)})</span>
                </div>
                <div class="chart-actions">
                    <button class="chart-edit-btn" data-action="edit" data-chart-id="${config.id}" title="Edit">
                        <i class="fa-solid fa-pen"></i>
                    </button>
                    <button class="chart-remove-btn" data-action="delete" data-chart-id="${config.id}" title="Hapus">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </div>
            </div>
            <div class="chart-card-body">
                <div class="chart-canvas-container">
                    <canvas id="${config.id}_canvas"></canvas>
                </div>
            </div>
            <div class="chart-resize-handle"></div>
        `;

        grid.appendChild(card);

        // Event listeners
        card.querySelector('.chart-edit-btn').addEventListener('click', e => {
            e.stopPropagation();
            e.preventDefault();
            openEditChartModal(config.id);
        });

        card.querySelector('.chart-remove-btn').addEventListener('click', e => {
            e.stopPropagation();
            e.preventDefault();
            removeChart(config.id);
        });
    }

    function initializeDragResize(chartId) {
        const el = document.getElementById(chartId);
        if (!el || typeof interact === 'undefined') return;

        interact(el)
            .draggable({
                allowFrom: '.chart-card-header',
                ignoreFrom: '.chart-actions',
                inertia: true,
                modifiers: [
                    interact.modifiers.restrictRect({
                        restriction: '#chartsGrid',
                        endOnly: true
                    })
                ],
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
                    end() {
                        el.classList.remove('dragging');
                        saveChartsToStorage();
                    }
                }
            })
            .resizable({
                edges: { right: true, bottom: true, left: false, top: false },
                inertia: true,
                modifiers: [
                    interact.modifiers.restrictSize({ min: { width: 280, height: 200 } })
                ],
                listeners: {
                    start() { el.classList.add('resizing'); },
                    move(event) {
                        Object.assign(el.style, {
                            width: `${event.rect.width}px`,
                            height: `${event.rect.height}px`
                        });
                        const chart = state.charts.find(c => c.id === chartId);
                        if (chart?.chartInstance) chart.chartInstance.resize();
                    },
                    end() {
                        el.classList.remove('resizing');
                        const chart = state.charts.find(c => c.id === chartId);
                        if (chart?.chartInstance) chart.chartInstance.resize();
                        saveChartsToStorage();
                    }
                }
            });
    }

    function initializeChartsGridResize() {
        const wrapper = document.querySelector('.charts-grid-wrapper');
        const grid = $('chartsGrid');
        if (!wrapper || !grid || typeof interact === 'undefined') return;

        interact(wrapper).resizable({
            edges: { right: false, bottom: true, left: false, top: false },
            inertia: false,
            modifiers: [
                interact.modifiers.restrictSize({ min: { width: 0, height: 400 } })
            ],
            listeners: {
                move(event) {
                    grid.style.height = `${event.rect.height}px`;
                    grid.style.width = '100%';
                    grid.style.minWidth = '100%';
                    grid.style.maxWidth = '100%';
                },
                end() {
                    state.charts.forEach(c => {
                        if (c.chartInstance) c.chartInstance.resize();
                    });
                }
            }
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
            $('chartsGrid').innerHTML = `
                <div class="empty-charts" style="text-align:center;padding:40px;color:var(--text-3);grid-column:1/-1;">
                    <i class="fa-solid fa-chart-column" style="font-size:40px;margin-bottom:12px;display:block;"></i>
                    <p style="font-size:14px;font-weight:600;">Belum ada diagram</p>
                    <p style="font-size:12px;margin-top:4px;">Klik "Tambah Diagram" untuk membuat visualisasi baru</p>
                </div>
            `;
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

            const now = new Date();
            const cutoffTime = new Date(now.getTime() - state.globalTimeMinutes * 60 * 1000);
            const filtered = result.data.history.filter(item => {
                try { return new Date(item.timestamp) >= cutoffTime; }
                catch (e) { return false; }
            });

            if (filtered.length === 0) {
                if (result.data.history.length > 0) {
                    await renderChartData(config, result.data.history);
                } else {
                    showChartEmpty(config.id, 'Menunggu data...');
                }
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

        // Destroy existing
        if (config.chartInstance) {
            try { config.chartInstance.destroy(); } catch (e) {}
            config.chartInstance = null;
        }

        const labels = historyData.map(item => {
            try {
                return new Date(item.timestamp).toLocaleTimeString('id-ID', {
                    hour: '2-digit', minute: '2-digit', second: '2-digit',
                    timeZone: 'Asia/Jakarta'
                });
            } catch (e) { return ''; }
        });

        const activeKeys = Object.entries(config.showData)
            .filter(([_, v]) => v)
            .map(([k]) => k);

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
                fill: isArea,
                tension: 0.35,
                pointRadius: 2,
                pointHoverRadius: 5,
                pointBackgroundColor: color,
                pointBorderColor: colors.pointBorderColor,
                pointBorderWidth: 1,
                borderWidth: 2,
                stack: isStacked ? 'stack1' : undefined
            });
        }

        if (datasets.length === 0) {
            showChartEmpty(config.id, 'Tidak ada data sensor yang cocok');
            return;
        }

        // Doughnut/Pie/Polar/Radar
        if (['doughnut', 'pie', 'polarArea', 'radar'].includes(config.chartType)) {
            const latest = historyData[historyData.length - 1];
            const gaugeLabels = [];
            const gaugeValues = [];

            activeKeys.forEach(key => {
                const info = DATA_KEYS[key];
                if (!info) return;
                const val = latest.data?.[key];
                if (val !== null && val !== undefined) {
                    gaugeLabels.push(info.label);
                    gaugeValues.push(val);
                }
            });

            if (gaugeValues.length === 0) {
                showChartEmpty(config.id, 'Tidak ada data terbaru');
                return;
            }

            config.chartInstance = new Chart(ctx, {
                type: config.chartType,
                data: {
                    labels: gaugeLabels,
                    datasets: [{
                        data: gaugeValues,
                        backgroundColor: gaugeValues.map((_, i) => CHART_COLORS[i % CHART_COLORS.length] + '80'),
                        borderColor: gaugeValues.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]),
                        borderWidth: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'right',
                            labels: {
                                color: colors.legendColor,
                                font: { size: 11, family: CHART_FONT },
                                usePointStyle: true,
                                padding: 12
                            }
                        }
                    }
                }
            });
            return;
        }

        // Line/Bar/etc
        let type = config.chartType;
        if (type === 'area' || type === 'stackedArea') type = 'line';
        if (type === 'horizontalBar' || type === 'stackedBar') type = 'bar';

        config.chartInstance = new Chart(ctx, {
            type,
            data: { labels, datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                indexAxis: config.chartType === 'horizontalBar' ? 'y' : 'x',
                animation: { duration: 750, easing: 'easeOutQuart' },
                plugins: {
                    legend: {
                        labels: {
                            color: colors.legendColor,
                            font: { size: 11, family: CHART_FONT },
                            usePointStyle: true,
                            pointStyle: 'circle',
                            padding: 12
                        }
                    },
                    tooltip: {
                        backgroundColor: colors.tooltipBg,
                        titleColor: colors.tooltipTitleColor,
                        bodyColor: colors.tooltipBodyColor,
                        borderColor: colors.tooltipBorder,
                        borderWidth: 1,
                        padding: 12,
                        cornerRadius: 10,
                        displayColors: true,
                        boxPadding: 5
                    }
                },
                scales: {
                    x: {
                        grid: { color: colors.gridColor },
                        ticks: {
                            color: colors.labelColor,
                            font: { family: CHART_FONT },
                            maxTicksLimit: 10,
                            maxRotation: 45,
                            autoSkip: true
                        },
                        stacked: config.chartType === 'stackedBar' || config.chartType === 'stackedArea'
                    },
                    y: {
                        grid: { color: colors.gridColor },
                        ticks: { color: colors.labelColor, font: { family: CHART_FONT } },
                        stacked: config.chartType === 'stackedBar' || config.chartType === 'stackedArea',
                        beginAtZero: true
                    }
                }
            }
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
            </div>
        `;
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
            if (graph && graph.style.display !== 'none') {
                refreshAllCharts();
            }
        }, 15000);
    }

    // ==========================================
    // MODAL UTILITIES
    // ==========================================
    function openModal(id) {
        const el = $(id);
        if (el) el.classList.add('active');
    }

    function closeModal(id) {
        const el = $(id);
        if (el) el.classList.remove('active');
    }

    // ==========================================
    // TIME RANGE
    // ==========================================
    function setGlobalTimeRange(minutes) {
        state.globalTimeMinutes = minutes;
        $$('.time-range-btn').forEach(btn => {
            btn.classList.toggle('active', parseInt(btn.dataset.minutes) === minutes);
        });
        localStorage.setItem(STORAGE_KEYS.GLOBAL_TIME, minutes);
        refreshAllCharts();
        showToast(`Rentang waktu: ${formatTimeRange(minutes)}`, 'success');
    }

    function loadGlobalTimeRange() {
        const saved = localStorage.getItem(STORAGE_KEYS.GLOBAL_TIME);
        if (saved) {
            state.globalTimeMinutes = parseInt(saved);
            $$('.time-range-btn').forEach(btn => {
                btn.classList.toggle('active', parseInt(btn.dataset.minutes) === state.globalTimeMinutes);
            });
        }
    }

    // ==========================================
    // INITIALIZATION
    // ==========================================
    function bindEvents() {
        // Sidebar toggle
        const logo = document.querySelector('.logo-ring');
        if (logo) logo.addEventListener('click', toggleSidebar);

        // Navigation
        const navItems = document.querySelectorAll('.sidebar-nav .nav-item');
        const sections = ['dashboard', 'map', 'graph', 'devices'];
        navItems.forEach((item, i) => {
            item.addEventListener('click', () => showSection(sections[i]));
        });

        // Theme toggle
        const themeBtn = $('themeToggleBtn');
        if (themeBtn) {
            themeBtn.addEventListener('click', () => {
                const newTheme = ThemeManager.toggle();
                updateThemeUI(newTheme);
                setTimeout(refreshAllCharts, 100);
            });
        }

        // Logout
        const logoutBtn = document.querySelector('.sidebar-footer .nav-item');
        if (logoutBtn) logoutBtn.addEventListener('click', () => window.location.href = '/logout');

        // Search
        const searchInput = $('searchInput');
        if (searchInput) searchInput.addEventListener('keyup', filterDevices);

        // Add device
        document.querySelectorAll('[data-action="add-device"]').forEach(btn => {
            btn.addEventListener('click', openAddDeviceModal);
        });

        // Add chart
        document.querySelectorAll('[data-action="add-chart"]').forEach(btn => {
            btn.addEventListener('click', openAddChartModal);
        });

        // Refresh charts
        document.querySelectorAll('[data-action="refresh-charts"]').forEach(btn => {
            btn.addEventListener('click', refreshAllCharts);
        });

        // Reset layout
        document.querySelectorAll('[data-action="reset-layout"]').forEach(btn => {
            btn.addEventListener('click', resetChartLayout);
        });

        // Save location
        const saveBtn = $('saveLocationBtn');
        if (saveBtn) saveBtn.addEventListener('click', saveLocation);

        // Map device select
        const mapSelect = $('mapDeviceSelect');
        if (mapSelect) {
            mapSelect.addEventListener('change', function() {
                state.selectedMapDeviceId = this.value;
                updateMapDeviceInfo();
                if (state.marker) {
                    state.marker.remove();
                    state.marker = null;
                }
                state.selectedLat = null;
                state.selectedLng = null;
                if (saveBtn) saveBtn.style.display = 'none';
            });
        }

        // Time range buttons
        document.querySelectorAll('.time-range-btn').forEach(btn => {
            btn.addEventListener('click', () => setGlobalTimeRange(parseInt(btn.dataset.minutes)));
        });

        // Filter buttons
        document.querySelectorAll('#deviceFilterBar .filter-btn').forEach(btn => {
            btn.addEventListener('click', () => setDeviceFilter(btn.dataset.filter));
        });
        document.querySelectorAll('#deviceFilterBarFull .filter-btn').forEach(btn => {
            btn.addEventListener('click', () => setDeviceFilterFull(btn.dataset.filter));
        });

        // Modal close
        document.querySelectorAll('.modal-close').forEach(btn => {
            btn.addEventListener('click', () => {
                const modal = btn.closest('.modal');
                if (modal) modal.classList.remove('active');
            });
        });

        // Modal backdrop click
        document.querySelectorAll('.modal').forEach(modal => {
            modal.addEventListener('click', e => {
                if (e.target === modal) modal.classList.remove('active');
            });
        });

        // Add device submit
        document.querySelectorAll('[data-action="submit-add-device"]').forEach(btn => {
            btn.addEventListener('click', addDevice);
        });

        // Copy API key
        document.querySelectorAll('[data-action="copy-api-key"]').forEach(btn => {
            btn.addEventListener('click', copyApiKey);
        });

        // Confirm delete
        document.querySelectorAll('[data-action="confirm-delete"]').forEach(btn => {
            btn.addEventListener('click', confirmDelete);
        });

        // Save chart
        document.querySelectorAll('[data-action="save-chart"]').forEach(btn => {
            btn.addEventListener('click', saveChart);
        });

        // Theme change listener — refresh charts
        ThemeManager.onChange(() => setTimeout(refreshAllCharts, 100));
    }

    function updateThemeUI(theme) {
        const icon = $('themeIcon');
        const label = $('themeLabel');
        if (icon) icon.className = theme === 'light' ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
        if (label) label.textContent = theme === 'light' ? 'Tema Terang' : 'Tema Gelap';
    }

    async function init() {
        // Bind events first
        bindEvents();

        // Init UI
        updateThemeUI(ThemeManager.get());
        loadGlobalTimeRange();
        updateDateTime();
        setInterval(updateDateTime, 1000);

        // Init maps
        initMapPreview();

        // Load data
        await loadDashboard();
        state.dashboardInterval = setInterval(loadDashboard, 30000);
        startAutoRefresh();
        initializeChartsGridResize();

        console.log('[Dashboard] Ready');
    }

    // Start when DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();