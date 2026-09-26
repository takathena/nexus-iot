/* ==========================================
   NEXUS IoT - API Helper (v2 FIXED)
   Fix: 401 clear session + redirect
   ========================================== */

(function() {
    'use strict';

    const metaTag = document.querySelector('meta[name="csrf-token"]');
    const CSRF_TOKEN = metaTag ? metaTag.content : '';

    if (!CSRF_TOKEN) console.warn('[API] CSRF token tidak ditemukan.');

    async function apiFetch(url, options = {}) {
        const method = (options.method || 'GET').toUpperCase();
        const headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            ...(options.headers || {})
        };

        if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
            headers['X-CSRFToken'] = CSRF_TOKEN;
        }

        return fetch(url, {
            ...options,
            method,
            headers,
            credentials: 'same-origin'
        });
    }

    // ✅ FIX: clear sessionStorage saat 401
    function clearClientSession() {
        try {
            sessionStorage.removeItem('nexus_back_url');
            sessionStorage.removeItem('nexus-last-section');
        } catch (e) {}
    }

    async function apiCall(url, options = {}) {
        try {
            const response = await apiFetch(url, options);

            if (response.status === 401) {
                const path = window.location.pathname || '';
                if (!path.startsWith('/login')) {
                    console.warn('[API] 401 Unauthorized, redirecting to login');
                    clearClientSession();
                    window.location.href = '/login';
                }
                return {
                    success: false,
                    status: 401,
                    error: 'Unauthorized',
                };
            }

            let data;
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                data = await response.json();
            } else {
                data = { success: response.ok, raw: await response.text() };
            }

            if (!response.ok) {
                return {
                    success: false,
                    status: response.status,
                    error: data.error || `HTTP ${response.status}`,
                    data
                };
            }

            return { success: true, status: response.status, data };
        } catch (err) {
            console.error('[API] Request failed:', err);
            return { success: false, status: 0, error: err.message || 'Network error' };
        }
    }

    const API = {
        getDevices: (params = {}) => {
            const qs = new URLSearchParams(params).toString();
            return apiCall(`/api/v1/devices${qs ? '?' + qs : ''}`);
        },
        getDevice: (deviceId) => apiCall(`/api/v1/devices/${encodeURIComponent(deviceId)}`),
        addDevice: (data) => apiCall('/api/v1/devices', { method: 'POST', body: JSON.stringify(data) }),
        updateDevice: (deviceId, data) => apiCall(`/api/v1/devices/${encodeURIComponent(deviceId)}`, { method: 'PUT', body: JSON.stringify(data) }),
        deleteDevice: (deviceId) => apiCall(`/api/v1/devices/${encodeURIComponent(deviceId)}`, { method: 'DELETE' }),
        regenerateKey: (deviceId) => apiCall(`/api/v1/devices/${encodeURIComponent(deviceId)}/regenerate-key`, { method: 'POST' }),
        getDeviceHistory: (deviceId, params = {}) => {
            const qs = new URLSearchParams(params).toString();
            return apiCall(`/api/v1/devices/${encodeURIComponent(deviceId)}/history${qs ? '?' + qs : ''}`);
        },
        getDeviceAlertRules: (deviceId) => apiCall(`/api/v1/devices/${encodeURIComponent(deviceId)}/alert-rules`),
        updateDeviceAlertRules: (deviceId, rules) => apiCall(`/api/v1/devices/${encodeURIComponent(deviceId)}/alert-rules`, { method: 'PUT', body: JSON.stringify(rules) }),

        getDashboard: () => apiCall('/api/v1/dashboard'),
        getDashboardBySlug: (slug) => apiCall(`/api/v1/dashboards/slug/${encodeURIComponent(slug)}`),

        getAlerts: () => apiCall('/api/v1/alerts'),
        getAlertsAll: (params = {}) => {
            const qs = new URLSearchParams(params).toString();
            return apiCall(`/api/v1/alerts/all${qs ? '?' + qs : ''}`);
        },
        getAlertsStats: () => apiCall('/api/v1/alerts/stats'),
        acknowledgeAlert: (alertId) => apiCall(`/api/v1/alerts/${alertId}/acknowledge`, { method: 'POST' }),
        bulkAcknowledge: (ids) => apiCall('/api/v1/alerts/bulk-acknowledge', { method: 'POST', body: JSON.stringify({ ids }) }),

        health: () => apiCall('/health'),
        getSystemInfo: () => apiCall('/api/v1/system/info'),

        getAttendance: () => apiCall('/api/v1/attendance'),
        getAttendanceStats: () => apiCall('/api/v1/attendance/stats'),
        getAttendanceToday: () => apiCall('/api/v1/attendance/today'),
        getUnregisteredCards: () => apiCall('/api/v1/attendance/unregistered'),
        getCardholders: () => apiCall('/api/v1/cardholders'),
        getLastUnknownTap: () => apiCall('/api/v1/attendance/last-unknown'),
        addCardholder: (data) => apiCall('/api/v1/cardholders', { method: 'POST', body: JSON.stringify(data) }),
        deleteCardholder: (uid) => apiCall(`/api/v1/cardholders/${encodeURIComponent(uid)}`, { method: 'DELETE' }),

        fetch: apiFetch,
        call: apiCall
    };

    window.API = API;
    window.apiFetch = apiFetch;
    window.apiCall = apiCall;

    console.log('[API] Initialized');
})();