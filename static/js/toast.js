/* ==========================================
   NEXUS IoT - Toast Notification
   ========================================== */

(function() {
    'use strict';

    let container = null;
    const DEFAULT_DURATION = 3000;

    function ensureContainer() {
        if (container && document.body.contains(container)) return container;

        container = document.createElement('div');
        container.id = 'toast-container';
        container.style.cssText = `
            position: fixed;
            bottom: 22px;
            right: 22px;
            z-index: 99999;
            display: flex;
            flex-direction: column;
            gap: 10px;
            pointer-events: none;
            max-width: 400px;
        `;
        document.body.appendChild(container);
        return container;
    }

    const ICONS = {
        success: 'fa-circle-check',
        error: 'fa-circle-exclamation',
        warning: 'fa-triangle-exclamation',
        info: 'fa-circle-info'
    };

    const COLORS = {
        success: '#30d158',
        error: '#ff453a',
        warning: '#ff9f0a',
        info: '#0a84ff'
    };

    /**
     * Tampilkan toast
     * @param {string} message
     * @param {'success'|'error'|'warning'|'info'} type
     * @param {number} duration ms
     */
    function showToast(message, type = 'success', duration = DEFAULT_DURATION) {
        const c = ensureContainer();

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.style.cssText = `
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 13px 18px;
            background: var(--surface-solid, #1c1c1e);
            border: 1px solid var(--hairline, rgba(255,255,255,.1));
            border-left: 3px solid ${COLORS[type] || COLORS.info};
            border-radius: 12px;
            font-size: 13px;
            font-weight: 600;
            color: var(--text, #f5f5f7);
            box-shadow: 0 12px 30px rgba(0,0,0,.3);
            pointer-events: auto;
            animation: toastSlideIn .35s cubic-bezier(.16,1,.3,1);
            max-width: 400px;
            word-wrap: break-word;
        `;

        toast.innerHTML = `
            <i class="fa-solid ${ICONS[type] || ICONS.info}" style="color:${COLORS[type] || COLORS.info};flex-shrink:0;"></i>
            <span style="flex:1;">${escapeHtml(message)}</span>
        `;

        // Click to dismiss
        toast.style.cursor = 'pointer';
        toast.onclick = () => removeToast(toast);

        c.appendChild(toast);

        if (duration > 0) {
            setTimeout(() => removeToast(toast), duration);
        }

        return toast;
    }

    function removeToast(toast) {
        if (!toast || !toast.parentNode) return;

        toast.style.animation = 'toastSlideOut .3s cubic-bezier(.16,1,.3,1) forwards';
        setTimeout(() => {
            if (toast.parentNode) toast.parentNode.removeChild(toast);
        }, 300);
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = String(str);
        return div.innerHTML;
    }

    // Inject keyframes
    if (!document.getElementById('toast-keyframes')) {
        const style = document.createElement('style');
        style.id = 'toast-keyframes';
        style.textContent = `
            @keyframes toastSlideIn {
                from { transform: translateX(120%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            @keyframes toastSlideOut {
                from { transform: translateX(0); opacity: 1; }
                to { transform: translateX(120%); opacity: 0; }
            }
        `;
        document.head.appendChild(style);
    }

    // Expose ke global
    window.showToast = showToast;
    window.toast = {
        success: (msg, dur) => showToast(msg, 'success', dur),
        error: (msg, dur) => showToast(msg, 'error', dur),
        warning: (msg, dur) => showToast(msg, 'warning', dur),
        info: (msg, dur) => showToast(msg, 'info', dur)
    };

    console.log('[Toast] Initialized');
})();