/* ==========================================
   NEXUS IoT - Alert Center (Section Module)
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
    };

    const STORAGE_KEYS = {
        BACK_URL: 'nexus_back_url',
    };

    function $(id) { return document.getElementById(id); }

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

    function formatTime(iso) {
        const d = parseDate(iso);
        if (!d) return '-';
        try {
            const diff = (Date.now() - d.getTime()) / 1000;
            if (diff < 60) return 'baru saja';
            if (diff < 3600) return `${Math.floor(diff / 60)} menit lalu`;
            if (diff < 86400) return `${Math.floor(diff / 3600)} jam lalu`;
            if (diff < 604800) return `${Math.floor(diff / 86400)} hari lalu`;
            return d.toLocaleString('id-ID', {
                day: '2-digit', month: 'short', year: 'numeric',
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
            danger: 'BAHAYA', warning: 'PERINGATAN',
            info: 'INFO', healthy: 'NORMAL',
        }[sev] || String(sev).toUpperCase();
    }

    function alertTypeLabel(type) {
        const map = {
            temperature: 'Suhu', humidity: 'Kelembaban', gas_level: 'Level Gas',
            offline: 'Perangkat Offline', smoke: 'Asap', motion: 'Gerakan',
            co2: 'CO2', moisture: 'Kelembaban Tanah', lux: 'Cahaya',
        };
        return map[type] || String(type).replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }

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
            state.alerts = Array.isArray(data.alerts) ? data.alerts : [];
            applyFilter();
            loadStats();
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
            html += renderAlertItem(a);
        });
        if (groupOpened) html += '</div>';

        container.innerHTML = html;
        bindItemEvents();
    }

    function renderAlertItem(a) {
        const isActive = a.is_still_active === 1;
        const severity = a.severity || 'info';
        const icon = severityIcon(severity);
        const sevLabel = severityLabel(severity);
        const typeLabel = alertTypeLabel(a.alert_type);
        const isHealthy = severity === 'healthy';
        const itemClass = isHealthy ? 'resolved' : (isActive ? severity : 'resolved');
        const isChecked = state.selectedIds.has(a.id);

        return `
            <div class="alert-item ${itemClass}" data-alert-id="${a.id}">
                ${isActive && !isHealthy ? `
                    <label class="alert-item-checkbox" onclick="event.stopPropagation();">
                        <input type="checkbox" class="alert-checkbox" data-alert-id="${a.id}" ${isChecked ? 'checked' : ''}>
                    </label>
                ` : '<div style="width:24px;flex-shrink:0;"></div>'}
                <div class="alert-item-icon"><i class="fa-solid ${icon}"></i></div>
                <div class="alert-item-content">
                    <div class="alert-item-header">
                        <span class="alert-item-title">${escapeHtml(typeLabel)}</span>
                        <span class="severity-badge ${severity}">${sevLabel}</span>
                        ${isActive && !isHealthy
                            ? '<span class="status-pill active"><i class="fa-solid fa-circle" style="font-size:6px;"></i> AKTIF</span>'
                            : '<span class="status-pill resolved"><i class="fa-solid fa-check"></i> SELESAI</span>'}
                    </div>
                    <div class="alert-item-message">${escapeHtml(a.message || '-')}</div>
                    <div class="alert-item-meta">
                        <span><i class="fa-solid fa-microchip"></i> <span class="device-ref">${escapeHtml(a.device_name || a.device_id)}</span></span>
                        ${a.location ? `<span><i class="fa-solid fa-location-dot"></i> ${escapeHtml(a.location)}</span>` : ''}
                        <span title="${formatFullTime(a.created_at)}"><i class="fa-regular fa-clock"></i> ${formatTime(a.created_at)}</span>
                    </div>
                </div>
                <div class="alert-item-actions">
                    <button class="alert-action-btn view" data-action="view-device" data-device-id="${escapeHtml(a.device_id)}">
                        <i class="fa-solid fa-eye"></i> Device
                    </button>
                    ${isActive && !isHealthy ? `
                        <button class="alert-action-btn ack" data-action="acknowledge" data-alert-id="${a.id}">
                            <i class="fa-solid fa-check"></i> Selesai
                        </button>` : ''}
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
        document.querySelectorAll('.alert-item').forEach(item => {
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
        const activeAlerts = state.filtered.filter(a => a.is_still_active === 1 && a.severity !== 'healthy');
        if (activeAlerts.length === 0) { bar.style.display = 'none'; return; }
        bar.style.display = 'flex';
        const countEl = $('selectedCount');
        if (countEl) countEl.textContent = `${state.selectedIds.size} dipilih`;
        const selectAll = $('selectAllCheckbox');
        if (selectAll) {
            selectAll.checked = activeAlerts.length > 0 && activeAlerts.every(a => state.selectedIds.has(a.id));
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

        const selectAll = $('selectAllCheckbox');
        if (selectAll) {
            selectAll.addEventListener('change', e => {
                const activeAlerts = state.filtered.filter(a => a.is_still_active === 1 && a.severity !== 'healthy');
                if (e.target.checked) activeAlerts.forEach(a => state.selectedIds.add(a.id));
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

    let initialized = false;

    function init() {
        if (initialized) return;
        initialized = true;
        bindEvents();
        loadAlerts();
        setInterval(() => {
            const alertsSection = $('alertsSection');
            if (alertsSection && alertsSection.style.display !== 'none') {
                loadAlerts();
            }
        }, 20000);
    }

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

    console.log('[Alerts] Initialized');
})();