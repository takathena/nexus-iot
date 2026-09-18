/* ==========================================
   NEXUS IoT - Global Error Boundary
   ========================================== */

(function() {
    'use strict';

    const MAX_TOASTS = 3;
    let errorCount = 0;
    let lastErrorTime = 0;

    function showErrorToast(message) {
        const now = Date.now();
        if (now - lastErrorTime < 5000) {
            errorCount++;
            if (errorCount > MAX_TOASTS) return;
        } else {
            errorCount = 1;
            lastErrorTime = now;
        }

        if (window.showToast) {
            window.showToast(message, 'error', 5000);
        } else {
            console.error('[ErrorHandler]', message);
        }
    }

    window.addEventListener('error', (event) => {
        if (event.target && event.target !== window) return;
        const msg = event.message || 'Unknown error';
        console.error('[GlobalError]', msg, event.error);
        showErrorToast('Terjadi kesalahan: ' + msg);
    });

    window.addEventListener('unhandledrejection', (event) => {
        const reason = event.reason;
        const msg = reason?.message || String(reason) || 'Unknown promise rejection';
        console.error('[UnhandledRejection]', msg, reason);
        if (/NetworkError|Failed to fetch|HTTP/.test(msg)) return;
        showErrorToast('Error: ' + msg);
    });

    const originalFetch = window.fetch;
    window.fetch = async function(...args) {
        try {
            const response = await originalFetch.apply(this, args);
            if (response.status >= 500 && response.status < 600) {
                console.warn('[Fetch] Server error:', response.status, args[0]);
            }
            return response;
        } catch (err) {
            console.error('[Fetch] Network error:', args[0], err);
            throw err;
        }
    };

    console.log('[ErrorHandler] Initialized');
})();