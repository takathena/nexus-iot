/* ==========================================
   NEXUS IoT v4.1 - Attendance filter & export
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
        const tbody = $('attendanceTableBody');
        if (!tbody) return;

        const { start, end } = getDateRange();
        const rows = tbody.querySelectorAll('tr');

        if (!start && !end) {
            rows.forEach(r => r.style.display = '');
            updateFilterInfo();
            return;
        }

        const startTs = start ? new Date(start + 'T00:00:00+07:00').getTime() : 0;
        const endTs = end ? new Date(end + 'T23:59:59+07:00').getTime() : Infinity;

        let visibleCount = 0;

        rows.forEach(row => {
            const dateEl = row.querySelector('.datetime-display .date');
            const timeEl = row.querySelector('.datetime-display .time');

            if (!dateEl || !timeEl) {
                row.style.display = '';
                return;
            }

            // Parse tanggal dari format "DD Mmm" + time "HH:MM:SS"
            // Sulit parse dari display. Lebih baik pakai data-attribute.
            const ts = row.dataset.timestamp;
            if (!ts) {
                row.style.display = '';
                return;
            }

            const rowTs = new Date(ts.replace(' ', 'T') + '+07:00').getTime();
            if (isNaN(rowTs)) {
                row.style.display = '';
                return;
            }

            if (rowTs >= startTs && rowTs <= endTs) {
                row.style.display = '';
                visibleCount++;
            } else {
                row.style.display = 'none';
            }
        });

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
    }

    // Patch: setelah attendance di-render, tambahkan data-timestamp ke setiap row
    // Sebenarnya lebih baik dashboard.js yang handle, tapi kita observer di sini.
    function observeAttendanceTable() {
        const tbody = $('attendanceTableBody');
        if (!tbody) return;

        const observer = new MutationObserver(() => {
            // Setelah render, kita perlu inject data-timestamp
            // Karena kita tidak punya akses ke raw timestamp di DOM,
            // kita pakai trick: ambil dari judul row kalau ada
            // Solusi: dashboard.js harus tambah data-timestamp="..."
            // → sudah di-patch di renderAttendanceTable (versi v4.1)
        });

        observer.observe(tbody, { childList: true });
    }

    function init() {
        bind();
        observeAttendanceTable();
        console.log('[Attendance] Filter & export initialized');
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();