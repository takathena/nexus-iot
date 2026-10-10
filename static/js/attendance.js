/* ==========================================
   NEXUS IoT v5.0 - Attendance filter & export
   Sparkline real dari /api/v1/metrics/attendance-history
   ========================================== */

(function() {
    'use strict';

    const $ = (id) => document.getElementById(id);

    function getDateRange() {
        const start = $('attendanceStartDate')?.value || '';
        const end = $('attendanceEndDate')?.value || '';
        return { start, end };
    }

    function updateFilterInfo() {
        const infoEl = $('attendanceFilterInfo');
        if (!infoEl) return;

        const { start, end } = getDateRange();
        if (!start && !end) { infoEl.textContent = ''; return; }

        const parts = [];
        if (start) parts.push(`dari ${start}`);
        if (end) parts.push(`sampai ${end}`);
        infoEl.textContent = `Filter aktif: ${parts.join(' ')}`;
    }

    async function renderAttendanceSparks() {
        const M = window.NexusMetrics;
        if (!M) return;

        try {
            const r = await fetch('/api/v1/metrics/attendance-history?days=7', {
                credentials: 'same-origin',
            });
            const data = await r.json();
            if (!data.success) return;

            const hadir = data.hadir || [];
            const kartu = data.kartu || [];
            const unknown = data.unknown || [];

            M.renderSparkline('statHadirHariIni', hadir, '#22c55e');
            M.renderSparkline('statTotalKartu', kartu, '#8b5cf6');
            M.renderSparkline('statBelumTerdaftar', unknown, '#f97316');

            const calcTrend = (arr) => {
                if (!Array.isArray(arr) || arr.length < 4) return 0;
                const half = Math.floor(arr.length / 2);
                const first = arr.slice(0, half).reduce((a, b) => a + b, 0);
                const second = arr.slice(half).reduce((a, b) => a + b, 0);
                if (first === 0) return second > 0 ? 100 : 0;
                return Math.round(((second - first) / first) * 100);
            };

            M.setTrend('statHadirHariIni', calcTrend(hadir), { label: 'vs minggu lalu' });
            M.setTrend('statTotalKartu', calcTrend(kartu), { label: 'vs minggu lalu' });
            M.setTrend('statBelumTerdaftar', calcTrend(unknown), { label: 'vs minggu lalu', invertColors: true });
        } catch (e) {
            console.warn('[Attendance] sparkline fetch failed', e);
        }
    }

    window.__nexusRenderAttendanceSparks = renderAttendanceSparks;

    function applyDateFilter() {
        if (typeof window.__nexusLoadAttendance === 'function') {
            window.__nexusLoadAttendance();
        }
        updateFilterInfo();
    }

    function clearDateFilter() {
        const startEl = $('attendanceStartDate');
        const endEl = $('attendanceEndDate');
        if (startEl) startEl.value = '';
        if (endEl) endEl.value = '';
        applyDateFilter();
    }

    function exportCSV() {
        const { start, end } = getDateRange();
        const params = new URLSearchParams();
        if (start) params.set('start', start);
        if (end) params.set('end', end);

        const url = `/api/v1/attendance/export${params.toString() ? '?' + params.toString() : ''}`;
        window.location.href = url;
    }

    function bind() {
        const applyBtn = $('attendanceApplyFilter');
        if (applyBtn) applyBtn.addEventListener('click', applyDateFilter);

        const clearBtn = $('attendanceClearFilter');
        if (clearBtn) clearBtn.addEventListener('click', clearDateFilter);

        const exportBtn = $('attendanceExportBtn');
        if (exportBtn) exportBtn.addEventListener('click', exportCSV);

        ['attendanceStartDate', 'attendanceEndDate'].forEach(id => {
            const el = $(id);
            if (el) el.addEventListener('change', applyDateFilter);
        });
    }

    function init() {
        bind();
        console.log('[Attendance] v5.0 ready');
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();