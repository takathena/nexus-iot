/* ============================================================
   NEXUS AI CHAT — Right panel controller (v2)
   - Toggle via topbar button (bukan floating tab)
   - Markdown rendering di bubble assistant
   ============================================================ */
(function() {
    'use strict';

    const STORAGE_KEY = 'nexus-chat-open';

    const state = {
        history: [],
        isOpen: false,
        isSending: false,
        isOnline: false,
    };

    const els = {};

    /* ============================================================
       MARKDOWN RENDERER (safe subset, XSS-protected)
       ============================================================ */
    function renderMarkdown(text) {
        if (!text) return '';

        // 1) Escape HTML dulu
        let s = String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');

        // 2) Code blocks
        const codeBlocks = [];
        s = s.replace(/```(?:[a-z]*\n)?([\s\S]*?)```/g, (_, code) => {
            codeBlocks.push(code.replace(/\n$/, ''));
            return `\x00CB${codeBlocks.length - 1}\x00`;
        });

        // 3) Inline code
        const inlineCodes = [];
        s = s.replace(/`([^`\n]+)`/g, (_, code) => {
            inlineCodes.push(code);
            return `\x00IC${inlineCodes.length - 1}\x00`;
        });

        // 4) Lists — proses baris per baris
        const lines = s.split('\n');
        const out = [];
        let inUl = false, inOl = false;

        for (const line of lines) {
            const ul = line.match(/^\s*[-*]\s+(.+)$/);
            const ol = line.match(/^\s*\d+\.\s+(.+)$/);

            if (ul) {
                if (inOl) { out.push('</ol>'); inOl = false; }
                if (!inUl) { out.push('<ul class="md-ul">'); inUl = true; }
                out.push(`<li>${ul[1]}</li>`);
            } else if (ol) {
                if (inUl) { out.push('</ul>'); inUl = false; }
                if (!inOl) { out.push('<ol class="md-ol">'); inOl = true; }
                out.push(`<li>${ol[1]}</li>`);
            } else {
                if (inUl) { out.push('</ul>'); inUl = false; }
                if (inOl) { out.push('</ol>'); inOl = false; }
                out.push(line);
            }
        }
        if (inUl) out.push('</ul>');
        if (inOl) out.push('</ol>');
        s = out.join('\n');

        // 5) Headers
        s = s.replace(/^###\s+(.+)$/gm, '<h4 class="md-h">$1</h4>');
        s = s.replace(/^##\s+(.+)$/gm,  '<h3 class="md-h">$1</h3>');
        s = s.replace(/^#\s+(.+)$/gm,   '<h2 class="md-h">$1</h2>');

        // 6) Bold + Italic
        s = s.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
        s = s.replace(/__([^_\n]+)__/g,     '<strong>$1</strong>');
        s = s.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>');
        s = s.replace(/(^|[^_])_([^_\n]+)_(?!_)/g,     '$1<em>$2</em>');

        // 7) Links
        s = s.replace(
            /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
            '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
        );

        // 8) Restore code
        s = s.replace(/\x00CB(\d+)\x00/g, (_, i) =>
            `<pre class="md-pre"><code>${codeBlocks[+i]}</code></pre>`
        );
        s = s.replace(/\x00IC(\d+)\x00/g, (_, i) =>
            `<code class="md-code">${inlineCodes[+i]}</code>`
        );

        // 9) Line breaks
        s = s.replace(/([^\n>])\n([^\n])/g, '$1<br>$2');

        return s;
    }

    /* ============================================================ */

    function init() {
        els.panel = document.getElementById('chatPanel');
        els.tab = document.getElementById('chatTab');
        els.messages = document.getElementById('chatMessages');
        els.input = document.getElementById('chatInput');
        els.send = document.getElementById('chatSend');
        els.status = document.getElementById('chatStatus');
        els.statusText = document.getElementById('chatStatusText');
        els.topbarBtn = document.getElementById('chatToggleBtn');

        if (!els.panel) return;

        // Restore state
        const wasOpen = localStorage.getItem(STORAGE_KEY) === '1';
        if (wasOpen && window.innerWidth > 992) {
            open(false);
        }

        bindEvents();
        checkHealth();
        setInterval(checkHealth, 30000);

        console.log('[NexusChat] Initialized v2');
    }

    function bindEvents() {
        if (els.send) els.send.addEventListener('click', send);

        // Topbar AI toggle button (primary)
        if (els.topbarBtn) {
            els.topbarBtn.addEventListener('click', toggle);
        }
        // Fallback: floating tab (kalau ada)
        if (els.tab) {
            els.tab.addEventListener('click', toggle);
        }

        if (els.input) {
            els.input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    send();
                }
            });
            els.input.addEventListener('input', autoGrow);
        }

        // Suggestion chips
        document.querySelectorAll('.chat-suggestion').forEach(btn => {
            btn.addEventListener('click', () => {
                if (!els.input) return;
                els.input.value = btn.dataset.q || btn.textContent.trim();
                send();
            });
        });

        // Click backdrop to close (empty area click)
        const backdrop = document.getElementById('chatBackdrop');
        if (backdrop) {
            backdrop.addEventListener('click', () => { if (state.isOpen) close(); });
        }

        // Esc menutup panel
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && state.isOpen) toggle();
        });
    }

    function autoGrow() {
        if (!els.input) return;
        els.input.style.height = 'auto';
        els.input.style.height = Math.min(els.input.scrollHeight, 140) + 'px';
    }

    function open(animate = true) {
        state.isOpen = true;
        if (!animate && els.panel) els.panel.style.transition = 'none';

        if (els.panel) els.panel.classList.add('open');
        if (els.tab) els.tab.classList.add('hidden');
        if (els.topbarBtn) els.topbarBtn.classList.add('active');
        document.body.classList.add('chat-open');

        const backdrop = document.getElementById('chatBackdrop');
        if (backdrop) backdrop.classList.add('active');

        localStorage.setItem(STORAGE_KEY, '1');

        if (!animate && els.panel) {
            requestAnimationFrame(() => {
                els.panel.style.transition = '';
            });
        }

        setTimeout(() => els.input && els.input.focus(), animate ? 300 : 0);
    }

    function close() {
        state.isOpen = false;
        if (els.panel) els.panel.classList.remove('open');
        if (els.tab) els.tab.classList.remove('hidden');
        if (els.topbarBtn) els.topbarBtn.classList.remove('active');
        document.body.classList.remove('chat-open');

        const backdrop = document.getElementById('chatBackdrop');
        if (backdrop) backdrop.classList.remove('active');

        localStorage.setItem(STORAGE_KEY, '0');
    }

    function toggle() {
        state.isOpen ? close() : open();
    }

    function scrollBottom() {
        if (els.messages) els.messages.scrollTop = els.messages.scrollHeight;
    }

    function hideWelcome() {
        const w = document.getElementById('chatWelcome');
        if (w) w.remove();
    }

    function addMessage(role, text) {
        const wrap = document.createElement('div');
        wrap.className = `chat-msg ${role}`;

        if (role === 'thinking') {
            wrap.innerHTML = `<div class="chat-bubble">
                <span class="dot"></span><span class="dot"></span><span class="dot"></span>
            </div>`;
        } else {
            const bubble = document.createElement('div');
            bubble.className = 'chat-bubble';
            if (role === 'assistant') {
                bubble.classList.add('chat-bubble-md');
                bubble.innerHTML = renderMarkdown(text);
            } else {
                bubble.textContent = text;
            }
            wrap.appendChild(bubble);
        }

        if (els.messages) els.messages.appendChild(wrap);
        scrollBottom();
        return wrap;
    }

    function addToolsHint(tools) {
        if (!tools || !tools.length) return;
        const hint = document.createElement('div');
        hint.className = 'chat-tools-hint';
        hint.innerHTML = `<i class="fa-solid fa-wrench"></i> ${tools.map(t => t.tool).join(' · ')}`;
        if (els.messages) els.messages.appendChild(hint);
        scrollBottom();
    }

    function getCsrf() {
        const m = document.querySelector('meta[name="csrf-token"]');
        return m ? m.content : '';
    }

    async function checkHealth() {
        try {
            const r = await fetch('/api/v1/chat/health', { credentials: 'same-origin' });
            const d = await r.json();
            if (d.success && d.upstream_ok) {
                state.isOnline = true;
                if (els.status) els.status.className = 'chat-status online';
                if (els.statusText) {
                    const m = (d.model || '').split('/').pop().replace(':free', '');
                    els.statusText.textContent = m.length > 22 ? m.slice(0, 20) + '…' : (m || 'Online');
                }
            } else {
                state.isOnline = false;
                if (els.status) els.status.className = 'chat-status offline';
                if (els.statusText) els.statusText.textContent = d.error || 'Offline';
            }
        } catch (e) {
            state.isOnline = false;
            if (els.status) els.status.className = 'chat-status offline';
            if (els.statusText) els.statusText.textContent = 'Tidak terhubung';
        }
    }

    async function send() {
        const text = els.input ? els.input.value.trim() : '';
        if (!text || state.isSending) return;

        state.isSending = true;
        els.input.value = '';
        els.input.style.height = 'auto';
        if (els.send) els.send.disabled = true;

        hideWelcome();
        addMessage('user', text);
        state.history.push({ role: 'user', content: text });

        const thinking = addMessage('thinking');

        try {
            const r = await fetch('/api/v1/chat', {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrf(),
                },
                body: JSON.stringify({ messages: state.history }),
            });

            const d = await r.json();
            thinking.remove();

            if (!d.success) {
                addMessage('error', '⚠️ ' + (d.error || 'Gagal'));
                return;
            }

            if (d.tools_used && d.tools_used.length) {
                addToolsHint(d.tools_used);
            }

            addMessage('assistant', d.reply);
            state.history.push({ role: 'assistant', content: d.reply });

            if (state.history.length > 20) {
                state.history = state.history.slice(-20);
            }
        } catch (e) {
            thinking.remove();
            addMessage('error', '⚠️ Koneksi gagal: ' + e.message);
        } finally {
            state.isSending = false;
            if (els.send) els.send.disabled = false;
            if (els.input) els.input.focus();
        }
    }

    function clear() {
        if (!confirm('Bersihkan semua percakapan?')) return;
        state.history = [];
        if (els.messages) els.messages.innerHTML = '';
        location.reload();
    }

    window.NexusChat = { toggle, open, close, send, clear };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();