/* ==========================================
   NEXUS IoT - Alert Center (v4.2)
   + Fix: ack pakai alert_id (bukan history.id)
   + Sound notification untuk danger/warning baru
   + Mark All Read
   ========================================== */

(function() {
    'use strict';

    const state = {
        alerts: [],
        filtered: [],
        status: 'all',
        severity: '',
        search: '',
        selectedIds: new Set(),
        newlyAdded: new Set(),
        refreshInterval: null,
        isInitialized: false,
    };

    const STORAGE_KEYS = {
        BACK_URL: 'nexus_back_url',
        SOUND: 'nexus-alerts-sound',
    };

    const _seenAlertIds = new Set();
    let _audioCtx = null;

    function $(id) { return document.getElementById(id); }

    function escapeHtml(str) {
        return String(str ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
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
        if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
            const d = new Date(s + 'T00:00:00+07:00');
            return isNaN(d.getTime()) ? null : d;
        }
        const d = new Date(s);
        return isNaN(d.getTime()) ? null : d;
    }

    function formatTime(iso) {
        const d = parseDate(iso);
        if (!d) return '-';
        try {
            const diff = (Date.now() - d.getTime()) / 1000;
            if (diff < 0) return 'baru saja';
            if (diff < 60) return 'baru saja';
            if (diff < 3600) return `${Math.floor(diff / 60)}m lalu`;
            if (diff < 86400) return `${Math.floor(diff / 3600)}j lalu`;
            if (diff < 604800) return `${Math.floor(diff / 86400)}h lalu`;
            return d.toLocaleString('id-ID', {
                day: '2-digit', month: 'short',
                hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Jakarta',
            });
        } catch (e) { return '-'; }
    }

    function formatFullTime(iso) {
        const d = parseDate(iso);
        if (!d) return '-';
        try {
            return d.toLocaleString('id-ID', {
                day: '2-digit', month: 'short', year: 'numeric',
                hour: '2-digit', minute: '2-digit', second: '2-digit',
                timeZone: 'Asia/Jakarta',
            }) + ' WIB';
        } catch (e) { return '-'; }
    }

    function severityIcon(sev) {
        return {
            danger: 'fa-fire', warning: 'fa-triangle-exclamation',
            info: 'fa-circle-info', healthy: 'fa-circle-check',
        }[sev] || 'fa-bell';
    }

    function severityLabel(sev) {
        return {
            danger: 'Bahaya', warning: 'Peringatan',
            info: 'Info', healthy: 'Normal',
        }[sev] || String(sev).toUpperCase();
    }

    function alertTypeLabel(type) {
        const map = {
            temperature: 'Suhu', humidity: 'Kelembaban', gas_level: 'Gas',
            offline: 'Offline', smoke: 'Asap', motion: 'Gerakan',
            co2: 'CO2', moisture: 'K. Tanah', lux: 'Cahaya',
            voc: 'VOC', air_quality: 'Kualitas Udara',
        };
        return map[type] || String(type).replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }

    const SENSOR_UNITS = {
        temperature: '°C', humidity: '%', gas_level: 'ppm',
        smoke: 'ppm', moisture: '%', lux: 'lux',
        co2: 'ppm', voc: 'ppb', air_quality: 'AQI',
        motion: '', rfid: '',
    };

    function formatValue(alertType, value) {
        if (value === null || value === undefined) return null;
        const unit = SENSOR_UNITS[alertType] ?? '';
        const num = parseFloat(value);
        if (isNaN(num)) return String(value);
        const trimmed = parseFloat(num.toFixed(2));
        return `${trimmed}${unit}`;
    }

    // ✅ helper: pilih ID yang tepat untuk ack (alert_id > id)
    function getAckId(a) {
        if (a && a.alert_id !== null && a.alert_id !== undefined) return a.alert_id;
        return a ? a.id : null;
    }

    // ==========================================
    // SOUND
    // ==========================================
    function _getAudioCtx() {
        if (!_audioCtx) {
            try {
                _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            } catch (e) {
                console.warn('[Alerts] AudioContext tidak didukung');
            }
        }
        if (_audioCtx && _audioCtx.state === 'suspended') {
            try { _audioCtx.resume(); } catch (e) {}
        }
        return _audioCtx;
    }

    function _playBeep(severity) {
        if (localStorage.getItem(STORAGE_KEYS.SOUND) === 'off') return;
        if (severity !== 'danger' && severity !== 'warning') return;

        const ctx = _getAudioCtx();
        if (!ctx) return;

        const now = ctx.currentTime;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);

        osc.type = 'sine';
        osc.frequency.setValueAtTime(severity === 'danger' ? 880 : 660, now);

        gain.gain.setValueAtTime(0.001, now);
        gain.gain.exponentialRampToValueAtTime(0.15, now + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.15);

        osc.start(now);
        osc.stop(now + 0.16);

        if (severity === 'danger') {
            const osc2 = ctx.createOscillator();
            const gain2 = ctx.createGain();
            osc2.connect(gain2);
            gain2.connect(ctx.destination);
            osc2.type = 'sine';
            osc2.frequency.setValueAtTime(880, now + 0.18);

            gain2.gain.setValueAtTime(0.001, now + 0.18);
            gain2.gain.exponentialRampToValueAtTime(0.15, now + 0.2);
            gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.33);

            osc2.start(now + 0.18);
            osc2.stop(now + 0.34);
        }
    }

    function _updateSoundToggleUI() {
        const btn = document.getElementById('alertSoundToggle');
        const icon = document.getElementById('alertSoundIcon');
        const label = document.getElementById('alertSoundLabel');
        if (!btn) return;

        const enabled = localStorage.getItem(STORAGE_KEYS.SOUND) !== 'off';
        btn.classList.toggle('muted', !enabled);
        if (icon) icon.className = enabled ? 'fa-solid fa-volume-high' : 'fa-solid fa-volume-xmark';
        if (label) label.textContent = enabled ? 'Suara: ON' : 'Suara: OFF';
    }

    // ==========================================
    // LOAD
    // ==========================================
    async function loadStats() {
        try {
            const res = await fetch('/api/v1/alerts/stats');
            const data = await res.json();
            if (!data.success) return;
            const setText = (id, val) => { const el = $(id); if (el) el.textContent = val ?? 0; };
            setText('statTotalActive', data.summary.total);
            setText('statDanger', data.summary.danger);
            setText('statWarning', data.summary.warning);
            setText('statInfo', data.summary.info);
            setText('alertBadge', data.summary.total);
        } catch (e) { console.error(e); }
    }

    async function loadAlerts() {
        const params = new URLSearchParams();
        if (state.status !== 'all') params.set('status', state.status);
        if (state.severity) params.set('severity', state.severity);
        params.set('limit', '500');

        try {
            const res = await fetch(`/api/v1/alerts/all?${params}`);
            const data = await res.json();
            if (!data.success) { showError('Gagal memuat alert'); return; }

            const freshAlerts = Array.isArray(data.alerts) ? data.alerts : [];
            const freshIds = new Set(freshAlerts.map(a => a.id));

            const newOnes = [];
            const wasFirstLoad = _seenAlertIds.size === 0;

            freshAlerts.forEach(a => {
                if (!_seenAlertIds.has(a.id)) {
                    if (!wasFirstLoad) newOnes.push(a);
                    _seenAlertIds.add(a.id);
                }
            });

            const activeNew = newOnes.filter(a => a.is_still_active === 1);
            if (activeNew.length > 0) {
                const worst = activeNew.some(a => a.severity === 'danger') ? 'danger' : 'warning';
                _playBeep(worst);
            }

            for (const id of Array.from(_seenAlertIds)) {
                if (!freshIds.has(id)) _seenAlertIds.delete(id);
            }

            state.alerts = freshAlerts;
            state.newlyAdded = new Set(newOnes.map(a => a.id));

            // Bersihkan selectedIds yang sudah tidak valid
            const validAckIds = new Set(
                freshAlerts
                    .filter(a => a.is_still_active === 1 && a.severity !== 'healthy')
                    .map(a => getAckId(a))
                    .filter(x => x !== null)
            );
            state.selectedIds.forEach(id => {
                if (!validAckIds.has(id)) state.selectedIds.delete(id);
            });

            applyFilter();
            loadStats();

            if (newOnes.length > 0) {
                setTimeout(() => {
                    state.newlyAdded = new Set();
                    document.querySelectorAll('.alert-row.is-new').forEach(el =>
                        el.classList.remove('is-new'));
                }, 5000);
            }
        } catch (e) { showError('Koneksi gagal'); }
    }

    function applyFilter() {
        let list = state.alerts;
        if (state.search) {
            const term = state.search.toLowerCase();
            list = list.filter(a =>
                (a.device_name || '').toLowerCase().includes(term) ||
                (a.device_id || '').toLowerCase().includes(term) ||
                (a.message || '').toLowerCase().includes(term) ||
                (a.alert_type || '').toLowerCase().includes(term) ||
                (a.label || '').toLowerCase().includes(term)
            );
        }
        state.filtered = list;
        renderAlerts();
        updateBulkBar();
    }

    function renderAlerts() {
        const container = $('alertsList');
        if (!container) return;

        if (state.filtered.length === 0) {
            const filterInfo = state.search || state.status !== 'all' || state.severity;
            container.innerHTML = `
                <div class="empty-state" style="padding:60px 20px;">
                    <i class="fa-solid fa-bell-slash" style="font-size:36px;color:var(--text-3);"></i>
                    <h3 style="margin-top:12px;">Tidak ada alert</h3>
                    <p style="font-size:12.5px;color:var(--text-3);">
                        ${filterInfo ? 'Coba ubah filter atau kata kunci pencarian' : 'Semua perangkat dalam kondisi normal'}
                    </p>
                </div>`;
            return;
        }

        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const yesterday = new Date(today.getTime() - 86400000);
        const weekAgo = new Date(today.getTime() - 7 * 86400000);
        let html = '';
        let currentGroup = '', groupOpened = false;

        state.filtered.forEach(a => {
            const created = parseDate(a.created_at);
            let group;
            if (!created) group = 'Tidak Diketahui';
            else if (created >= today) group = 'Hari Ini';
            else if (created >= yesterday) group = 'Kemarin';
            else if (created >= weekAgo) group = '7 Hari Terakhir';
            else group = 'Lebih Lama';

            if (group !== currentGroup) {
                if (groupOpened) html += '</div>';
                html += `<div class="alert-group"><div class="alert-group-label">${group}</div>`;
                currentGroup = group;
                groupOpened = true;
            }
            html += renderAlertRow(a);
        });
        if (groupOpened) html += '</div>';

        container.innerHTML = html;
        bindItemEvents();
    }

    function renderAlertRow(a) {
        const isActive = a.is_still_active === 1;
        const severity = a.severity || 'info';
        const icon = severityIcon(severity);
        const sevLabel = severityLabel(severity);
        const typeLabel = alertTypeLabel(a.alert_type);
        const isHealthy = severity === 'healthy';
        const itemClass = isHealthy ? 'resolved' : (isActive ? severity : 'resolved');
        const ackId = getAckId(a);
        const isChecked = ackId !== null && state.selectedIds.has(ackId);
        const isNew = state.newlyAdded && state.newlyAdded.has(a.id);

        const valueDisplay = formatValue(a.alert_type, a.value);
        const timeStr = formatTime(a.created_at);
        const statusText = isActive && !isHealthy ? 'Aktif' : 'Selesai';

        const checkboxHtml = (isActive && !isHealthy && ackId !== null) ? `
            <label class="alert-row-check" onclick="event.stopPropagation();">
                <input type="checkbox" class="alert-checkbox" data-alert-id="${ackId}" ${isChecked ? 'checked' : ''}>
            </label>
        ` : '<div style="width:20px;flex-shrink:0;"></div>';

        const ackBtnHtml = (isActive && !isHealthy && ackId !== null) ? `
            <button class="alert-act-btn ack" data-action="acknowledge" data-alert-id="${ackId}" title="Tandai Selesai">
                <i class="fa-solid fa-check"></i>
            </button>
        ` : '';

        return `
            <div class="alert-row ${itemClass}${isNew ? ' is-new' : ''}" data-alert-id="${a.id}">
                ${checkboxHtml}

                <span class="alert-icon"><i class="fa-solid ${icon}"></i></span>

                <div class="alert-body">
                    <div class="alert-line-1">
                        <strong>${escapeHtml(typeLabel)}</strong>
                        ${valueDisplay ? `<span class="alert-val">${escapeHtml(valueDisplay)}</span>` : ''}
                        <span class="alert-msg">${escapeHtml(a.message || '-')}</span>
                    </div>
                    <div class="alert-line-2">
                        <span class="alert-sev ${severity}">${sevLabel}</span>
                        <span class="alert-st ${isActive && !isHealthy ? 'active' : 'done'}">${statusText}</span>
                        <span class="alert-dev"><i class="fa-solid fa-microchip"></i> ${escapeHtml(a.device_name || a.device_id)}</span>
                        <span class="alert-time" title="${formatFullTime(a.created_at)}">${timeStr}</span>
                    </div>
                </div>

                <div class="alert-acts">
                    <button class="alert-act-btn view" data-action="view-device" data-device-id="${escapeHtml(a.device_id)}" title="Lihat Device">
                        <i class="fa-solid fa-eye"></i>
                    </button>
                    ${ackBtnHtml}
                </div>
            </div>`;
    }

    function bindItemEvents() {
        document.querySelectorAll('[data-action="view-device"]').forEach(btn => {
            btn.addEventListener('click', e => {
                e.stopPropagation();
                try { sessionStorage.setItem(STORAGE_KEYS.BACK_URL, '/#alerts'); } catch (err) {}
                window.location.href = `/device/${encodeURIComponent(btn.dataset.deviceId)}`;
            });
        });
        document.querySelectorAll('[data-action="acknowledge"]').forEach(btn => {
            btn.addEventListener('click', async e => {
                e.stopPropagation();
                const alertId = parseInt(btn.dataset.alertId, 10);
                if (!Number.isFinite(alertId)) return;
                const ok = await acknowledgeAlert(alertId);
                if (ok) {
                    window.showToast('Alert ditandai selesai', 'success');
                    state.selectedIds.delete(alertId);
                    loadAlerts();
                } else window.showToast('Gagal menandai alert', 'error');
            });
        });
        document.querySelectorAll('.alert-checkbox').forEach(cb => {
            cb.addEventListener('change', e => {
                const id = parseInt(e.target.dataset.alertId, 10);
                if (!Number.isFinite(id)) return;
                if (e.target.checked) state.selectedIds.add(id);
                else state.selectedIds.delete(id);
                updateBulkBar();
            });
        });
        document.querySelectorAll('.alert-row').forEach(item => {
            item.addEventListener('click', (e) => {
                if (e.target.closest('button') || e.target.closest('label')) return;
                const viewBtn = item.querySelector('[data-action="view-device"]');
                if (viewBtn) {
                    try { sessionStorage.setItem(STORAGE_KEYS.BACK_URL, '/#alerts'); } catch (err) {}
                    window.location.href = `/device/${encodeURIComponent(viewBtn.dataset.deviceId)}`;
                }
            });
        });
    }

    function updateBulkBar() {
        const bar = $('bulkActionBar');
        if (!bar) return;
        const activeAlerts = state.filtered.filter(a => a.is_still_active === 1 && a.severity !== 'healthy' && getAckId(a) !== null);
        if (activeAlerts.length === 0) { bar.style.display = 'none'; return; }
        bar.style.display = 'flex';
        const countEl = $('selectedCount');
        if (countEl) countEl.textContent = `${state.selectedIds.size} dipilih`;
        const selectAll = $('selectAllCheckbox');
        if (selectAll) {
            const allIds = activeAlerts.map(a => getAckId(a));
            selectAll.checked = allIds.length > 0 && allIds.every(id => state.selectedIds.has(id));
        }
    }

    async function acknowledgeAlert(alertId) {
        try {
            const res = await fetch(`/api/v1/alerts/${alertId}/acknowledge`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            });
            const data = await res.json();
            return data.success === true;
        } catch (e) { return false; }
    }

    async function bulkAcknowledge() {
        if (state.selectedIds.size === 0) {
            window.showToast('Pilih minimal satu alert', 'warning');
            return;
        }
        const ids = Array.from(state.selectedIds);
        try {
            const res = await fetch('/api/v1/alerts/bulk-acknowledge', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                body: JSON.stringify({ ids }),
            });
            const data = await res.json();
            if (data.success) {
                window.showToast(`${data.acknowledged} alert ditandai selesai`, 'success');
                state.selectedIds.clear();
                loadAlerts();
            } else window.showToast(data.error || 'Gagal', 'error');
        } catch (e) { window.showToast('Koneksi gagal', 'error'); }
    }

    async function markAllVisible() {
        const visibleActive = state.filtered.filter(a =>
            a.is_still_active === 1 && a.severity !== 'healthy' && getAckId(a) !== null);

        if (visibleActive.length === 0) {
            window.showToast('Tidak ada alert aktif di filter ini', 'info');
            return;
        }

        if (!confirm(`Tandai ${visibleActive.length} alert sebagai selesai?`)) return;

        const ids = visibleActive.map(a => getAckId(a));
        try {
            const res = await fetch('/api/v1/alerts/bulk-acknowledge', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                body: JSON.stringify({ ids }),
            });
            const data = await res.json();
            if (data.success) {
                window.showToast(`${data.acknowledged} alert ditandai selesai`, 'success');
                loadAlerts();
            } else {
                window.showToast(data.error || 'Gagal', 'error');
            }
        } catch (e) {
            window.showToast('Koneksi gagal', 'error');
        }
    }

    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : '';
    }

    function showError(msg) {
        const container = $('alertsList');
        if (!container) return;
        container.innerHTML = `
            <div class="empty-state" style="padding:60px 20px;">
                <i class="fa-solid fa-triangle-exclamation" style="font-size:36px;color:var(--red);"></i>
                <h3 style="margin-top:12px;">${escapeHtml(msg)}</h3>
            </div>`;
    }

    function bindEvents() {
        document.querySelectorAll('[data-status]').forEach(btn => {
            btn.addEventListener('click', () => {
                state.status = btn.dataset.status;
                document.querySelectorAll('[data-status]').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                loadAlerts();
            });
        });

        document.querySelectorAll('[data-severity]').forEach(btn => {
            btn.addEventListener('click', () => {
                const sev = btn.dataset.severity;
                if (state.severity === sev) state.severity = '';
                else state.severity = sev;
                document.querySelectorAll('[data-severity]').forEach(b => b.classList.remove('active'));
                if (state.severity !== '') btn.classList.add('active');
                else {
                    const allBtn = document.querySelector('[data-severity=""]');
                    if (allBtn) allBtn.classList.add('active');
                }
                loadAlerts();
            });
        });

        const searchInput = $('alertSearchInput');
        if (searchInput) {
            let t;
            searchInput.addEventListener('input', e => {
                clearTimeout(t);
                t = setTimeout(() => { state.search = e.target.value.trim(); applyFilter(); }, 200);
            });
        }

        const refreshBtn = $('refreshAlertsBtn');
        if (refreshBtn) refreshBtn.addEventListener('click', loadAlerts);

        const soundBtn = $('alertSoundToggle');
        if (soundBtn) {
            soundBtn.addEventListener('click', () => {
                const enabled = localStorage.getItem(STORAGE_KEYS.SOUND) !== 'off';
                localStorage.setItem(STORAGE_KEYS.SOUND, enabled ? 'off' : 'on');
                _updateSoundToggleUI();
                if (!enabled) _playBeep('warning');
            });
        }

        const markAllBtn = $('markAllReadBtn');
        if (markAllBtn) markAllBtn.addEventListener('click', markAllVisible);

        const selectAll = $('selectAllCheckbox');
        if (selectAll) {
            selectAll.addEventListener('change', e => {
                const activeAlerts = state.filtered.filter(a => a.is_still_active === 1 && a.severity !== 'healthy' && getAckId(a) !== null);
                if (e.target.checked) activeAlerts.forEach(a => state.selectedIds.add(getAckId(a)));
                else state.selectedIds.clear();
                renderAlerts();
                updateBulkBar();
            });
        }

        const bulkAckBtn = $('bulkAckBtn');
        if (bulkAckBtn) bulkAckBtn.addEventListener('click', bulkAcknowledge);

        document.addEventListener('keydown', e => {
            if (e.key === 'r' && (e.ctrlKey || e.metaKey)) {
                const alertsSection = $('alertsSection');
                if (alertsSection && alertsSection.style.display !== 'none') {
                    e.preventDefault();
                    loadAlerts();
                }
            }
        });
    }

    function init() {
        if (state.isInitialized) return;
        state.isInitialized = true;
        _updateSoundToggleUI();
        bindEvents();
        loadAlerts();
        state.refreshInterval = setInterval(() => {
            const alertsSection = $('alertsSection');
            if (alertsSection && alertsSection.style.display !== 'none') {
                loadAlerts();
            }
        }, 20000);
    }

    window.addEventListener('beforeunload', () => {
        if (state.refreshInterval) {
            clearInterval(state.refreshInterval);
            state.refreshInterval = null;
        }
    });

    window.NexusAlerts = {
        init,
        load: loadAlerts,
        loadStats,
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    console.log('[Alerts] Initialized v4.2');
})();