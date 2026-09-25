/* ==========================================
   NEXUS IoT - Sidebar Toggle (Hybrid v3)
   - Toggle via topbar button (bukan logo sidebar)
   - DESKTOP (>992px): collapse icon-only ↔ full 240px
   - MOBILE (≤992px): mini icon-only 72px ↔ overlay expanded 240px
   ========================================== */

(function() {
    'use strict';

    const STORAGE_KEY = 'nexus-sidebar-collapsed';
    const MOBILE_BREAKPOINT = 992;
    const mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT}px)`);

    function $(id) { return document.getElementById(id); }
    function isMobile() { return mql.matches; }
    function isCollapsedStored() {
        return localStorage.getItem(STORAGE_KEY) === 'true';
    }

    function invalidateMaps() {
        setTimeout(() => {
            if (window.__nexusMaps) {
                window.__nexusMaps.forEach(m => {
                    try { m.invalidateSize(); } catch (e) {}
                });
            }
        }, 300);
    }

    function setIcon(collapsed) {
        const icon = $('sidebarToggleIcon');
        if (!icon) return;
        // bars = expanded (sidebar shown)
        // xmark = mobile overlay open
        // angles-right = collapsed (icon-only)
        if (isMobile()) {
            icon.className = collapsed ? 'fa-solid fa-bars' : 'fa-solid fa-xmark';
        } else {
            icon.className = collapsed ? 'fa-solid fa-angles-right' : 'fa-solid fa-bars';
        }
    }

    // ---------- DESKTOP ----------
    function setDesktopCollapsed(collapsed) {
        const sidebar = $('sidebar');
        const main = $('mainContent');
        if (!sidebar) return;

        sidebar.classList.toggle('collapsed', collapsed);
        if (main) main.classList.toggle('expanded', collapsed);

        try { localStorage.setItem(STORAGE_KEY, collapsed ? 'true' : 'false'); } catch (e) {}

        setIcon(collapsed);

        invalidateMaps();
        window.dispatchEvent(new CustomEvent('sidebar-toggle', {
            detail: { collapsed, mode: 'desktop' }
        }));
    }

    // ---------- MOBILE ----------
    function setMobileExpanded(expanded) {
        const sidebar = $('sidebar');
        const backdrop = $('sidebarBackdrop');
        const main = $('mainContent');
        if (!sidebar) return;

        if (expanded) {
            sidebar.classList.remove('collapsed');
            sidebar.classList.add('mobile-open');
            if (backdrop) backdrop.classList.add('active');
            if (main) main.classList.remove('expanded');
            document.body.style.overflow = 'hidden';
        } else {
            sidebar.classList.add('collapsed');
            sidebar.classList.remove('mobile-open');
            if (backdrop) backdrop.classList.remove('active');
            if (main) main.classList.add('expanded');
            document.body.style.overflow = '';
        }

        setIcon(!expanded);

        invalidateMaps();
        window.dispatchEvent(new CustomEvent('sidebar-toggle', {
            detail: { expanded, mode: 'mobile' }
        }));
    }

    function isMobileExpanded() {
        const sidebar = $('sidebar');
        return sidebar && sidebar.classList.contains('mobile-open');
    }

    // ---------- MODE SWITCH ----------
    function applyMode() {
        const sidebar = $('sidebar');
        const backdrop = $('sidebarBackdrop');
        const main = $('mainContent');
        if (!sidebar) return;

        if (isMobile()) {
            sidebar.classList.remove('mobile-open');
            sidebar.classList.add('collapsed');
            if (backdrop) backdrop.classList.remove('active');
            if (main) main.classList.add('expanded');
            document.body.style.overflow = '';
            setIcon(true);
        } else {
            sidebar.classList.remove('mobile-open');
            if (backdrop) backdrop.classList.remove('active');
            document.body.style.overflow = '';

            const collapsed = isCollapsedStored();
            setDesktopCollapsed(collapsed);
        }

        invalidateMaps();
    }

    function toggleSidebar() {
        if (isMobile()) {
            setMobileExpanded(!isMobileExpanded());
        } else {
            const sidebar = $('sidebar');
            const willCollapse = !sidebar.classList.contains('collapsed');
            setDesktopCollapsed(willCollapse);
        }
    }

    function init() {
        applyMode();

        const toggleBtn = $('sidebarToggleBtn');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                toggleSidebar();
            });
        }

        const backdrop = $('sidebarBackdrop');
        if (backdrop) {
            backdrop.addEventListener('click', () => {
                if (isMobile() && isMobileExpanded()) {
                    setMobileExpanded(false);
                }
            });
        }

        // Esc untuk tutup overlay
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && isMobile() && isMobileExpanded()) {
                setMobileExpanded(false);
            }
        });

        // Auto-close overlay saat pilih menu (mobile)
        document.querySelectorAll('.sidebar-nav .nav-item, .sidebar-footer .nav-item')
            .forEach(item => {
                item.addEventListener('click', () => {
                    if (isMobile() && isMobileExpanded()) {
                        setTimeout(() => setMobileExpanded(false), 120);
                    }
                });
            });

        // Handle resize
        const onChange = () => applyMode();
        if (mql.addEventListener) mql.addEventListener('change', onChange);
        else mql.addListener(onChange);

        console.log('[Sidebar] Initialized v3. Mobile:', isMobile());
    }

    window.toggleSidebar = toggleSidebar;
    window.NexusSidebar = {
        toggle: toggleSidebar,
        setDesktopCollapsed,
        setMobileExpanded,
        isMobile,
        isMobileExpanded,
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();