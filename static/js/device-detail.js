/* ============================================================
   NEXUS — Device Detail page logic
   Requires: api.js? (page-local api() below), theme.js (ThemeManager)
   ============================================================ */
/* ============================================================
   NEXUS Device Detail — v3
   ============================================================ */
const CSRF = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';

/* ---------- Sensor meta (palette vibrant) ---------- */
const SENSOR_META = {
  temperature: {icon:'fa-temperature-half', color:'#ef6a6a', unit:'°C', range:[0,50]},
  humidity:    {icon:'fa-droplet',          color:'#5b9eff', unit:'%',  range:[0,100]},
  moisture:    {icon:'fa-water',            color:'#38bdf8', unit:'%',  range:[0,100]},
  lux:         {icon:'fa-sun',              color:'#f0b547', unit:'lux',range:[0,1000]},
  co2:         {icon:'fa-cloud',            color:'#3ecf8e', unit:'ppm',range:[0,2000]},
  voc:         {icon:'fa-wind',             color:'#b078f0', unit:'ppb',range:[0,500]},
  gas_level:   {icon:'fa-fire',             color:'#f59e0b', unit:'ppm',range:[0,100]},
  air_quality: {icon:'fa-lungs',            color:'#5b9eff', unit:'AQI',range:[0,500]},
  smoke:       {icon:'fa-smog',             color:'#a78bfa', unit:'ppm',range:[0,1000]},
  motion:      {icon:'fa-person-running',   color:'#22d3ee', unit:'',   range:[0,1]},
  rfid:        {icon:'fa-id-card',          color:'#a3e635', unit:'',   range:[0,1]},
};
const getSensor = k => SENSOR_META[k] || {icon:'fa-microchip', color:'#adb5c2', unit:'', range:[0,100]};
const gaugePct = (k,v) => {
  const [a,b] = getSensor(k).range;
  return Math.min(100, Math.max(0, ((v-a)/(b-a))*100));
};

/* ---------- Helpers ---------- */
const esc = s => { const d = document.createElement('div'); d.textContent = String(s ?? ''); return d.innerHTML; };
const fmtUp = s => {
  if(!s && s !== 0) return '—';
  s = parseInt(s) || 0;
  if(s < 60) return `${s}s`;
  const d = Math.floor(s/86400), h = Math.floor((s%86400)/3600), m = Math.floor((s%3600)/60);
  if(d > 0) return `${d}h ${h}j`;
  if(h > 0) return `${h}j ${m}m`;
  return `${m}m`;
};
const fmtTime = iso => {
  if(!iso) return '—';
  try{
    const d = new Date(String(iso).replace(' ','T') + '+07:00');
    return d.toLocaleString('id-ID', {
      day:'2-digit', month:'short', year:'numeric',
      hour:'2-digit', minute:'2-digit', second:'2-digit',
      timeZone:'Asia/Jakarta'
    }) + ' WIB';
  }catch(e){ return '—'; }
};
const fmtRelative = iso => {
  if(!iso) return '—';
  try{
    const d = new Date(String(iso).replace(' ','T') + '+07:00');
    const diff = (Date.now() - d.getTime()) / 1000;
    if(diff < 60) return 'baru saja';
    if(diff < 3600) return `${Math.floor(diff/60)} mnt lalu`;
    if(diff < 86400) return `${Math.floor(diff/3600)} jam lalu`;
    if(diff < 604800) return `${Math.floor(diff/86400)} hari lalu`;
    return d.toLocaleDateString('id-ID', {day:'2-digit', month:'short', timeZone:'Asia/Jakarta'});
  }catch(e){ return '—'; }
};

function toast(msg){
  const t = document.createElement('div');
  t.className = 'toast';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => {
    t.style.opacity = '0';
    t.style.transition = 'opacity .3s';
    setTimeout(() => t.remove(), 300);
  }, 1800);
}

/* ---------- Modal ---------- */
function openModal(id){
  const el = document.getElementById(id);
  if(el){ el.classList.add('open'); document.body.style.overflow = 'hidden'; }
}
function closeModal(id){
  const el = document.getElementById(id);
  if(el) el.classList.remove('open');
  if(!document.querySelector('.modal.open')) document.body.style.overflow = '';
}
document.querySelectorAll('.modal').forEach(m => {
  m.addEventListener('click', e => { if(e.target === m) closeModal(m.id); });
});
document.addEventListener('keydown', e => {
  if(e.key === 'Escape') document.querySelectorAll('.modal.open').forEach(m => closeModal(m.id));
});

/* ---------- Theme ---------- */
updateThemeIcon();
window.ThemeManager.onChange(updateThemeIcon);
function updateThemeIcon(){
  const i = document.getElementById('themeIcon');
  if(i) i.className = document.documentElement.getAttribute('data-theme') === 'light'
    ? 'fa-solid fa-sun'
    : 'fa-solid fa-moon';
}

/* ---------- Back navigation ---------- */
(function setupBack(){
  const btn = document.getElementById('btnBack');
  let back = '/mobile';
  try{
    const stored = sessionStorage.getItem('nexus_back_url');
    if(stored && stored.startsWith('/')) back = stored;
  }catch(e){}
  btn.onclick = () => {
    try{ sessionStorage.removeItem('nexus_back_url'); }catch(e){}
    window.location.href = back;
  };
})();

/* ---------- Export ---------- */
document.getElementById('btnExport').onclick = () => {
  window.location.href = `/api/v1/devices/${encodeURIComponent(deviceId)}/export?format=csv&hours=24`;
};

/* ---------- Render: status ---------- */
function renderStatus(device){
  const bar = document.getElementById('statusBar');
  const pulse = document.getElementById('statusPulse');
  const label = document.getElementById('statusLabel');
  const sub = document.getElementById('statusSub');
  const live = document.getElementById('liveBadge');

  let statusClass = device.status || 'offline';
  let statusText = statusClass.toUpperCase();
  let subText = '';
  let barClass = statusClass === 'online' ? 'ok' : 'crit';

  if(device.status === 'online'){
    subText = `Aktif ${fmtRelative(device.last_seen)}`;
  } else {
    subText = device.last_seen
      ? `Terakhir aktif ${fmtRelative(device.last_seen)}`
      : 'Belum pernah aktif';
  }

  if(device.active_alerts && device.active_alerts.length > 0){
    const top = device.active_alerts[0].severity;
    statusClass = top;
    if(top === 'danger'){ statusText = 'BAHAYA'; barClass = 'crit'; }
    else if(top === 'warning'){ statusText = 'PERINGATAN'; barClass = 'warn'; }
    else if(top === 'info'){ statusText = 'INFO'; barClass = 'info'; }
    subText = `${device.active_alerts.length} alert • ${subText}`;
  }

  bar.className = 'status-bar ' + barClass;
  pulse.className = 'status-pulse ' + statusClass;
  label.textContent = statusText;
  sub.textContent = subText;
  live.style.display = device.status === 'online' ? 'inline-flex' : 'none';
}

/* ---------- Render: alerts ---------- */
function renderAlerts(alerts){
  const body = document.getElementById('alertBody');
  const count = document.getElementById('alertCount');

  if(!alerts || !alerts.length){
    count.textContent = '';
    body.innerHTML = `
      <div class="empty">
        <i class="fa-solid fa-circle-check" style="color:var(--ok);opacity:1;"></i>
        <div class="empty-title" style="color:var(--ok);">Semua Normal</div>
        <div class="empty-sub">Tidak ada alert aktif</div>
      </div>`;
    return;
  }

  count.textContent = `${alerts.length} alert`;
  body.innerHTML = alerts.map(a => {
    const sev = a.severity || 'info';
    return `<div class="alert-item">
      <div class="alert-head">
        <span class="alert-sev ${sev}">${esc(sev)}</span>
        <span class="alert-head-type">${esc(a.alert_type || '')}</span>
      </div>
      <div class="alert-msg">${esc(a.message || '—')}</div>
      <div class="alert-meta">
        <span>${fmtTime(a.created_at)}</span>
      </div>
    </div>`;
  }).join('');
}

/* ---------- Render: info ---------- */
function renderInfo(device){
  const wifi = device.latest_data?.wifi_ssid || null;
  const uptime = fmtUp(device.latest_data?.uptime_seconds || 0);
  const interval = fmtUp(device.expected_interval || 60);
  const timeout = fmtUp(device.offline_timeout || 900);
  const lastSeen = device.last_seen ? fmtTime(device.last_seen) : null;

  const rows = [
    {label:'ID Perangkat', value:device.device_id, mono:true},
    {label:'Tipe', value:device.device_type || 'Universal'},
    {label:'Lokasi', value:device.location || null, muted:!device.location, emptyText:'Belum diatur'},
    {label:'WiFi SSID', value:wifi, mono:true, muted:!wifi, emptyText:'—'},
    {label:'Uptime', value:uptime, mono:true},
    {label:'Interval Kirim', value:interval, mono:true},
    {label:'Offline Timeout', value:timeout, mono:true},
    {label:'Terakhir Aktif', value:lastSeen, muted:!lastSeen, emptyText:'Belum pernah'},
  ];

  if(device.description){
    rows.push({label:'Deskripsi', value:device.description});
  }

  document.getElementById('infoBody').innerHTML = `
    <div class="info-list">
      ${rows.map(r => {
        const cls = ['info-value', r.mono ? 'mono' : '', r.muted ? 'muted' : ''].filter(Boolean).join(' ');
        const val = r.value ?? (r.emptyText || '—');
        return `<div class="info-row">
          <span class="info-label">${esc(r.label)}</span>
          <span class="${cls}">${esc(val)}</span>
        </div>`;
      }).join('')}
    </div>
  `;
}

/* ---------- Render: sensors ---------- */
function renderSensors(device){
  const body = document.getElementById('sensorBody');
  const meta = document.getElementById('sensorMeta');

  if(!device.latest_data?.data){
    meta.textContent = '';
    body.innerHTML = `
      <div class="empty">
        <i class="fa-solid fa-satellite-dish"></i>
        <div class="empty-title">Belum Ada Data</div>
        <div class="empty-sub">Perangkat belum mengirimkan data sensor</div>
      </div>`;
    return;
  }

  const sd = device.latest_data.data;
  const entries = Object.entries(sd).filter(([k]) => k !== 'uid' && k !== 'card_id');

  meta.textContent = device.latest_data.sensor_type || '';

  if(!entries.length){
    body.innerHTML = '<div class="empty"><div class="empty-title">Tidak ada data sensor</div></div>';
    return;
  }

  body.innerHTML = `
    <div class="sensor-grid">
      ${entries.map(([k, v]) => {
        const m = getSensor(k);
        const label = k.replace(/_/g,' ').replace(/\b\w/g, c => c.toUpperCase());
        const pct = typeof v === 'number' ? gaugePct(k, v) : 0;
        return `<div class="sensor-card">
          <div class="sensor-head">
            <div class="sensor-icon" style="background:${m.color}22;color:${m.color};">
              <i class="fa-solid ${m.icon}"></i>
            </div>
            <div class="sensor-name">${esc(label)}</div>
          </div>
          <div class="sensor-value" style="color:${m.color};">${esc(String(v))}</div>
          <div class="sensor-unit">${esc(m.unit || '\u00A0')}</div>
          <div class="sensor-gauge">
            <div class="sensor-gauge-fill" style="width:${pct}%;background:${m.color};color:${m.color};"></div>
          </div>
        </div>`;
      }).join('')}
    </div>
  `;
}

/* ---------- Load ---------- */
async function loadDetail(){
  try{
    const r = await fetch(`/api/v1/devices/${encodeURIComponent(deviceId)}`);
    const d = await r.json();

    if(!d.success){
      document.getElementById('statusLabel').textContent = 'Gagal memuat';
      document.getElementById('statusSub').textContent = d.error || 'Perangkat tidak ditemukan';
      return;
    }

    const dev = d.device;
    document.getElementById('deviceName').textContent = dev.device_name || dev.device_id;
    document.getElementById('deviceIdDisplay').textContent = dev.device_id;

    renderStatus(dev);
    renderAlerts(dev.active_alerts);
    renderInfo(dev);
    renderSensors(dev);

  }catch(e){
    console.error('[DeviceDetail]', e);
    document.getElementById('infoBody').innerHTML = `
      <div class="empty">
        <i class="fa-solid fa-triangle-exclamation"></i>
        <div class="empty-title">Koneksi Gagal</div>
        <div class="empty-sub">Tidak dapat memuat data perangkat</div>
      </div>`;
  }
}

/* ---------- Regenerate key ---------- */
async function regenKey(){
  if(!confirm(`Regenerate API Key untuk "${deviceId}"?\n\nKey lama tidak akan berfungsi lagi.`)) return;
  try{
    const r = await fetch(`/api/v1/devices/${encodeURIComponent(deviceId)}/regenerate-key`, {
      method: 'POST',
      headers: {'Content-Type':'application/json', 'X-CSRFToken': CSRF}
    });
    const d = await r.json();
    if(d.success){
      document.getElementById('keyValue').textContent = d.api_key;
      openModal('m-key');
    } else {
      alert('Gagal: ' + (d.error || ''));
    }
  }catch(e){ alert('Error: ' + e.message); }
}

function copyKey(){
  const key = document.getElementById('keyValue').textContent;
  if(navigator.clipboard){
    navigator.clipboard.writeText(key).then(() => toast('API Key disalin'));
  } else {
    alert('Copy manual:\n' + key);
  }
}

/* ---------- Delete ---------- */
function openDelete(){
  document.getElementById('delDesc').textContent =
    `Perangkat "${document.getElementById('deviceName').textContent}" akan dihapus permanen beserta semua data sensornya. Tindakan ini tidak dapat dibatalkan.`;
  document.getElementById('delLabel').innerHTML =
    `Ketik <code>${esc(deviceId)}</code> untuk konfirmasi`;
  const input = document.getElementById('delInput');
  input.value = '';
  input.placeholder = `Ketik ${deviceId}...`;
  document.getElementById('delBtn').disabled = true;
  openModal('m-del');
  setTimeout(() => input.focus(), 200);
}

document.getElementById('delInput').addEventListener('input', e => {
  document.getElementById('delBtn').disabled = e.target.value.trim() !== deviceId;
});

async function confirmDelete(){
  const input = document.getElementById('delInput').value.trim();
  if(input !== deviceId){ alert('Konfirmasi salah'); return; }

  const btn = document.getElementById('delBtn');
  btn.disabled = true;
  btn.textContent = 'Menghapus...';

  try{
    const r = await fetch(`/api/v1/devices/${encodeURIComponent(deviceId)}`, {
      method: 'DELETE',
      headers: {'X-CSRFToken': CSRF}
    });
    const d = await r.json();
    if(d.success){
      closeModal('m-del');
      try{ sessionStorage.removeItem('nexus_back_url'); }catch(e){}
      toast('Perangkat dihapus');
      setTimeout(() => window.location.href = '/mobile', 500);
    } else {
      alert('Gagal: ' + (d.error || ''));
      btn.disabled = false;
      btn.textContent = 'Hapus';
    }
  }catch(e){
    alert('Error: ' + e.message);
    btn.disabled = false;
    btn.textContent = 'Hapus';
  }
}

/* ---------- Init ---------- */
loadDetail();
setInterval(loadDetail, 10000);
