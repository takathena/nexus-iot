/* ==========================================
   NEXUS IoT - Alert Center Logic
   ========================================== */

(function() {
    'use strict';

    const state = {
        alerts: [],
        filtered: [],
        status: 'all',
        severity: '',
        search: '',
        refreshInterval: null,
        selectedIds: new Set(),
    };

    function $(id) { return document.getElementById(id); }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = String(str ?? '');
        return div.innerHTML;
    }

    function formatTime(iso) {
        if (!iso) return '-';
        try {
            const d = new Date(iso);
            const diff = (new Date() - d) / 1000;
            if (diff < 60) return 'baru saja';
            if (diff < 3600) return `${Math.floor(diff / 60)} menit lalu`;
            if (diff < 86400) return `${Math.floor(diff / 3600)} jam lalu`;
            if (diff < 604800) return `${Math.floor(diff / 86400)} hari lalu`;
            return d.toLocaleString('id-ID', {
                day: '2-digit', month: 'short', year: 'numeric',
                hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Jakarta'
            });
        } catch (e) { return '-'; }
    }

    function formatFullTime(iso) {
        if (!iso) return '-';
        try {
            return new Date(iso).toLocaleString('id-ID', {
                day: '2-digit', month: 'short', year: 'numeric',
                hour: '2-digit', minute: '2-digit', second: '2-digit',
                timeZone: 'Asia/Jakarta'
            }) + ' WIB';
        } catch (e) { return '-'; }
    }

    function severityIcon(sev) {
        return { danger: 'fa-fire', warning: 'fa-triangle-exclamation', info: 'fa-circle-info', healthy: 'fa-circle-check' }[sev] || 'fa-bell';
    }

    function severityLabel(sev) {
        return { danger: 'BAHAYA', warning: 'PERINGATAN', info: 'INFO', healthy: 'NORMAL' }[sev] || sev.toUpperCase();
    }

    function alertTypeLabel(type) {
        const map = {
            temperature: 'Suhu', humidity: 'Kelembaban', gas_level: 'Level Gas',
            offline: 'Perangkat Offline', smoke: 'Asap', motion: 'Gerakan',
            co2: 'CO2', moisture: 'Kelembaban Tanah', lux: 'Cahaya'
        };
        return map[type] || type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }

    function updateDateTime() {
        const now = new Date();
        const dateEl = $('currentDate'), timeEl = $('currentTime');
        if (dateEl) dateEl.textContent = now.toLocaleDateString('id-ID', {
            weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Asia/Jakarta'
        });
        if (timeEl) timeEl.textContent = now.toLocaleTimeString('id-ID', {
            hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'Asia/Jakarta'
        }) + ' WIB';
    }

    async function loadStats() {
        try {
            const res = await fetch('/api/v1/alerts/stats');
            const data = await res.json();
            if (!data.success) return;
            $('statTotalActive').textContent = data.summary.total;
            $('statDanger').textContent = data.summary.danger;
            $('statWarning').textContent = data.summary.warning;
            $('statInfo').textContent = data.summary.info;
            const badge = $('alertBadge');
            if (badge) badge.textContent = data.summary.total;
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
            state.alerts = data.alerts;
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
            container.innerHTML = `
                <div class="empty-state" style="padding:60px 20px;">
                    <i class="fa-solid fa-bell-slash" style="font-size:36px;color:var(--text-3);"></i>
                    <h3 style="margin-top:12px;">Tidak ada alert</h3>
                    <p style="font-size:12.5px;color:var(--text-3);">
                        ${state.search || state.status !== 'all' || state.severity
                            ? 'Coba ubah filter atau kata kunci pencarian'
                            : 'Semua perangkat dalam kondisi normal'}
                    </p>
                </div>
            `;
            return;
        }

        let html = '';
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const yesterday = new Date(today.getTime() - 86400000);
        const weekAgo = new Date(today.getTime() - 7 * 86400000);
        let currentGroup = '', groupOpened = false;

        state.filtered.forEach(a => {
            const created = new Date(a.created_at);
            let group;
            if (created >= today) group = 'Hari Ini';
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
            </div>
        `;
    }

    function bindItemEvents() {
        document.querySelectorAll('[data-action="view-device"]').forEach(btn => {
            btn.addEventListener('click', e => {
                e.stopPropagation();
                window.location.href = `/device/${encodeURIComponent(btn.dataset.deviceId)}`;
            });
        });
        document.querySelectorAll('[data-action="acknowledge"]').forEach(btn => {
            btn.addEventListener('click', async e => {
                e.stopPropagation();
                const alertId = parseInt(btn.dataset.alertId);
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
                const id = parseInt(e.target.dataset.alertId);
                if (e.target.checked) state.selectedIds.add(id);
                else state.selectedIds.delete(id);
                updateBulkBar();
            });
        });
        document.querySelectorAll('.alert-item').forEach(item => {
            item.addEventListener('click', (e) => {
                if (e.target.closest('button') || e.target.closest('label')) return;
                const viewBtn = item.querySelector('[data-action="view-device"]');
                if (viewBtn) window.location.href = `/device/${encodeURIComponent(viewBtn.dataset.deviceId)}`;
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
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() }
            });
            const data = await res.json();
            return data.success;
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
                body: JSON.stringify({ ids })
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
        if (container) {
            container.innerHTML = `
                <div class="empty-state" style="padding:60px 20px;">
                    <i class="fa-solid fa-triangle-exclamation" style="font-size:36px;color:var(--red);"></i>
                    <h3 style="margin-top:12px;">${escapeHtml(msg)}</h3>
                </div>`;
        }
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
                else document.querySelector('[data-severity=""]').classList.add('active');
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

        const logoutBtn = $('logoutBtn');
        if (logoutBtn) logoutBtn.addEventListener('click', () => window.location.href = '/logout');
        const themeBtn = $('themeToggleBtn');
        if (themeBtn) {
            themeBtn.addEventListener('click', () => {
                const newTheme = window.ThemeManager ? window.ThemeManager.toggle() : 'dark';
                updateThemeUI(newTheme);
            });
        }
    }

    function updateThemeUI(theme) {
        const icon = $('themeIcon'), label = $('themeLabel');
        if (icon) icon.className = theme === 'light' ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
        if (label) label.textContent = theme === 'light' ? 'Tema Terang' : 'Tema Gelap';
    }

    function init() {
        bindEvents();
        updateDateTime();
        setInterval(updateDateTime, 1000);
        loadAlerts();
        state.refreshInterval = setInterval(loadAlerts, 20000);
        if (window.ThemeManager) updateThemeUI(window.ThemeManager.get());
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else init();
})();