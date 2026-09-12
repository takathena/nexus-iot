/* ==========================================
   NEXUS IoT - API Helper
   Semua request ke server harus pakai apiFetch()
   ========================================== */

(function() {
    'use strict';

    // Ambil CSRF token dari meta tag
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    const CSRF_TOKEN = metaTag ? metaTag.content : '';

    if (!CSRF_TOKEN) {
        console.warn('[API] CSRF token tidak ditemukan. Form POST akan gagal.');
    }

    /**
     * Fetch wrapper dengan CSRF token & credentials otomatis
     * @param {string} url - Endpoint URL
     * @param {object} options - Fetch options
     * @returns {Promise<Response>}
     */
    async function apiFetch(url, options = {}) {
        const method = (options.method || 'GET').toUpperCase();
        const headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            ...(options.headers || {})
        };

        // Tambahkan CSRF token untuk method yang mengubah data
        if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
            headers['X-CSRFToken'] = CSRF_TOKEN;
        }

        const response = await fetch(url, {
            ...options,
            method,
            headers,
            credentials: 'same-origin'
        });

        return response;
    }

    /**
     * API call yang otomatis parse JSON dan handle error
     * @param {string} url
     * @param {object} options
     * @returns {Promise<{success: boolean, data?: any, error?: string, status: number}>}
     */
    async function apiCall(url, options = {}) {
        try {
            const response = await apiFetch(url, options);

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

            return {
                success: true,
                status: response.status,
                data
            };
        } catch (err) {
            console.error('[API] Request failed:', err);
            return {
                success: false,
                status: 0,
                error: err.message || 'Network error'
            };
        }
    }

    // ==========================================
    // HIGH-LEVEL API METHODS
    // ==========================================
    const API = {
        // Devices
        getDevices: (params = {}) => {
            const qs = new URLSearchParams(params).toString();
            return apiCall(`/api/v1/devices${qs ? '?' + qs : ''}`);
        },

        getDevice: (deviceId) => apiCall(`/api/v1/devices/${encodeURIComponent(deviceId)}`),

        addDevice: (data) => apiCall('/api/v1/devices', {
            method: 'POST',
            body: JSON.stringify(data)
        }),

        updateDevice: (deviceId, data) => apiCall(`/api/v1/devices/${encodeURIComponent(deviceId)}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        }),

        deleteDevice: (deviceId) => apiCall(`/api/v1/devices/${encodeURIComponent(deviceId)}`, {
            method: 'DELETE'
        }),

        regenerateKey: (deviceId) => apiCall(`/api/v1/devices/${encodeURIComponent(deviceId)}/regenerate-key`, {
            method: 'POST'
        }),

        getDeviceHistory: (deviceId, params = {}) => {
            const qs = new URLSearchParams(params).toString();
            return apiCall(`/api/v1/devices/${encodeURIComponent(deviceId)}/history${qs ? '?' + qs : ''}`);
        },

        // Dashboard
        getDashboard: () => apiCall('/api/v1/dashboard'),

        // Alerts
        getAlerts: () => apiCall('/api/v1/alerts'),

        acknowledgeAlert: (alertId) => apiCall(`/api/v1/alerts/${alertId}/acknowledge`, {
            method: 'POST'
        }),

        // Health
        health: () => apiCall('/health'),

        // Expose raw helpers
        fetch: apiFetch,
        call: apiCall
    };

    // Expose ke global
    window.API = API;
    window.apiFetch = apiFetch;
    window.apiCall = apiCall;

    console.log('[API] Initialized');
})();