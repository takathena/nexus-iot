/* ==========================================
   NEXUS IoT v4.3 - Attendance filter & export
   Filter tanggal diterapkan di dashboard.js (bukan DOM manipulation)
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
        if (!start && !end) {
            infoEl.textContent = '';
            return;
        }

        const parts = [];
        if (start) parts.push(`dari ${start}`);
        if (end) parts.push(`sampai ${end}`);
        infoEl.textContent = `Filter aktif: ${parts.join(' ')}`;
    }

    function applyDateFilter() {
        // Delegasi ke dashboard.js (logika filter ada di sana)
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

        // Enter pada input tanggal = apply
        ['attendanceStartDate', 'attendanceEndDate'].forEach(id => {
            const el = $(id);
            if (el) el.addEventListener('change', applyDateFilter);
        });
    }

    function init() {
        bind();
        console.log('[Attendance] Filter & export initialized v4.3');
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();