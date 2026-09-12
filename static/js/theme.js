/* ==========================================
   NEXUS IoT - Theme Manager
   ========================================== */

(function() {
    'use strict';

    const THEME_KEY = 'nexus-theme';
    const THEMES = { DARK: 'dark', LIGHT: 'light' };

    const ThemeManager = {
        /**
         * Ambil tema saat ini
         * @returns {'dark'|'light'}
         */
        get() {
            return localStorage.getItem(THEME_KEY) || THEMES.DARK;
        },

        /**
         * Set tema
         * @param {'dark'|'light'} theme
         */
        set(theme) {
            if (!Object.values(THEMES).includes(theme)) {
                console.warn('[Theme] Invalid theme:', theme);
                return;
            }

            document.documentElement.setAttribute('data-theme', theme);
            localStorage.setItem(THEME_KEY, theme);

            // Update meta theme-color
            const meta = document.querySelector('meta[name="theme-color"]');
            if (meta) {
                meta.content = theme === THEMES.LIGHT ? '#f5f5f7' : '#000000';
            }

            // Dispatch event untuk listener
            window.dispatchEvent(new CustomEvent('themechange', { detail: { theme } }));
        },

        /**
         * Toggle antara dark & light
         * @returns {'dark'|'light'} tema baru
         */
        toggle() {
            const newTheme = this.get() === THEMES.LIGHT ? THEMES.DARK : THEMES.LIGHT;
            this.set(newTheme);
            return newTheme;
        },

        /**
         * Init — apply tema tersimpan
         */
        init() {
            const theme = this.get();
            document.documentElement.setAttribute('data-theme', theme);
            return theme;
        },

        /**
         * Cek apakah sedang dark mode
         */
        isDark() {
            return this.get() === THEMES.DARK;
        },

        /**
         * Register listener untuk perubahan tema
         * @param {Function} callback
         */
        onChange(callback) {
            window.addEventListener('themechange', (e) => callback(e.detail.theme));
        }
    };

    // Init saat load
    ThemeManager.init();

    // Expose ke global
    window.ThemeManager = ThemeManager;
    window.toggleTheme = () => ThemeManager.toggle();

    console.log('[Theme] Initialized:', ThemeManager.get());
})();