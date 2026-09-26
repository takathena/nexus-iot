/* ============================================================
   NEXUS — Mobile page logic
   Requires: api.js? (page-local api() below), theme.js (ThemeManager)
   ============================================================ */
/* ============================================================
   NEXUS Mobile v4 — Logic
   ============================================================ */
const CSRF = (document.querySelector('meta[name="csrf-token"]')||{}).content||'';

async function api(url, opts = {}){
  const m = (opts.method||'GET').toUpperCase();
  const h = { 'Accept':'application/json', ...(opts.headers||{}) };
  if(opts.body && !h['Content-Type']) h['Content-Type'] = 'application/json';
  if(['POST','PUT','DELETE','PATCH'].includes(m)) h['X-CSRFToken'] = CSRF;
  return fetch(url, { ...opts, method:m, headers:h, credentials:'same-origin' });
}

/* ===== State ===== */
let devices = [];
let filterDash = 'all', filterDev = 'all';
let charts = [], timeMinutes = 1440;
let dashboardId = null, currentTabId = null, tabs = [];
let attendanceView = 'report';
let alerts = [], alertStatus = 'all', alertSev = '', alertSearch = '';
let alertDateStart = '', alertDateEnd = '';
let alertSelectedIds = new Set();
let sheetDeviceId = null;
let pendingRedirect = null;

// Map
let map = null, mapMarkers = {}, mapReady = false;
let selDeviceId = null, selLat = null, selLng = null, selMarker = null, mapDirty = false;
let mapFilter = 'all', mapSearch = '';
const MAP_DEFAULT_CENTER = [-2.5489, 118.0149];
const MAP_DEFAULT_ZOOM = 5;

/* Sensor data keys */
const DATA_KEYS = {
  temperature:{label:'Suhu',unit:'°C',color:'#ef6a6a'},
  humidity:{label:'Kelembaban',unit:'%',color:'#5b9eff'},
  gas_level:{label:'Gas',unit:'%',color:'#f59e0b'},
  smoke:{label:'Asap',unit:'ppm',color:'#a78bfa'},
  motion:{label:'Gerakan',unit:'',color:'#22d3ee'},
  rfid:{label:'RFID',unit:'',color:'#a3e635'},
  moisture:{label:'K. Tanah',unit:'%',color:'#38bdf8'},
  lux:{label:'Cahaya',unit:'lux',color:'#f0b547'},
  co2:{label:'CO2',unit:'ppm',color:'#3ecf8e'},
  voc:{label:'VOC',unit:'ppb',color:'#b078f0'},
  air_quality:{label:'Kualitas Udara',unit:'AQI',color:'#5b9eff'},
};
const PRESETS = {
  temperature:{label:'Suhu',defaults:{healthy:{min:20,max:26},warning:{min:15,max:30},danger:{min:10,max:35}}},
  humidity:{label:'Kelembaban',defaults:{healthy:{min:40,max:70},warning:{min:30,max:80},danger:{min:20,max:90}}},
  gas_level:{label:'Level Gas',defaults:{healthy:{min:0,max:70},warning:{min:0,max:85},danger:{min:0,max:100}}},
  co2:{label:'CO2',defaults:{healthy:{min:300,max:1000},warning:{min:300,max:1500},danger:{min:300,max:5000}}},
  moisture:{label:'K. Tanah',defaults:{healthy:{min:40,max:70},warning:{min:30,max:80},danger:{min:20,max:90}}},
  lux:{label:'Cahaya',defaults:{healthy:{min:100,max:800},warning:{min:50,max:1000},danger:{min:0,max:2000}}},
};
const COLORS = ['#ef6a6a','#5b9eff','#3ecf8e','#f59e0b','#a78bfa','#22d3ee','#f0b547','#a3e635'];

/* ===== Helpers ===== */
const esc = s => { const d = document.createElement('div'); d.textContent = String(s ?? ''); return d.innerHTML; };
const fmtUp = s => {
  if(!s) return '-';
  s = parseInt(s)||0;
  const d = Math.floor(s/86400), h = Math.floor((s%86400)/3600), m = Math.floor((s%3600)/60);
  if(d>0) return `${d}h ${h}j`;
  if(h>0) return `${h}j ${m}m`;
  return `${m}m`;
};
const parseTs = iso => {
  if(!iso) return null;
  try{ return new Date(String(iso).replace(' ','T')+'+07:00'); }catch(e){ return null; }
};
const fmtTime = iso => {
  const d = parseTs(iso); if(!d) return '-';
  try{ return d.toLocaleTimeString('id-ID',{hour:'2-digit',minute:'2-digit',timeZone:'Asia/Jakarta'}); }
  catch(e){ return '-'; }
};
const fmtDateSplit = iso => {
  const d = parseTs(iso); if(!d) return {date:'-',time:'-'};
  try{
    return {
      date: d.toLocaleDateString('id-ID',{day:'2-digit',month:'short',timeZone:'Asia/Jakarta'}),
      time: d.toLocaleTimeString('id-ID',{hour:'2-digit',minute:'2-digit',second:'2-digit',timeZone:'Asia/Jakarta'})
    };
  }catch(e){ return {date:'-',time:'-'}; }
};
const fmtRelative = iso => {
  const d = parseTs(iso); if(!d) return '-';
  const diff = (Date.now() - d.getTime())/1000;
  if(diff < 60) return 'baru saja';
  if(diff < 3600) return `${Math.floor(diff/60)}m lalu`;
  if(diff < 86400) return `${Math.floor(diff/3600)}j lalu`;
  if(diff < 604800) return `${Math.floor(diff/86400)}h lalu`;
  return d.toLocaleDateString('id-ID',{day:'2-digit',month:'short',timeZone:'Asia/Jakarta'});
};
const deviceStatus = d => {
  if(d.status === 'offline') return 'offline';
  if(d.has_alert && d.top_alert_severity) return d.top_alert_severity;
  return d.status || 'offline';
};
const alertTypeLabel = type => {
  const map = {temperature:'Suhu',humidity:'Kelembaban',gas_level:'Gas',offline:'Offline',smoke:'Asap',motion:'Gerakan',co2:'CO2',moisture:'K. Tanah',lux:'Cahaya',voc:'VOC',air_quality:'Kualitas Udara'};
  return map[type] || String(type||'').replace(/_/g,' ').replace(/\b\w/g,l=>l.toUpperCase());
};
const SENSOR_UNITS = {temperature:'°C',humidity:'%',gas_level:'ppm',smoke:'ppm',moisture:'%',lux:'lux',co2:'ppm',voc:'ppb',air_quality:'AQI',motion:'',rfid:''};
const formatVal = (type, value) => {
  if(value === null || value === undefined) return null;
  const unit = SENSOR_UNITS[type] ?? '';
  const num = parseFloat(value);
  if(isNaN(num)) return String(value);
  return `${parseFloat(num.toFixed(2))}${unit}`;
};
const ackIdOf = a => a.alert_id != null ? a.alert_id : a.id;

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

/* ===== Modal ===== */
function openModal(id){
  const el = document.getElementById(id);
  if(el){ el.classList.add('open'); document.body.classList.add('modal-open'); }
}
function closeModal(id){
  const el = document.getElementById(id);
  if(el) el.classList.remove('open');
  if(!document.querySelector('.modal.open')) document.body.classList.remove('modal-open');
}
document.querySelectorAll('.modal').forEach(m => {
  m.addEventListener('click', e => { if(e.target === m) closeModal(m.id); });
});
document.addEventListener('keydown', e => {
  if(e.key === 'Escape'){
    document.querySelectorAll('.modal.open').forEach(m => closeModal(m.id));
    document.querySelectorAll('.ios-dd.open').forEach(m => m.classList.remove('open'));
  }
});

/* ===== Theme ===== */
updateThemeIcon();
window.ThemeManager.onChange(function(theme){
  updateThemeIcon();
  if(document.getElementById('s-analytics').classList.contains('active')) loadCharts();
});
function updateThemeIcon(){
  const i = document.getElementById('themeIcon');
  if(i) i.className = document.documentElement.getAttribute('data-theme') === 'light'
    ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
}

/* ===== Nav ===== */
function go(name, opts = {}){
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  const el = document.getElementById('s-' + name);
  if(el) el.classList.add('active');
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));

  if(opts.filter) setFilterFull(opts.filter);

  if(name === 'dashboard'){ loadDashboard(); loadActivity(); }
  else if(name === 'map') setTimeout(() => initMap(), 100);
  else if(name === 'analytics') loadTabs().then(() => { if(currentTabId) loadCharts(); });
  else if(name === 'attendance') loadAttend();
  else if(name === 'devices') renderDevicesFull();
  else if(name === 'alerts') loadAlerts();

  window.scrollTo({ top: 0, behavior: 'smooth' });
}
function logout(){ if(confirm('Logout dari NEXUS?')) window.location.href = '/logout'; }
function openDevice(id){
  try{ sessionStorage.setItem('nexus_back_url', '/mobile'); }catch(e){}
  window.location.href = '/device/' + encodeURIComponent(id);
}

/* ===== Dashboard ===== */
async function loadDashboard(){
  try{
    const r = await api('/api/v1/dashboard');
    const d = await r.json();
    if(!d.success) return;
    devices = d.devices || [];

    document.getElementById('sTotal').textContent = d.summary.total_devices;
    document.getElementById('sOnline').textContent = d.summary.online_devices;
    document.getElementById('sOffline').textContent = d.summary.offline_devices;
    document.getElementById('sAlert').textContent = d.summary.active_alerts || 0;

    const badge = document.getElementById('tabAlertBadge');
    if(d.summary.active_alerts > 0){
      badge.textContent = d.summary.active_alerts;
      badge.classList.remove('hidden');
    } else badge.classList.add('hidden');

    updateRing(d.summary);
    updateCounts();
    renderDevices();
    renderDevicesFull();

    // Last update timestamp
    const lu = document.getElementById('dashLastUpdate');
    if(lu){
      const now = new Date();
      lu.textContent = 'Diperbarui ' + now.toLocaleTimeString('id-ID',{hour:'2-digit',minute:'2-digit',timeZone:'Asia/Jakarta'}) + ' WIB';
    }

    if(document.getElementById('s-map').classList.contains('active')){
      loadMapMarkers(); renderMapList();
    }
  }catch(e){ console.error(e); }
}
function updateRing(s){
  const healthy = s.healthy_devices ?? 0, total = s.total_devices ?? 0;
  const pct = total > 0 ? Math.round((healthy/total)*100) : 0;
  const circ = 2*Math.PI*42, offset = circ - (pct/100)*circ;
  const ring = document.getElementById('ringProg');
  if(ring){ ring.setAttribute('stroke-dasharray', circ.toFixed(1)); ring.style.strokeDashoffset = offset; }
  document.getElementById('ringPct').textContent = pct + '%';
  document.getElementById('ringTitle').textContent = total > 0 ? `${healthy} perangkat sehat` : 'Belum ada perangkat';
  document.getElementById('ringCaption').textContent = total > 0
    ? `dari ${total} perangkat terdaftar`
    : 'Tambahkan perangkat untuk memulai monitoring';
}
function updateCounts(){
  const online = devices.filter(d => d.status === 'online').length;
  const offline = devices.filter(d => d.status === 'offline').length;
  const alert = devices.filter(d => d.has_alert === true).length;
  document.getElementById('cAll').textContent = devices.length;
  document.getElementById('cOnline').textContent = online;
  document.getElementById('cOffline').textContent = offline;
  document.getElementById('cAlert').textContent = alert;
  document.getElementById('deviceCountSub').textContent = `${devices.length} perangkat terdaftar`;
  document.getElementById('deviceSubFull').textContent = `${devices.length} perangkat`;
}

function setFilter(f){
  filterDash = f;
  document.querySelectorAll('#filterChips .chip').forEach(c => c.classList.toggle('active', c.dataset.f === f));
  renderDevices();
}
function setFilterFull(f){
  filterDev = f;
  document.querySelectorAll('#deviceChips .chip').forEach(c => c.classList.toggle('active', c.dataset.f === f));
  renderDevicesFull();
}
function filterList(list, f){
  if(f === 'online') return list.filter(d => d.status === 'online');
  if(f === 'offline') return list.filter(d => d.status === 'offline');
  if(f === 'alert') return list.filter(d => d.has_alert === true);
  return list;
}
function renderDevices(){ renderDeviceRows(filterList(devices, filterDash), 'deviceList'); }
function renderDevicesFull(){ renderDeviceRows(filterList(devices, filterDev), 'deviceListFull'); }

function renderDeviceRows(list, targetId){
  const c = document.getElementById(targetId);
  if(!c) return;
  if(!list.length){
    c.innerHTML = '<div class="empty"><i class="fa-solid fa-microchip"></i><div class="empty-title">Tidak ada perangkat</div></div>';
    return;
  }
  c.innerHTML = list.map(d => {
    const st = deviceStatus(d);
    const type = d.device_type || 'Universal';
    const loc = d.location || d.latest_wifi_ssid || '—';
    const uptime = fmtUp(d.latest_uptime_seconds || 0);
    return `<div class="row" onclick="openDevice('${esc(d.device_id)}')">
      <span class="row-status ${st}"></span>
      <div class="row-main">
        <div class="row-title">${esc(d.device_name)}</div>
        <div class="row-sub"><span class="badge-type">${esc(type)}</span>${esc(d.device_id)} · ${esc(loc)} · ${uptime}</div>
      </div>
      <button class="row-more" onclick="event.stopPropagation();openSheet('${esc(d.device_id)}')">
        <i class="fa-solid fa-ellipsis"></i>
      </button>
    </div>`;
  }).join('');
}

/* ===== Activity ===== */
async function loadActivity(){
  const c = document.getElementById('activityList');
  if(!c) return;
  try{
    const r = await api('/api/v1/alerts/all?limit=15');
    const d = await r.json();
    const events = [];
    if(d.success && Array.isArray(d.alerts)){
      d.alerts.slice(0,8).forEach(a => events.push({
        sev: a.severity || 'info',
        title: a.device_name || a.device_id,
        msg: a.message || a.alert_type,
        ts: a.created_at,
        dev: a.device_id
      }));
    }
    devices.forEach(x => {
      if(!x.last_seen) return;
      events.push({
        sev: x.status === 'online' ? 'online' : 'offline',
        title: x.device_name,
        msg: x.status === 'online' ? 'Baru saja online' : 'Terakhir terlihat',
        ts: x.last_seen,
        dev: x.device_id
      });
    });
    events.sort((a,b) => new Date(b.ts) - new Date(a.ts));
    const top = events.slice(0, 8);
    if(!top.length){
      c.innerHTML = '<div class="empty" style="padding:30px;"><div class="empty-title">Belum ada aktivitas</div></div>';
      return;
    }
    const icons = {danger:'fa-fire',warning:'fa-triangle-exclamation',info:'fa-circle-info',online:'fa-circle-check',offline:'fa-power-off'};
    c.innerHTML = top.map(ev => `
      <div class="activity-item" onclick="openDevice('${esc(ev.dev)}')">
        <div class="activity-icon ${ev.sev}"><i class="fa-solid ${icons[ev.sev] || 'fa-bell'}"></i></div>
        <div class="activity-body">
          <div class="activity-text"><strong>${esc(ev.title)}</strong> — ${esc(String(ev.msg).slice(0,70))}</div>
          <div class="activity-time">${fmtTime(ev.ts)}</div>
        </div>
      </div>
    `).join('');
  }catch(e){ c.innerHTML = '<div class="empty" style="padding:30px;"><div class="empty-title">Gagal memuat</div></div>'; }
}

/* ===== Map ===== */
function initMap(force){
  if(mapReady && !force){
    if(map) setTimeout(() => map.invalidateSize(), 100);
    return;
  }
  if(force && map){ try{ map.remove(); }catch(e){} map = null; mapMarkers = {}; mapReady = false; }
  const el = document.getElementById('mMapFull'); if(!el) return;
  map = L.map('mMapFull', {zoomControl:true, attributionControl:false}).setView(MAP_DEFAULT_CENTER, MAP_DEFAULT_ZOOM);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom:19}).addTo(map);
  map.on('click', e => { if(selDeviceId) placeMarker(e.latlng.lat, e.latlng.lng); });
  mapReady = true;
  setTimeout(() => map.invalidateSize(), 150);
  loadMapMarkers(); renderMapList();
}
function resetMapView(){
  if(!map) return;
  map.flyTo(MAP_DEFAULT_CENTER, MAP_DEFAULT_ZOOM, {duration:.8});
  // Clear selection marker
  if(selMarker){ try{ map.removeLayer(selMarker); }catch(e){} selMarker = null; }
  selDeviceId = null; selLat = null; selLng = null; mapDirty = false;
  updateMapBanner();
  toast('View direset');
}
function mapStyle(d){
  if(d.status === 'offline') return {color:'#ef6a6a', label:'OFF'};
  if(d.has_alert && d.top_alert_severity){
    if(d.top_alert_severity === 'danger') return {color:'#ef6a6a', label:'ALERT'};
    if(d.top_alert_severity === 'warning') return {color:'#f0b547', label:'WARN'};
    if(d.top_alert_severity === 'info') return {color:'#5b9eff', label:'INFO'};
  }
  if(d.status === 'online') return {color:'#3ecf8e', label:'ON'};
  return {color:'#7a8290', label:'—'};
}
function loadMapMarkers(){
  if(!map) return;
  Object.values(mapMarkers).forEach(m => { try{ map.removeLayer(m); }catch(e){} });
  mapMarkers = {};
  devices.forEach(d => {
    if(!d.latitude || !d.longitude || (d.latitude === 0 && d.longitude === 0)) return;
    const s = mapStyle(d);
    const m = L.circleMarker([d.latitude,d.longitude], {radius:7, color:s.color, fillColor:s.color, fillOpacity:.9, weight:2}).addTo(map);
    m.bindPopup(`<b>${esc(d.device_name)}</b><br><span style="font-size:11px;color:#888;">${esc(d.device_id)}</span>`);
    mapMarkers[d.device_id] = m;
  });
}
function setMapFilter(f){
  mapFilter = f;
  document.querySelectorAll('#mapChips .chip').forEach(c => c.classList.toggle('active', c.dataset.mf === f));
  renderMapList();
}
document.getElementById('mapSearch').addEventListener('input', e => {
  mapSearch = e.target.value.toLowerCase().trim(); renderMapList();
});
function renderMapList(){
  const c = document.getElementById('mapList'); if(!c) return;
  let list = devices.slice();
  if(mapFilter === 'online') list = list.filter(d => d.status === 'online');
  else if(mapFilter === 'offline') list = list.filter(d => d.status === 'offline');
  else if(mapFilter === 'alert') list = list.filter(d => d.has_alert === true);
  if(mapSearch) list = list.filter(d =>
    (d.device_name||'').toLowerCase().includes(mapSearch) ||
    (d.device_id||'').toLowerCase().includes(mapSearch));

  if(!list.length){
    c.innerHTML = '<div class="empty"><i class="fa-solid fa-map"></i><div class="empty-title">Tidak ada device</div></div>';
    return;
  }
  c.innerHTML = list.map(d => {
    const s = mapStyle(d);
    const hasLoc = d.latitude && d.longitude && !(d.latitude === 0 && d.longitude === 0);
    return `<div class="row" onclick="selectMapDevice('${esc(d.device_id)}')">
      <span class="row-status" style="background:${s.color};box-shadow:0 0 0 3px ${s.color}22;"></span>
      <div class="row-main">
        <div class="row-title">${esc(d.device_name)}</div>
        <div class="row-sub">${esc(d.device_id)}${!hasLoc ? ' · belum ada lokasi' : ''}</div>
      </div>
      <i class="fa-solid fa-chevron-right row-chevron"></i>
    </div>`;
  }).join('');
}
function selectMapDevice(id){
  const d = devices.find(x => x.device_id === id); if(!d) return;
  selDeviceId = id; mapDirty = false;
  selLat = null; selLng = null;
  const hasLoc = d.latitude && d.longitude && !(d.latitude === 0 && d.longitude === 0);
  if(hasLoc){
    selLat = d.latitude; selLng = d.longitude;
    if(map) map.flyTo([d.latitude,d.longitude], 14, {duration:.8});
  } else if(map){
    const c = map.getCenter();
    placeMarker(c.lat, c.lng);
  }
  updateMapBanner(); renderMapList();
}
function placeMarker(lat, lng){
  if(!map) return;
  selLat = lat; selLng = lng;
  if(selMarker) selMarker.setLatLng([lat,lng]);
  else{
    selMarker = L.marker([lat,lng], {draggable:true}).addTo(map);
    selMarker.on('dragend', e => {
      const p = e.target.getLatLng();
      selLat = p.lat; selLng = p.lng; mapDirty = true; updateMapBanner();
    });
  }
  mapDirty = true; updateMapBanner();
}
function updateMapBanner(){
  const b = document.getElementById('mapBanner');
  if(!selDeviceId){ b.classList.add('hidden'); return; }
  const d = devices.find(x => x.device_id === selDeviceId); if(!d){ b.classList.add('hidden'); return; }
  const s = mapStyle(d);
  b.classList.remove('hidden');
  document.getElementById('mapBannerName').textContent = d.device_name;
  document.getElementById('mapBannerDot').style.background = s.color;
  const coordEl = document.getElementById('mapBannerCoord');
  coordEl.innerHTML = selLat != null
    ? `${selLat.toFixed(5)}, ${selLng.toFixed(5)}${mapDirty ? ' · belum disimpan' : ''}`
    : 'Belum ada koordinat';
  document.getElementById('mapSaveBtn').disabled = !(selLat != null && mapDirty);
}
function clearMapSel(){
  if(mapDirty && !confirm('Batalkan perubahan?')) return;
  selDeviceId = null; selLat = null; selLng = null; mapDirty = false;
  if(selMarker && map){ map.removeLayer(selMarker); selMarker = null; }
  updateMapBanner(); renderMapList();
}
async function saveMapLoc(){
  if(!selDeviceId || selLat == null) return;
  const r = await api(`/api/v1/devices/${encodeURIComponent(selDeviceId)}`, {
    method:'PUT', body:JSON.stringify({latitude:selLat, longitude:selLng})
  });
  const d = await r.json();
  if(d.success){
    const dev = devices.find(x => x.device_id === selDeviceId);
    if(dev){ dev.latitude = selLat; dev.longitude = selLng; }
    mapDirty = false; updateMapBanner(); loadMapMarkers(); toast('Lokasi tersimpan');
  } else alert(d.error || 'Gagal');
}

/* ==========================================
   iOS Custom Dropdown helper
   ========================================== */
function bindIosDD(id, onChange) {
  const dd = document.getElementById(id);
  if (!dd) return;
  const trigger = dd.querySelector('.ios-dd-trigger');
  const label = dd.querySelector('.ios-dd-label');
  const items = dd.querySelectorAll('.ios-dd-item');
  if (!trigger || !label) return;

  trigger.addEventListener('click', (e) => {
    e.stopPropagation();
    document.querySelectorAll('.ios-dd.open').forEach(el => {
      if (el !== dd) el.classList.remove('open');
    });
    dd.classList.toggle('open');
  });

  items.forEach(item => {
    item.addEventListener('click', (e) => {
      e.stopPropagation();
      const value = item.dataset.value || item.dataset.min || '';
      const textEl = item.querySelector('span');
      const text = textEl ? textEl.textContent.trim() : '';
      dd.dataset.value = value;
      label.textContent = text;
      items.forEach(i => i.classList.toggle('active', i === item));
      dd.classList.remove('open');
      if (typeof onChange === 'function') onChange(value, text);
    });
  });
}

document.addEventListener('click', (e) => {
  if (!e.target.closest('.ios-dd')) {
    document.querySelectorAll('.ios-dd.open').forEach(el => el.classList.remove('open'));
  }
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.ios-dd.open').forEach(el => el.classList.remove('open'));
  }
});

/* ===== Analytics ===== */
let __analyticsBound = false;
function bindAnalyticsDropdowns() {
  if (__analyticsBound) return;
  __analyticsBound = true;

  bindIosDD('timeDD', (val) => {
    const m = parseInt(val) || 1440;
    timeMinutes = m;
    const label = m < 60 ? `${m} Menit` :
                  m < 1440 ? `${Math.round(m/60)} Jam` :
                  m < 10080 ? `${Math.round(m/1440)} Hari` :
                  m < 43200 ? `${Math.round(m/10080)} Minggu` :
                  `${Math.round(m/43200)} Bulan`;
    const lbl = document.getElementById('timeLabel');
    if (lbl) lbl.textContent = label;
    loadCharts();
  });
}
bindAnalyticsDropdowns();

async function loadTabs(){
  try{
    const r = await api('/api/v1/dashboards');
    const d = await r.json();
    if(!d.success || !d.dashboards.length){ tabs = []; return; }
    const def = d.dashboards.find(x => x.is_default) || d.dashboards[0];
    dashboardId = def.id;
    const tr = await api(`/api/v1/dashboards/${def.id}/analytics-tabs`);
    const td = await tr.json();
    tabs = td.success ? (td.tabs || []) : [];
    if(!currentTabId && tabs.length) currentTabId = tabs[0].id;
    renderTabs();
  }catch(e){ console.error(e); }
}
function renderTabs(){
  const label = document.getElementById('tabLabel');
  const menu = document.getElementById('tabMenu');
  const dd = document.getElementById('tabDD');
  if (!label || !menu) return;
  const cur = tabs.find(t => t.id === currentTabId);
  label.textContent = cur ? cur.name : 'Pilih Tab';

  let html = tabs.map(t => `
    <button type="button" class="ios-dd-item ${t.id === currentTabId ? 'active' : ''}" data-tab-id="${t.id}">
      <i class="fa-solid ${esc(t.icon || 'fa-chart-line')}"></i>
      <span>${esc(t.name)}</span>
      <i class="fa-solid fa-check ios-dd-check"></i>
    </button>
  `).join('');
  html += `<div class="dd-divider" style="height:1px;background:var(--border-soft);margin:4px 6px;"></div>`;
  html += `<button type="button" class="ios-dd-item" data-action="new-tab">
    <i class="fa-solid fa-plus"></i>
    <span>Tambah Tab</span>
    <i class="fa-solid fa-check ios-dd-check" style="opacity:0;"></i>
  </button>`;
  menu.innerHTML = html;

  menu.querySelectorAll('[data-tab-id]').forEach(item => {
    item.addEventListener('click', (e) => {
      e.stopPropagation();
      switchTab(parseInt(item.dataset.tabId));
      if (dd) dd.classList.remove('open');
    });
  });
  const addBtn = menu.querySelector('[data-action="new-tab"]');
  if (addBtn) addBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    openTabModal('new');
    if (dd) dd.classList.remove('open');
  });

  if (dd && !dd.__bound) {
    dd.__bound = true;
    const trigger = dd.querySelector('.ios-dd-trigger');
    if (trigger) trigger.addEventListener('click', (e) => {
      e.stopPropagation();
      document.querySelectorAll('.ios-dd.open').forEach(el => {
        if (el !== dd) el.classList.remove('open');
      });
      dd.classList.toggle('open');
    });
  }
}
function switchTab(id){
  currentTabId = id; renderTabs();
  const dd = document.getElementById('tabDD'); if (dd) dd.classList.remove('open');
  loadCharts();
}
function openTabModal(mode, id, name){
  document.getElementById('tabModalTitle').textContent = mode === 'edit' ? 'Edit Tab' : 'Tambah Tab';
  document.getElementById('tabMode').value = mode;
  document.getElementById('tabId').value = id || '';
  document.getElementById('tabName').value = name || '';
  document.getElementById('tabDeleteBtn').classList.toggle('hidden', mode !== 'edit');
  openModal('m-tab');
}
async function saveTab(){
  const mode = document.getElementById('tabMode').value;
  const id = document.getElementById('tabId').value;
  const name = document.getElementById('tabName').value.trim();
  if(!name){ alert('Nama tab wajib'); return; }
  let url, method;
  if(mode === 'edit' && id){ url = `/api/v1/analytics-tabs/${id}`; method = 'PUT'; }
  else{ url = `/api/v1/dashboards/${dashboardId}/analytics-tabs`; method = 'POST'; }
  const r = await api(url, {method, body:JSON.stringify({name, icon:'fa-chart-line'})});
  const d = await r.json();
  if(d.success){ closeModal('m-tab'); await loadTabs(); if(d.id) currentTabId = d.id; loadCharts(); }
  else alert(d.error || 'Gagal');
}
async function deleteTab(){
  const id = document.getElementById('tabId').value; if(!id) return;
  if(!confirm('Hapus tab ini beserta diagramnya?')) return;
  const r = await api(`/api/v1/analytics-tabs/${id}`, {method:'DELETE'});
  const d = await r.json();
  if(d.success){ closeModal('m-tab'); currentTabId = null; await loadTabs(); if(tabs.length) switchTab(tabs[0].id); else loadCharts(); }
  else alert(d.error || 'Gagal');
}

const toChart = t => ({line_chart:'line', bar_chart:'bar', area_chart:'area', doughnut_chart:'doughnut', pie_chart:'pie', polar_area:'polarArea', radar_chart:'radar', horizontal_bar:'horizontalBar', stacked_bar:'stackedBar', stacked_area:'stackedArea'}[t] || 'line');
const toWidget = t => ({line:'line_chart', bar:'bar_chart', area:'area_chart', doughnut:'doughnut_chart', pie:'pie_chart', polarArea:'polar_area', radar:'radar_chart', horizontalBar:'horizontal_bar', stackedBar:'stacked_bar', stackedArea:'stacked_area'}[t] || 'line_chart');

async function loadCharts(){
  const c = document.getElementById('chartsList'); if(!c) return;
  if(!currentTabId){
    document.getElementById('chartCountSub').textContent = 'Belum ada tab';
    c.innerHTML = '<div class="empty"><i class="fa-solid fa-chart-column"></i><div class="empty-title">Belum ada tab</div></div>';
    return;
  }
  c.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  try{
    const r = await api(`/api/v1/dashboards/${dashboardId}/analytics-tabs/${currentTabId}/widgets`);
    const d = await r.json();
    if(!d.success){
      c.innerHTML = '<div class="empty"><i class="fa-solid fa-triangle-exclamation"></i><div class="empty-title">Gagal memuat</div></div>';
      return;
    }
    const widgets = d.widgets || [];
    charts.forEach(ch => { if(ch.chartInstance) try{ ch.chartInstance.destroy(); }catch(e){} });
    charts = widgets.map(w => {
      const cfg = w.config || {};
      const devs = Array.isArray(cfg.devices) && cfg.devices.length ? cfg.devices : (w.device_id ? [w.device_id] : []);
      return {id:`chart_${w.id}`, widgetId:w.id, title:w.title, deviceIds:devs, chartType:toChart(w.widget_type), showData:cfg.show_data || {}, chartInstance:null};
    });
    document.getElementById('chartCountSub').textContent = `${charts.length} diagram`;
    if(!charts.length){
      c.innerHTML = '<div class="empty"><i class="fa-solid fa-chart-column"></i><div class="empty-title">Belum ada diagram</div><div class="empty-sub">Tap + untuk menambahkan</div></div>';
      return;
    }
    c.innerHTML = charts.map(ch => {
      const deviceNames = ch.deviceIds.map(id => devices.find(d => d.device_id === id)?.device_name || id).join(', ');
      const dataLabels = Object.entries(ch.showData).filter(([_,v])=>v).map(([k])=>DATA_KEYS[k]?.label).filter(Boolean).join(', ');
      return `
      <div class="chart-card" id="${ch.id}">
        <div class="chart-head">
          <div class="chart-info">
            <div class="chart-title">${esc(ch.title)}</div>
            <div class="chart-sub">${esc(deviceNames)}${dataLabels ? ' · ' + esc(dataLabels) : ''}</div>
          </div>
          <div class="chart-actions">
            <button class="chart-act" onclick="openChart('${ch.id}')"><i class="fa-solid fa-pen"></i></button>
            <button class="chart-act danger" onclick="removeChart('${ch.id}')"><i class="fa-solid fa-trash"></i></button>
          </div>
        </div>
        <div class="chart-canvas"><canvas id="${ch.id}_c"></canvas></div>
      </div>`;
    }).join('');
    await loadChartsData();
  }catch(e){ console.error(e); c.innerHTML = '<div class="empty"><div class="empty-title">Koneksi gagal</div></div>'; }
}
async function loadChartsData(){
  const devSet = new Set();
  charts.forEach(ch => ch.deviceIds.forEach(d => devSet.add(d)));
  if(!devSet.size) return;
  const hours = Math.max(1, Math.ceil(timeMinutes/60));
  const limit = Math.min(Math.max(hours*60, 500), 5000);
  const results = await Promise.all(Array.from(devSet).map(did =>
    api(`/api/v1/devices/${encodeURIComponent(did)}/history?hours=${hours}&limit=${limit}`)
      .then(r => r.json())
      .then(j => ({did, data: j.success ? (j.history || []) : []}))
      .catch(() => ({did, data: []}))
  ));
  const hist = {}; results.forEach(r => { hist[r.did] = r.data; });
  charts.forEach(ch => renderChart(ch, hist));
}
function renderChart(ch, hist){
  const canvas = document.getElementById(`${ch.id}_c`); if(!canvas) return;
  const ctx = canvas.getContext('2d');
  if(ch.chartInstance) try{ ch.chartInstance.destroy(); }catch(e){}
  const isLight = document.documentElement.getAttribute('data-theme') === 'light';
  const gridC = isLight ? 'rgba(0,0,0,.07)' : 'rgba(255,255,255,.07)';
  const labelC = isLight ? 'rgba(71,85,105,.85)' : 'rgba(173,181,194,.8)';
  const activeKeys = Object.entries(ch.showData).filter(([k,v]) => v).map(([k]) => k);

  if(['doughnut','pie','polarArea','radar'].includes(ch.chartType)){
    const labels = [], vals = [];
    ch.deviceIds.forEach(did => {
      const h = hist[did] || []; if(!h.length) return;
      const last = h[h.length - 1];
      const dn = devices.find(x => x.device_id === did)?.device_name || did;
      activeKeys.forEach(k => {
        const info = DATA_KEYS[k]; if(!info) return;
        const v = last.data?.[k];
        if(v != null){ labels.push(ch.deviceIds.length > 1 ? `${dn} — ${info.label}` : info.label); vals.push(v); }
      });
    });
    if(!vals.length) return;
    ch.chartInstance = new Chart(ctx, {
      type: ch.chartType,
      data: {labels, datasets: [{data: vals, backgroundColor: vals.map((_,i) => COLORS[i%COLORS.length] + '99'), borderColor: vals.map((_,i) => COLORS[i%COLORS.length]), borderWidth: 2}]},
      options: {responsive:true, maintainAspectRatio:false,
        plugins:{legend:{position:'bottom', labels:{color:labelC, font:{size:9, weight:'600'}, boxWidth:10, padding:6, usePointStyle:true, pointStyle:'circle'}}}}
    });
    return;
  }

  const tsSet = new Set();
  ch.deviceIds.forEach(did => (hist[did] || []).forEach(it => tsSet.add(it.timestamp)));
  if(!tsSet.size) return;
  const cutoff = Date.now() - timeMinutes*60*1000;
  const allTs = Array.from(tsSet).sort();
  const inRange = allTs.filter(ts => {
    const d = parseTs(ts); return d && d.getTime() >= cutoff;
  });
  const usedTs = (inRange.length ? inRange : allTs).slice(-200);
  const labels = usedTs.map(ts => fmtTime(ts));
  const datasets = []; let ci = 0;
  ch.deviceIds.forEach(did => {
    const h = hist[did] || []; if(!h.length) return;
    const dn = devices.find(x => x.device_id === did)?.device_name || did;
    const tsMap = {}; h.forEach(it => { tsMap[it.timestamp] = it.data || {}; });
    activeKeys.forEach(k => {
      const info = DATA_KEYS[k]; if(!info) return;
      const values = usedTs.map(ts => { const o = tsMap[ts]; return o ? (o[k] ?? null) : null; });
      if(!values.some(v => v != null)) return;
      const color = COLORS[ci % COLORS.length]; ci++;
      const isArea = ch.chartType === 'area' || ch.chartType === 'stackedArea';
      datasets.push({
        label: ch.deviceIds.length > 1 ? `${dn} — ${info.label}` : `${info.label} (${info.unit})`,
        data: values, borderColor: color, backgroundColor: isArea ? color+'30' : color+'99',
        fill: isArea, tension: .35, pointRadius: 2, pointHoverRadius: 5,
        pointBackgroundColor: color, borderWidth: 2, spanGaps: true
      });
    });
  });
  if(!datasets.length) return;
  let type = ch.chartType;
  if(type === 'area' || type === 'stackedArea') type = 'line';
  if(type === 'horizontalBar' || type === 'stackedBar') type = 'bar';
  ch.chartInstance = new Chart(ctx, {
    type,
    data: {labels, datasets},
    options: {responsive:true, maintainAspectRatio:false,
      interaction:{mode:'index', intersect:false},
      indexAxis: ch.chartType === 'horizontalBar' ? 'y' : 'x',
      plugins:{legend:{labels:{color:labelC, font:{size:9, weight:'600'}, boxWidth:10, padding:8, usePointStyle:true, pointStyle:'circle'}}},
      scales:{
        x:{grid:{color:gridC}, ticks:{color:labelC, font:{size:9}, maxTicksLimit:6}},
        y:{grid:{color:gridC}, ticks:{color:labelC, font:{size:9}}, beginAtZero:true}
      }
    }
  });
}
function resetChartsLayout(){
  // Clear any cached layout (mobile doesn't drag, but reset if API has cached pos)
  if(!currentTabId){ toast('Tidak ada tab aktif'); return; }
  if(!confirm('Reset layout diagram di tab ini?')) return;
  // Mobile layout is auto-stacked, so we just reload
  loadCharts();
  toast('Layout direset');
}

/* ===== Chart Modal ===== */
function genChartDeviceCbs(sel = []){
  const c = document.getElementById('chartDeviceCbs'); if(!c) return;
  const s = new Set(sel);
  if(!devices.length){ c.innerHTML = '<div style="padding:8px;color:var(--text-3);font-size:11px;grid-column:1/-1;">Belum ada perangkat</div>'; return; }
  c.innerHTML = devices.map(d => `<label class="cb"><input type="checkbox" class="chart-dev" data-id="${esc(d.device_id)}" ${s.has(d.device_id)?'checked':''}><span>${esc(d.device_name)}</span></label>`).join('');
}
function genChartDataCbs(sel = {}){
  const c = document.getElementById('chartDataCbs'); if(!c) return;
  c.innerHTML = Object.entries(DATA_KEYS).map(([k,i]) =>
    `<label class="cb"><input type="checkbox" class="chart-data" data-key="${k}" ${sel[k]?'checked':''}><span class="dot-color" style="background:${i.color};"></span><span>${i.label}</span></label>`
  ).join('');
}
function openChart(id){
  if(!currentTabId){ alert('Buat tab analitik dulu'); go('analytics'); return; }
  if(id){
    const ch = charts.find(c => c.id === id); if(!ch) return;
    document.getElementById('chartModalTitle').textContent = 'Edit Diagram';
    document.getElementById('editChartId').value = id;
    document.getElementById('chartTitle').value = ch.title;
    document.getElementById('chartType').value = ch.chartType;
    genChartDeviceCbs(ch.deviceIds);
    genChartDataCbs(ch.showData);
  } else {
    document.getElementById('chartModalTitle').textContent = 'Tambah Diagram';
    document.getElementById('editChartId').value = '';
    document.getElementById('chartTitle').value = '';
    document.getElementById('chartType').value = 'line';
    genChartDeviceCbs(devices[0] ? [devices[0].device_id] : []);
    genChartDataCbs({temperature:true});
  }
  openModal('m-chart');
}
async function saveChart(){
  const editId = document.getElementById('editChartId').value;
  const title = document.getElementById('chartTitle').value.trim() || 'Diagram';
  const chartType = document.getElementById('chartType').value;
  const deviceIds = []; document.querySelectorAll('.chart-dev:checked').forEach(cb => deviceIds.push(cb.dataset.id));
  const showData = {}; document.querySelectorAll('.chart-data').forEach(cb => { showData[cb.dataset.key] = cb.checked; });
  if(!deviceIds.length){ alert('Pilih minimal 1 perangkat'); return; }
  if(!Object.values(showData).some(v => v)){ alert('Pilih minimal 1 jenis data'); return; }
  const wt = toWidget(chartType);
  const config = {show_data: showData, devices: deviceIds};
  let url, method;
  if(editId){ const ch = charts.find(c => c.id === editId); if(!ch) return; url = `/api/v1/widgets/${ch.widgetId}`; method = 'PUT'; }
  else{ url = `/api/v1/dashboards/${dashboardId}/widgets`; method = 'POST'; }
  const body = {title, device_id: deviceIds[0], widget_type: wt, config};
  if(!editId) Object.assign(body, {grid_x:0, grid_y:0, grid_w:6, grid_h:2, analytics_tab_id:currentTabId});
  const r = await api(url, {method, body:JSON.stringify(body)});
  const d = await r.json();
  if(d.success){ closeModal('m-chart'); loadCharts(); toast(editId ? 'Diagram diupdate' : 'Diagram ditambahkan'); }
  else alert(d.error || 'Gagal');
}
async function removeChart(id){
  const ch = charts.find(c => c.id === id); if(!ch) return;
  if(!confirm(`Hapus diagram "${ch.title}"?`)) return;
  await api(`/api/v1/widgets/${ch.widgetId}`, {method:'DELETE'});
  loadCharts();
}

/* ===== Attendance ===== */
function setAttendView(v){
  attendanceView = v;
  document.querySelectorAll('.attend-tab').forEach(t => t.classList.toggle('active', t.dataset.t === v));
  loadAttend();
}
async function loadAttend(){
  const c = document.getElementById('attendList'); if(!c) return;
  c.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  try{
    const sr = await api('/api/v1/attendance/stats');
    const sd = await sr.json();
    if(sd.success){
      document.getElementById('sHadir').textContent = sd.stats.hadir_hari_ini || 0;
      document.getElementById('sKartu').textContent = sd.stats.total_kartu_aktif || 0;
      document.getElementById('sUnknown').textContent = sd.stats.kartu_belum_terdaftar || 0;
      document.getElementById('attendSub').textContent = `${sd.stats.hadir_hari_ini || 0} hadir hari ini`;
    }
  }catch(e){}

  const start = document.getElementById('dateStart').value, end = document.getElementById('dateEnd').value;
  try{
    if(attendanceView === 'report'){
      const params = new URLSearchParams(); if(start) params.set('start', start); if(end) params.set('end', end);
      const r = await api(`/api/v1/attendance/report?${params}`);
      const d = await r.json();
      const rows = d.success ? (d.report || []) : [];
      if(!rows.length){ c.innerHTML = '<div class="empty"><i class="fa-solid fa-clipboard-list"></i><div class="empty-title">Belum ada laporan</div></div>'; return; }
      c.innerHTML = rows.map(r => {
      const cleanTime = (s) => s ? String(s).split(' ')[1]?.split('.')[0] || '-' : '-';
      const ci = cleanTime(r.check_in);
      const co = (r.check_out && r.check_out !== r.check_in) ? cleanTime(r.check_out) : '-';
        let duration = '-';
        if(r.check_in && r.check_out && r.check_in !== r.check_out){
          try{
            const t1 = new Date(r.check_in.replace(' ','T')+'+07:00').getTime();
            const t2 = new Date(r.check_out.replace(' ','T')+'+07:00').getTime();
            const mins = Math.floor((t2-t1)/60000);
            if(mins > 0){
              const h = Math.floor(mins/60);
              const m = mins % 60;
              duration = h > 0 ? `${h}j ${m}m` : `${m}m`;
            }
          }catch(e){}
        }
        return `<div class="attend-item">
          <div class="attend-head">
            <div class="attend-name">${esc(r.nama)}</div>
            <div class="attend-time">${esc(r.day)}</div>
          </div>
          <div class="attend-uid">${esc(r.uid)}</div>
          <div class="attend-grid">
            <div><div class="attend-cell-label">Masuk</div><div class="attend-cell-val ok">${ci}</div></div>
            <div><div class="attend-cell-label">Keluar</div><div class="attend-cell-val warn">${co}</div></div>
            <div><div class="attend-cell-label">Durasi</div><div class="attend-cell-val mute">${duration}</div></div>
          </div>
        </div>`;
      }).join('');
    } else {
      const r = await api('/api/v1/attendance?limit=200');
      const d = await r.json();
      let rows = d.success ? (d.attendance || []) : [];
      if(start || end){
        const st = start ? new Date(start+'T00:00:00+07:00').getTime() : 0;
        const en = end ? new Date(end+'T23:59:59+07:00').getTime() : Infinity;
        rows = rows.filter(x => {
          const t = new Date(String(x.timestamp).replace(' ','T')+'+07:00').getTime();
          return t >= st && t <= en;
        });
      }
      if(!rows.length){ c.innerHTML = '<div class="empty"><i class="fa-solid fa-id-card"></i><div class="empty-title">Belum ada aktivitas</div></div>'; return; }
      c.innerHTML = rows.map(r => {
        const dt = fmtDateSplit(r.timestamp);
        return `<div class="attend-item">
          <div class="attend-head">
            <div class="attend-name">${esc(r.nama)}</div>
            <div class="attend-time">${dt.date} ${dt.time}</div>
          </div>
          <div class="attend-grid" style="grid-template-columns:1fr 1fr;">
            <div><div class="attend-cell-label">UID</div><div class="attend-cell-val">${esc(r.uid)}</div></div>
            <div><div class="attend-cell-label">Device</div><div class="attend-cell-val">${esc(r.device_id)}</div></div>
          </div>
        </div>`;
      }).join('');
    }
  }catch(e){ c.innerHTML = '<div class="empty"><div class="empty-title">Gagal memuat</div></div>'; }
}
function exportAttend(){
  const start = document.getElementById('dateStart').value, end = document.getElementById('dateEnd').value;
  const params = new URLSearchParams(); if(start) params.set('start', start); if(end) params.set('end', end);
  window.location.href = '/api/v1/attendance/export?' + params.toString();
}
async function captureLastTap(){
  const r = await api('/api/v1/attendance/last-unknown');
  const d = await r.json();
  if(d.success && d.uid) document.getElementById('cardUid').value = d.uid;
  else alert('Belum ada kartu asing');
}
function openCardholder(){
  document.getElementById('cardUid').value = '';
  document.getElementById('cardNama').value = '';
  openModal('m-card');
}
async function submitCardholder(){
  const uid = document.getElementById('cardUid').value.trim();
  const nama = document.getElementById('cardNama').value.trim();
  if(!uid || !nama){ alert('UID dan Nama wajib diisi'); return; }
  const r = await api('/api/v1/cardholders', {method:'POST', body:JSON.stringify({uid, nama})});
  const d = await r.json();
  if(d.success){ closeModal('m-card'); loadAttend(); toast('Kartu terdaftar'); }
  else alert(d.error || 'Gagal');
}
async function openStatDetail(type){
  const title = document.getElementById('statTitle');
  const body = document.getElementById('statBody');
  body.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  openModal('m-stat');
  try{
    if(type === 'hadir'){
      title.textContent = 'Hadir Hari Ini';
      const r = await api('/api/v1/attendance/today');
      const d = await r.json();
      const rows = d.success ? (d.hadir || []) : [];
      if(!rows.length){ body.innerHTML = '<div class="empty"><div class="empty-title">Belum ada tap</div></div>'; return; }
      body.innerHTML = rows.map(x => `<div class="attend-item" style="padding:12px 0;">
        <div class="attend-head"><div class="attend-name">${esc(x.nama)}</div><div class="attend-time">${fmtDateSplit(x.pertama_tap).time}</div></div>
        <div class="attend-uid">${esc(x.uid)}</div>
      </div>`).join('');
    } else if(type === 'total'){
      title.textContent = 'Total Kartu Aktif';
      const r = await api('/api/v1/cardholders');
      const d = await r.json();
      const rows = d.success ? (d.cardholders || []) : [];
      if(!rows.length){ body.innerHTML = '<div class="empty"><div class="empty-title">Belum ada kartu</div></div>'; return; }
      body.innerHTML = rows.map(x => `<div class="attend-item" style="padding:12px 0;">
        <div class="attend-head">
          <div class="attend-name">${esc(x.nama)}</div>
          <button class="chart-act danger" onclick="deleteCardholder('${esc(x.uid)}')"><i class="fa-solid fa-trash"></i></button>
        </div>
        <div class="attend-uid">${esc(x.uid)}</div>
      </div>`).join('');
    } else {
      title.textContent = 'Kartu Belum Terdaftar';
      const r = await api('/api/v1/attendance/unregistered');
      const d = await r.json();
      const rows = d.success ? (d.kartu || []) : [];
      if(!rows.length){ body.innerHTML = '<div class="empty"><div class="empty-title">Semua kartu terdaftar</div></div>'; return; }
      body.innerHTML = rows.map(x => {
        const dt = fmtDateSplit(x.terakhir_tap);
        return `<div class="attend-item" style="padding:12px 0;">
          <div class="attend-head">
            <div class="attend-name mono" style="font-family:var(--mono);font-size:13px;">${esc(x.uid)}</div>
            <button class="btn-soft" style="flex-shrink:0;padding:6px 12px;font-size:11.5px;min-height:32px;" onclick="closeModal('m-stat');openCardholder();setTimeout(()=>{document.getElementById('cardUid').value='${esc(x.uid)}';},150)">Daftar</button>
          </div>
          <div class="attend-time" style="text-align:left;">${dt.date} ${dt.time}</div>
        </div>`;
      }).join('');
    }
  }catch(e){ body.innerHTML = '<div class="empty"><div class="empty-title">Gagal memuat</div></div>'; }
}
async function deleteCardholder(uid){
  if(!confirm('Hapus kartu ini?')) return;
  await api(`/api/v1/cardholders/${encodeURIComponent(uid)}`, {method:'DELETE'});
  openStatDetail('total');
}

/* ===== Alerts ===== */
let __alertDDsBound = false;
function bindAlertDropdowns() {
  if (__alertDDsBound) return;
  __alertDDsBound = true;

  bindIosDD('alertStatusDD', (val) => {
    alertStatus = val || 'all';
    loadAlerts();
  });
  bindIosDD('alertSevDD', (val) => {
    alertSev = val || '';
    loadAlerts();
  });
}
bindAlertDropdowns();

document.getElementById('alertSearch').addEventListener('input', e => {
  clearTimeout(window.__aST);
  window.__aST = setTimeout(() => { alertSearch = e.target.value.trim(); renderAlerts(); }, 200);
});

async function loadAlerts(){
  const c = document.getElementById('alertsList'); if(!c) return;
  try{
    const sr = await api('/api/v1/alerts/stats');
    const sd = await sr.json();
    if(sd.success){
      document.getElementById('aTotal').textContent = sd.summary.total;
      document.getElementById('aDanger').textContent = sd.summary.danger;
      document.getElementById('aWarning').textContent = sd.summary.warning;
      document.getElementById('aInfo').textContent = sd.summary.info;
      document.getElementById('alertSub').textContent = `${sd.summary.total} alert aktif`;
    }
    const params = new URLSearchParams();
    if(alertStatus !== 'all') params.set('status', alertStatus);
    if(alertSev) params.set('severity', alertSev);
    params.set('limit', '1000');
    const r = await api(`/api/v1/alerts/all?${params}`);
    const d = await r.json();
    alerts = d.success ? (d.alerts || []) : [];
    // Prune selection
    const validIds = new Set(alerts.filter(a => a.is_still_active === 1 && a.severity !== 'healthy').map(ackIdOf).filter(x=>x!=null));
    Array.from(alertSelectedIds).forEach(id => { if(!validIds.has(id)) alertSelectedIds.delete(id); });
    renderAlerts();
  }catch(e){ c.innerHTML = '<div class="empty"><div class="empty-title">Koneksi gagal</div></div>'; }
}

function inAlertDateRange(iso){
  if(!alertDateStart && !alertDateEnd) return true;
  const d = parseTs(iso); if(!d) return true;
  const t = d.getTime();
  if(alertDateStart){
    const st = new Date(alertDateStart+'T00:00:00+07:00').getTime();
    if(t < st) return false;
  }
  if(alertDateEnd){
    const en = new Date(alertDateEnd+'T23:59:59+07:00').getTime();
    if(t > en) return false;
  }
  return true;
}

function applyAlertDateFilter(){
  alertDateStart = document.getElementById('alertDateStart').value;
  alertDateEnd = document.getElementById('alertDateEnd').value;
  renderAlerts();
}
function resetAlertDateFilter(){
  document.getElementById('alertDateStart').value = '';
  document.getElementById('alertDateEnd').value = '';
  alertDateStart = '';
  alertDateEnd = '';
  renderAlerts();
}

function getFilteredAlerts(){
  let list = alerts.slice();
  // Date
  list = list.filter(a => inAlertDateRange(a.created_at));
  // Search
  if(alertSearch){
    const t = alertSearch.toLowerCase();
    list = list.filter(a =>
      (a.device_name||'').toLowerCase().includes(t) ||
      (a.device_id||'').toLowerCase().includes(t) ||
      (a.message||'').toLowerCase().includes(t) ||
      (a.alert_type||'').toLowerCase().includes(t) ||
      (a.label||'').toLowerCase().includes(t));
  }
  return list;
}

function renderAlerts(){
  const c = document.getElementById('alertsList'); if(!c) return;
  const list = getFilteredAlerts();

  if(!list.length){
    c.innerHTML = '<div class="empty"><i class="fa-solid fa-bell-slash"></i><div class="empty-title">Tidak ada alert</div></div>';
    updateAlertBulkBar();
    return;
  }

  // Group by date
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);
  const weekAgo = new Date(today.getTime() - 7*86400000);

  let html = '';
  let currentGroup = '', groupOpen = false;

  list.forEach(a => {
    const d = parseTs(a.created_at);
    let group;
    if(!d) group = 'Tidak Diketahui';
    else if(d >= today) group = 'Hari Ini';
    else if(d >= yesterday) group = 'Kemarin';
    else if(d >= weekAgo) group = '7 Hari Terakhir';
    else group = 'Lebih Lama';

    if(group !== currentGroup){
      if(groupOpen) html += '</div>';
      html += `<div class="alert-group"><div class="alert-group-label">${group}</div>`;
      currentGroup = group;
      groupOpen = true;
    }
    html += renderAlertRow(a);
  });
  if(groupOpen) html += '</div>';

  c.innerHTML = html;
  bindAlertRowEvents();
  updateAlertBulkBar();
}

function renderAlertRow(a){
  const active = a.is_still_active === 1;
  const sev = a.severity || 'info';
  const healthy = sev === 'healthy';
  const cls = healthy ? 'resolved' : (active ? sev : 'resolved');
  const id = ackIdOf(a);
  const canAck = active && !healthy && id != null;
  const isChecked = id != null && alertSelectedIds.has(id);
  const valueDisplay = formatVal(a.alert_type, a.value);
  const typeLabel = a.label || alertTypeLabel(a.alert_type);

  const checkHtml = canAck
    ? `<label class="alert-check" onclick="event.stopPropagation();">
         <input type="checkbox" class="alert-cb" data-alert-id="${id}" ${isChecked?'checked':''}>
       </label>`
    : `<div class="alert-check hidden"></div>`;

  return `<div class="alert-item ${cls}" data-alert-id="${a.id}" data-device-id="${esc(a.device_id)}">
    ${checkHtml}
    <div class="alert-body">
      <div class="alert-head">
        <span class="alert-sev ${sev}">${sev}</span>
        <span class="alert-head-type">${esc(a.alert_type || '')}</span>
        ${valueDisplay ? `<span class="alert-val">${esc(valueDisplay)}</span>` : ''}
      </div>
      <div class="alert-title">${esc(typeLabel)}</div>
      <div class="alert-msg">${esc(a.message || '-')}</div>
      <div class="alert-meta">
        <span><i class="fa-solid fa-microchip"></i> ${esc(a.device_name || a.device_id)}</span>
        <span class="dot"></span>
        <span>${fmtRelative(a.created_at)}</span>
      </div>
      ${(active || canAck) ? `<div class="alert-actions">
        <button class="alert-act-btn" data-action="view-device" data-device-id="${esc(a.device_id)}">
          <i class="fa-solid fa-eye"></i> Detail
        </button>
        ${canAck ? `<button class="alert-act-btn ok" data-action="acknowledge" data-alert-id="${id}">
          <i class="fa-solid fa-check"></i> Tandai
        </button>` : ''}
      </div>` : ''}
    </div>
  </div>`;
}

function bindAlertRowEvents(){
  document.querySelectorAll('.alert-item [data-action="view-device"]').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      openDevice(btn.dataset.deviceId);
    });
  });
  document.querySelectorAll('.alert-item [data-action="acknowledge"]').forEach(btn => {
    btn.addEventListener('click', async e => {
      e.stopPropagation();
      const id = parseInt(btn.dataset.alertId, 10);
      if(!Number.isFinite(id)) return;
      const ok = await ackAlert(id);
      if(ok){ loadAlerts(); toast('Alert ditandai selesai'); }
      else alert('Gagal');
    });
  });
  document.querySelectorAll('.alert-cb').forEach(cb => {
    cb.addEventListener('change', e => {
      const id = parseInt(e.target.dataset.alertId, 10);
      if(!Number.isFinite(id)) return;
      if(e.target.checked) alertSelectedIds.add(id);
      else alertSelectedIds.delete(id);
      updateAlertBulkBar();
    });
  });
  // Click row to open device
  document.querySelectorAll('.alert-item').forEach(item => {
    item.addEventListener('click', e => {
      if(e.target.closest('button') || e.target.closest('label') || e.target.closest('input')) return;
      const id = item.dataset.deviceId;
      if(id) openDevice(id);
    });
  });
}

function updateAlertBulkBar(){
  const bar = document.getElementById('alertBulkBar');
  if(!bar) return;
  const activeVisible = getFilteredAlerts().filter(a =>
    a.is_still_active === 1 && a.severity !== 'healthy' && ackIdOf(a) != null);
  if(activeVisible.length === 0){
    bar.style.display = 'none';
    return;
  }
  bar.style.display = 'flex';
  document.getElementById('alertSelectedCount').textContent = `${alertSelectedIds.size} dipilih`;
  const selAll = document.getElementById('alertSelectAll');
  const allIds = activeVisible.map(ackIdOf);
  selAll.checked = allIds.length > 0 && allIds.every(id => alertSelectedIds.has(id));
}

document.getElementById('alertSelectAll').addEventListener('change', e => {
  const activeVisible = getFilteredAlerts().filter(a =>
    a.is_still_active === 1 && a.severity !== 'healthy' && ackIdOf(a) != null);
  if(e.target.checked){
    activeVisible.forEach(a => alertSelectedIds.add(ackIdOf(a)));
  } else {
    alertSelectedIds.clear();
  }
  renderAlerts();
});

async function bulkAckAlerts(){
  if(alertSelectedIds.size === 0){ toast('Pilih minimal satu alert'); return; }
  if(!confirm(`Tandai ${alertSelectedIds.size} alert sebagai selesai?`)) return;
  const ids = Array.from(alertSelectedIds);
  try{
    const r = await api('/api/v1/alerts/bulk-acknowledge', {
      method:'POST',
      body:JSON.stringify({ids})
    });
    const d = await r.json();
    if(d.success){
      toast(`${d.acknowledged || ids.length} alert ditandai selesai`);
      alertSelectedIds.clear();
      loadAlerts();
    } else alert(d.error || 'Gagal');
  }catch(e){ alert('Koneksi gagal'); }
}

async function markAllVisibleAlerts(){
  const visible = getFilteredAlerts().filter(a =>
    a.is_still_active === 1 && a.severity !== 'healthy' && ackIdOf(a) != null);
  if(!visible.length){ toast('Tidak ada alert aktif di filter ini'); return; }
  if(!confirm(`Tandai ${visible.length} alert sebagai selesai?`)) return;
  const ids = visible.map(ackIdOf);
  try{
    const r = await api('/api/v1/alerts/bulk-acknowledge', {
      method:'POST',
      body:JSON.stringify({ids})
    });
    const d = await r.json();
    if(d.success){ toast(`${d.acknowledged || ids.length} alert ditandai selesai`); loadAlerts(); }
    else alert(d.error || 'Gagal');
  }catch(e){ alert('Koneksi gagal'); }
}

async function ackAlert(id){
  try{
    const r = await api(`/api/v1/alerts/${id}/acknowledge`, {method:'POST'});
    const d = await r.json();
    return d.success === true;
  }catch(e){ return false; }
}

/* ===== Device CRUD ===== */
function openAddDevice(){
  document.getElementById('addId').value = '';
  document.getElementById('addName').value = '';
  document.getElementById('addLocation').value = '';
  document.getElementById('addInterval').value = '60';
  document.getElementById('addTimeout').value = '';
  document.getElementById('addRules').innerHTML = '<div class="rule-empty">Belum ada custom rule</div>';
  openModal('m-add');
}
async function submitAddDevice(){
  const id = document.getElementById('addId').value.trim();
  const name = document.getElementById('addName').value.trim();
  if(!id || !name){ alert('ID dan Nama wajib diisi'); return; }
  const payload = {
    device_id: id, device_name: name,
    device_type: document.getElementById('addType').value,
    location: document.getElementById('addLocation').value,
    expected_interval: parseInt(document.getElementById('addInterval').value) || 60,
  };
  const to = document.getElementById('addTimeout').value;
  if(to) payload.offline_timeout = parseInt(to);
  const rules = collectRules('add'); if(rules) payload.alert_rules = rules;
  try{
    const r = await api('/api/v1/devices', {method:'POST', body:JSON.stringify(payload)});
    const d = await r.json();
    if(d.success){
      closeModal('m-add');
      document.getElementById('apiKeyValue').textContent = d.device.api_key;
      pendingRedirect = d.device.device_id;
      openModal('m-apikey');
      loadDashboard();
    } else {
      const msg = typeof d.error === 'object' ? Object.values(d.error).flat().join(', ') : d.error;
      alert(msg || 'Gagal');
    }
  }catch(e){ alert('Error: ' + e.message); }
}
function copyApiKey(){
  const k = document.getElementById('apiKeyValue').textContent;
  if(navigator.clipboard) navigator.clipboard.writeText(k).then(() => toast('API Key disalin'));
  else alert('Copy manual: ' + k);
}
function closeApiKeyModal(){
  closeModal('m-apikey');
  if(pendingRedirect){
    const id = pendingRedirect; pendingRedirect = null;
    setTimeout(() => openDevice(id), 200);
  }
}
async function openSheet(id){
  const d = devices.find(x => x.device_id === id); if(!d) return;
  sheetDeviceId = id;
  document.getElementById('sheetTitle').textContent = d.device_name;
  openModal('m-sheet');
}
function sheetAction(action){
  const id = sheetDeviceId;
  closeModal('m-sheet');
  if(!id) return;
  setTimeout(() => {
    if(action === 'detail') openDevice(id);
    else if(action === 'config') openEditConfig(id);
    else if(action === 'key') regenKey(id);
    else if(action === 'delete') openDelete(id);
  }, 180);
}
async function regenKey(id){
  if(!confirm(`Regenerate API Key untuk "${id}"?\n\nKey lama tidak akan berfungsi lagi.`)) return;
  const r = await api(`/api/v1/devices/${encodeURIComponent(id)}/regenerate-key`, {method:'POST'});
  const d = await r.json();
  if(d.success){
    document.getElementById('apiKeyValue').textContent = d.api_key;
    pendingRedirect = null;
    openModal('m-apikey');
    loadDashboard();
  } else alert(d.error || 'Gagal');
}
async function openEditConfig(id){
  try{
    const r = await api(`/api/v1/devices/${encodeURIComponent(id)}`);
    const d = await r.json();
    if(!d.success){ alert('Gagal memuat'); return; }
    const dev = d.device;
    document.getElementById('editId').value = id;
    document.getElementById('editInterval').value = dev.expected_interval || 60;
    document.getElementById('editTimeout').value = dev.offline_timeout || 900;
    populateRules('edit', dev.alert_rules);
    openModal('m-edit');
  }catch(e){ alert('Error: ' + e.message); }
}
async function submitEditConfig(){
  const id = document.getElementById('editId').value; if(!id) return;
  const rules = collectRules('edit');
  const payload = {
    expected_interval: parseInt(document.getElementById('editInterval').value) || 60,
    offline_timeout: parseInt(document.getElementById('editTimeout').value) || 900,
    alert_rules: rules,
  };
  const r = await api(`/api/v1/devices/${encodeURIComponent(id)}`, {method:'PUT', body:JSON.stringify(payload)});
  const d = await r.json();
  if(d.success){ closeModal('m-edit'); loadDashboard(); toast('Tersimpan'); }
  else alert(d.error || 'Gagal');
}

/* ===== Delete ===== */
let delTarget = null;
function openDelete(id){
  const d = devices.find(x => x.device_id === id);
  const name = d ? d.device_name : id;
  delTarget = id;
  document.getElementById('deleteTitle').textContent = 'Hapus Perangkat';
  document.getElementById('deleteText').textContent = `Perangkat "${name}" akan dihapus permanen. Tindakan ini tidak bisa dibatalkan.`;
  document.getElementById('deleteLabel').innerHTML = `Ketik <span class="mono" style="color:var(--text);background:var(--surface-2);padding:3px 8px;border-radius:6px;">${esc(id)}</span> untuk konfirmasi`;
  document.getElementById('deleteInput').value = '';
  document.getElementById('deleteInput').placeholder = `Ketik ${id}...`;
  document.getElementById('deleteConfirm').disabled = true;
  openModal('m-delete');
}
document.getElementById('deleteInput').addEventListener('input', e => {
  document.getElementById('deleteConfirm').disabled = e.target.value.trim() !== (delTarget || '');
});
async function confirmDelete(){
  if(!delTarget) return;
  const input = document.getElementById('deleteInput').value.trim();
  if(input !== delTarget){ alert('Konfirmasi salah'); return; }
  const r = await api(`/api/v1/devices/${encodeURIComponent(delTarget)}`, {method:'DELETE'});
  const d = await r.json();
  if(d.success){ closeModal('m-delete'); delTarget = null; loadDashboard(); toast('Perangkat dihapus'); }
  else alert(d.error || 'Gagal');
}

/* ===== Alert Rules Builder ===== */
function addRule(mode){
  const c = document.getElementById(mode === 'add' ? 'addRules' : 'editRules'); if(!c) return;
  const empty = c.querySelector('.rule-empty'); if(empty) empty.remove();
  const used = Array.from(c.querySelectorAll('.rule-select')).map(s => s.value);
  const avail = Object.keys(PRESETS).find(k => !used.includes(k)) || Object.keys(PRESETS)[0];
  const p = PRESETS[avail];
  const item = document.createElement('div');
  item.className = 'rule';
  item.innerHTML = `
    <div class="rule-head">
      <select class="rule-select">${Object.entries(PRESETS).map(([k,v]) => `<option value="${k}" ${k===avail?'selected':''}>${v.label}</option>`).join('')}</select>
      <button class="rule-remove" onclick="this.closest('.rule').remove();checkRulesEmpty('${mode}')"><i class="fa-solid fa-xmark"></i></button>
    </div>
    ${sevRow('healthy', p.defaults.healthy)}
    ${sevRow('warning', p.defaults.warning)}
    ${sevRow('danger', p.defaults.danger)}
  `;
  c.appendChild(item);
  item.querySelector('.rule-select').addEventListener('change', function(){
    const pr = PRESETS[this.value];
    item.querySelectorAll('.rule-sev').forEach(row => {
      const sev = Array.from(row.classList).find(x => ['healthy','warning','danger'].includes(x));
      if(sev && pr.defaults[sev]){
        row.querySelector('[data-field="min"]').value = pr.defaults[sev].min;
        row.querySelector('[data-field="max"]').value = pr.defaults[sev].max;
      }
    });
  });
}
const sevRow = (sev, v) => `<div class="rule-sev ${sev}">
  <div class="rule-sev-label"><span class="dot"></span>${sev === 'healthy' ? 'Normal' : sev === 'warning' ? 'Warning' : 'Bahaya'}</div>
  <input type="number" step="0.1" data-field="min" value="${v.min}">
  <input type="number" step="0.1" data-field="max" value="${v.max}">
</div>`;
function checkRulesEmpty(mode){
  const c = document.getElementById(mode === 'add' ? 'addRules' : 'editRules');
  if(c && !c.querySelector('.rule')) c.innerHTML = '<div class="rule-empty">Belum ada custom rule</div>';
}
function collectRules(mode){
  const c = document.getElementById(mode === 'add' ? 'addRules' : 'editRules'); if(!c) return null;
  const rules = {};
  c.querySelectorAll('.rule').forEach(item => {
    const key = item.querySelector('.rule-select').value;
    const rule = {};
    item.querySelectorAll('.rule-sev').forEach(row => {
      const sev = Array.from(row.classList).find(x => ['healthy','warning','danger'].includes(x));
      if(!sev) return;
      const mn = parseFloat(row.querySelector('[data-field="min"]').value);
      const mx = parseFloat(row.querySelector('[data-field="max"]').value);
      if(!isNaN(mn) && !isNaN(mx)) rule[sev] = {min:mn, max:mx};
    });
    if(Object.keys(rule).length) rules[key] = rule;
  });
  return Object.keys(rules).length ? rules : null;
}
function populateRules(mode, rules){
  const c = document.getElementById(mode === 'add' ? 'addRules' : 'editRules'); if(!c) return;
  c.innerHTML = '';
  if(!rules || !Object.keys(rules).length){
    c.innerHTML = '<div class="rule-empty">Belum ada custom rule</div>'; return;
  }
  Object.entries(rules).forEach(([key, rule]) => {
    const item = document.createElement('div');
    item.className = 'rule';
    item.innerHTML = `
      <div class="rule-head">
        <select class="rule-select">${Object.entries(PRESETS).map(([k,v]) => `<option value="${k}" ${k===key?'selected':''}>${v.label}</option>`).join('')}</select>
        <button class="rule-remove" onclick="this.closest('.rule').remove();checkRulesEmpty('${mode}')"><i class="fa-solid fa-xmark"></i></button>
      </div>
      ${rule.healthy ? sevRow('healthy', rule.healthy) : ''}
      ${rule.warning ? sevRow('warning', rule.warning) : ''}
      ${rule.danger ? sevRow('danger', rule.danger) : ''}
    `;
    c.appendChild(item);
  });
}

/* ===== Init ===== */
loadDashboard();
setInterval(loadDashboard, 30000);
setInterval(() => { if(document.getElementById('s-dashboard').classList.contains('active')) loadActivity(); }, 60000);
setInterval(() => { if(document.getElementById('s-alerts').classList.contains('active')) loadAlerts(); }, 20000);
setInterval(() => { if(document.getElementById('s-attendance').classList.contains('active')) loadAttend(); }, 15000);
