/* ==========================================
   NEXUS IoT - API Helper (v3 FIXED)
   Fix:
     - 401 clear session + redirect
     - Global flatten error object → string
       (fix bug "[object Object]" di toast)
   ========================================== */

(function() {
    'use strict';

    const metaTag = document.querySelector('meta[name="csrf-token"]');
    const CSRF_TOKEN = metaTag ? metaTag.content : '';

    if (!CSRF_TOKEN) console.warn('[API] CSRF token tidak ditemukan.');

    // ==========================================
    // ERROR FLATTENER
    // ==========================================
    /**
     * Flatten error dari berbagai bentuk menjadi string readable.
     * Handle:
     *   - string       → return as-is
     *   - array        → join dengan "; "
     *   - object       → "field: msg" (Marshmallow style)
     *   - nested       → recursive
     *   - null/undef   → fallback
     */
    function flattenError(error, fallback = 'Terjadi kesalahan') {
        if (error === null || error === undefined || error === '') {
            return fallback;
        }

        // Already string
        if (typeof error === 'string') {
            return error.trim() || fallback;
        }

        // Number/boolean
        if (typeof error === 'number' || typeof error === 'boolean') {
            return String(error);
        }

        // Array → join
        if (Array.isArray(error)) {
            const parts = error
                .map(e => flattenError(e, ''))
                .filter(s => s && s !== fallback);
            return parts.length > 0 ? parts.join('; ') : fallback;
        }

        // Object → "field: msg, field2: msg2"
        if (typeof error === 'object') {
            const parts = [];
            for (const [key, value] of Object.entries(error)) {
                if (value === null || value === undefined) continue;

                // Array of messages
                if (Array.isArray(value)) {
                    value.forEach(msg => {
                        const flat = flattenError(msg, '');
                        if (flat && flat !== fallback) {
                            parts.push(`${key}: ${flat}`);
                        }
                    });
                }
                // Nested object
                else if (typeof value === 'object') {
                    const nested = flattenError(value, '');
                    if (nested && nested !== fallback) {
                        parts.push(`${key}: ${nested}`);
                    }
                }
                // Primitive
                else {
                    const flat = String(value).trim();
                    if (flat) parts.push(`${key}: ${flat}`);
                }
            }
            return parts.length > 0 ? parts.join(' | ') : fallback;
        }

        return String(error) || fallback;
    }

    // ==========================================
    // FETCH WRAPPER
    // ==========================================
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

    function clearClientSession() {
        try {
            sessionStorage.removeItem('nexus_back_url');
            sessionStorage.removeItem('nexus-last-section');
        } catch (e) {}
    }

    async function apiCall(url, options = {}) {
        try {
            const response = await apiFetch(url, options);

            // 401 → redirect login
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

            // ==========================================
            // FLATTEN ERROR (fix bug [object Object])
            // ==========================================
            const rawError = data && data.error;

            if (!response.ok) {
                return {
                    success: false,
                    status: response.status,
                    error: flattenError(rawError, `HTTP ${response.status}`),
                    data,
                };
            }

            // Response OK tapi success=false (rare case)
            if (data && data.success === false && rawError) {
                return {
                    success: false,
                    status: response.status,
                    error: flattenError(rawError, 'Gagal'),
                    data,
                };
            }

            return {
                success: true,
                status: response.status,
                data,
            };
        } catch (err) {
            console.error('[API] Request failed:', err);
            return {
                success: false,
                status: 0,
                error: err.message || 'Network error',
            };
        }
    }

    // ==========================================
    // PUBLIC API
    // ==========================================
    const API = {
        // Devices
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

        // Dashboard
        getDashboard: () => apiCall('/api/v1/dashboard'),
        getDashboardBySlug: (slug) => apiCall(`/api/v1/dashboards/slug/${encodeURIComponent(slug)}`),

        // Alerts
        getAlerts: () => apiCall('/api/v1/alerts'),
        getAlertsAll: (params = {}) => {
            const qs = new URLSearchParams(params).toString();
            return apiCall(`/api/v1/alerts/all${qs ? '?' + qs : ''}`);
        },
        getAlertsStats: () => apiCall('/api/v1/alerts/stats'),
        acknowledgeAlert: (alertId) => apiCall(`/api/v1/alerts/${alertId}/acknowledge`, { method: 'POST' }),
        bulkAcknowledge: (ids) => apiCall('/api/v1/alerts/bulk-acknowledge', { method: 'POST', body: JSON.stringify({ ids }) }),

        // System
        health: () => apiCall('/health'),
        getSystemInfo: () => apiCall('/api/v1/system/info'),

        // Attendance
        getAttendance: () => apiCall('/api/v1/attendance'),
        getAttendanceStats: () => apiCall('/api/v1/attendance/stats'),
        getAttendanceToday: () => apiCall('/api/v1/attendance/today'),
        getUnregisteredCards: () => apiCall('/api/v1/attendance/unregistered'),
        getCardholders: () => apiCall('/api/v1/cardholders'),
        getLastUnknownTap: () => apiCall('/api/v1/attendance/last-unknown'),
        addCardholder: (data) => apiCall('/api/v1/cardholders', { method: 'POST', body: JSON.stringify(data) }),
        deleteCardholder: (uid) => apiCall(`/api/v1/cardholders/${encodeURIComponent(uid)}`, { method: 'DELETE' }),

        // Raw access
        fetch: apiFetch,
        call: apiCall,

        // Utility (bisa dipakai di module lain)
        flattenError,
    };

    // Expose ke window
    window.API = API;
    window.apiFetch = apiFetch;
    window.apiCall = apiCall;
    window.flattenError = flattenError;   // ← global helper

    console.log('[API] Initialized v3 (with error flattener)');
})();