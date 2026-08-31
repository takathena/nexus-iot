## NEXUS IoT - Universal IoT Monitoring Platform

**Versi:** 2.0
**Tanggal:** 31 Agustus 2026
**Status:** Production Ready

---

## 1. Executive Summary

NEXUS IoT adalah platform monitoring Internet of Things (IoT) universal yang memungkinkan pengguna untuk mengelola, memantau, dan menganalisis data dari berbagai perangkat IoT dalam satu dashboard terpusat. Platform ini dirancang untuk mendukung perangkat ESP32, ESP8266, Arduino, dan Raspberry Pi dengan antarmuka web responsif yang dapat diakses dari desktop maupun mobile.

**Nilai Utama:**
- **Universal Compatibility** — Menerima data dari berbagai jenis perangkat IoT
- **Real-time Monitoring** — Dashboard live dengan update otomatis setiap 30 detik
- **Interactive Mapping** — Visualisasi lokasi perangkat dengan Leaflet.js
- **Advanced Analytics** — Multi-chart untuk analisis data sensor historis
- **Easy Device Management** — Manajemen perangkat dengan API key per device
- **Responsive Design** — Optimasi untuk desktop dan mobile/tablet

---

## 2. Product Overview

### 2.1 Vision
Menjadi platform monitoring IoT yang universal, mudah digunakan, dan scalable untuk berbagai kebutuhan monitoring dari skala kecil hingga enterprise.

### 2.2 Mission
- Menyediakan platform open-source untuk monitoring IoT
- Memudahkan integrasi berbagai jenis perangkat IoT
- Memberikan visualisasi data yang intuitif dan informatif
- Memastikan keamanan data dengan autentikasi dan API key

### 2.3 Target Users
| Segmen | Deskripsi |
|--------|-----------|
| **IoT Enthusiast/Hobbyist** | Pengguna individu yang ingin memonitor perangkat IoT di rumah |
| **SME/UKM** | Usaha kecil menengah yang membutuhkan monitoring lingkungan |
| **Agriculture/Farming** | Pemantauan suhu, kelembaban untuk pertanian/peternakan |
| **Smart Building** | Monitoring lingkungan gedung, ruangan, atau server room |
| **Education** | Laboratorium dan proyek penelitian IoT |
| **Enterprise** | Monitoring perangkat IoT dalam skala besar |

---

## 3. System Architecture

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│   ESP32/ESP8266/Arduino           ┌─────────────────────────────────┐  │
│   ┌────────────────────────┐      │   NEXUS IoT Server (Flask)     │  │
│   │   DHT22 Sensor         │      │                                 │  │
│   │   ├── Temperature      │──┐   │   ┌─────────────────────────┐ │  │
│   │   └── Humidity         │  │   │   │   API v1 Endpoints      │ │  │
│   │                        │  │   │   │   POST /api/v1/data     │ │  │
│   │   WiFi Module          │  │   │   │   GET  /api/v1/devices  │ │  │
│   │   ├── Connect WiFi     │  │   │   │   GET  /api/v1/dashboard│ │  │
│   │   └── HTTP POST        │──┼──►│   └─────────────────────────┘ │  │
│   │                        │  │   │                                 │  │
│   │   NTP Sync             │  │   │   ┌─────────────────────────┐ │  │
│   └────────────────────────┘  │   │   │   Background Checker    │ │  │
│                               │   │   │   ├── Status monitoring │ │  │
│   ┌────────────────────────┐  │   │   │   └── Timeout detection│ │  │
│   │   Alternative Sensors  │  │   │   └─────────────────────────┘ │  │
│   │   ├── DHT11            │  │   │                                 │  │
│   │   ├── BME280           │  │   │   ┌─────────────────────────┐ │  │
│   │   ├── MQ-2 (Gas)       │  │   │   │   Database (SQLite)     │ │  │
│   │   └── Custom Sensors   │──┘   │   │   ├── devices           │ │  │
│   └────────────────────────┘      │   │   ├── sensor_data       │ │  │
│                                    │   │   └── alerts            │ │  │
│                                    │   └─────────────────────────┘ │  │
│                                    │                                 │  │
│                                    │   ┌─────────────────────────┐ │  │
│                                    │   │   Web Interface         │ │  │
│                                    │   │   ├── Dashboard (desktop│ │  │
│                                    │   │   ├── Mobile (mobile)   │ │  │
│                                    │   │   └── Device Detail     │ │  │
│                                    │   └─────────────────────────┘ │  │
│                                    │                                 │  │
│                                    │   ┌─────────────────────────┐ │  │
│                                    │   │   External Services     │ │  │
│                                    │   │   ├── Leaflet.js (Map) │ │  │
│                                    │   │   └── Chart.js (Graphs)│ │  │
│                                    │   └─────────────────────────┘ │  │
│                                    └─────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| **Backend** | Python Flask | 3.1.3 |
| **Database** | SQLite | 3.x |
| **Frontend** | HTML5, CSS3, Vanilla JS | — |
| **Charts** | Chart.js | 4.4.0 |
| **Maps** | Leaflet.js | 1.9.4 |
| **Icons** | Font Awesome | 6.5.1 |
| **Fonts** | Google Fonts (Inter, JetBrains Mono) | — |
| **ESP32 Firmware** | MicroPython | — |
| **Web Server** | Flask Development Server | — |

### 3.3 Data Flow

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   ESP32     │────▶│  /api/v1/data   │────▶│  Database       │
│  (Device)   │     │  (POST)         │     │  - sensor_data  │
└─────────────┘     └──────────────────┘     └─────────────────┘
                            │                         │
                            ▼                         ▼
                    ┌──────────────────┐     ┌─────────────────┐
                    │  Update Device   │     │  Web Dashboard  │
                    │  Status → Online │     │  (fetch /api/v1)│
                    └──────────────────┘     └─────────────────┘
                                                     │
                                                     ▼
                    ┌──────────────────┐     ┌─────────────────┐
                    │ Background       │     │  Chart.js       │
                    │ Checker (60s)    │     │  Visualizations │
                    │  Offline if >15m │     └─────────────────┘
                    └──────────────────┘
```

---

## 4. Functional Requirements

### 4.1 Authentication & Security

| ID | Requirement | Priority |
|----|-------------|----------|
| **AUTH-01** | Login dengan username dan password dari environment variable | P0 |
| **AUTH-02** | Session management dengan Flask session | P0 |
| **AUTH-03** | Auto-redirect ke login jika session tidak valid | P0 |
| **AUTH-04** | Logout menghapus session | P0 |
| **AUTH-05** | Setiap perangkat memiliki API key unik (32 hex) | P0 |
| **AUTH-06** | Validasi API key pada setiap request data | P0 |
| **AUTH-07** | CORS support untuk akses lintas origin | P1 |

### 4.2 Device Management

| ID | Requirement | Priority |
|----|-------------|----------|
| **DVC-01** | Tambah perangkat baru dengan device_id dan name | P0 |
| **DVC-02** | Generate API key otomatis saat device ditambahkan | P0 |
| **DVC-03** | Lihat daftar semua perangkat | P0 |
| **DVC-04** | Lihat detail perangkat (status, data terakhir, lokasi) | P0 |
| **DVC-05** | Update informasi perangkat (name, type, location, coordinates) | P0 |
| **DVC-06** | Hapus perangkat (cascade ke sensor_data dan alerts) | P0 |
| **DVC-07** | Auto-detect status online/offline (timeout 15 menit) | P0 |
| **DVC-08** | Show latest WiFi SSID per device | P0 |
| **DVC-09** | Show uptime per device | P0 |

### 4.3 Data Reception (API)

| ID | Requirement | Priority |
|----|-------------|----------|
| **DAT-01** | Endpoint POST /api/v1/data menerima JSON payload | P0 |
| **DAT-02** | Validasi required fields: device_id, api_key, sensor_type, data | P0 |
| **DAT-03** | Validasi device_id dan api_key mencocokkan database | P0 |
| **DAT-04** | Simpan sensor data ke database dengan timestamp WIB | P0 |
| **DAT-05** | Support metadata tambahan: wifi_ssid, uptime_seconds | P0 |
| **DAT-06** | Update device status menjadi "online" setiap data diterima | P0 |
| **DAT-07** | Return timestamp untuk konfirmasi | P0 |

### 4.4 Dashboard & Visualization

| ID | Requirement | Priority |
|----|-------------|----------|
| **DASH-01** | Ring kesehatan (donut) menunjukkan persentase online | P0 |
| **DASH-02** | Statistik total, online, offline, alert | P0 |
| **DASH-03** | Tabel daftar perangkat dengan status, WiFi, uptime | P0 |
| **DASH-04** | Peta interaktif (preview) lokasi perangkat | P0 |
| **DASH-05** | Search/filter perangkat | P1 |
| **DASH-06** | Refresh data manual | P1 |
| **DASH-07** | Auto-refresh setiap 30 detik | P0 |
| **DASH-08** | Tampilkan waktu WIB real-time | P0 |

### 4.5 Interactive Map

| ID | Requirement | Priority |
|----|-------------|----------|
| **MAP-01** | Tampilkan semua perangkat di peta (Leaflet.js) | P0 |
| **MAP-02** | Marker warna berbeda untuk online (hijau) dan offline (merah) | P0 |
| **MAP-03** | Popup menampilkan nama dan ID perangkat | P0 |
| **MAP-04** | Select perangkat dari dropdown untuk update lokasi | P0 |
| **MAP-05** | Click peta untuk memilih lokasi | P1 |
| **MAP-06** | Simpan lokasi ke perangkat melalui API PUT | P0 |
| **MAP-07** | Fullscreen peta dengan zoom control | P0 |

### 4.6 Analytics & Charts

| ID | Requirement | Priority |
|----|-------------|----------|
| **CHT-01** | Combined chart semua perangkat (temperature) | P0 |
| **CHT-02** | Individual chart per perangkat (temp, humidity, gas) | P0 |
| **CHT-03** | Time range filter: 1 jam, 3 jam, 6 jam, 24 jam | P0 |
| **CHT-04** | Auto-select perangkat yang disimpan di localStorage | P1 |
| **CHT-05** | Multi-line chart dengan legend | P0 |
| **CHT-06** | Tooltip interaktif pada chart | P0 |
| **CHT-07** | Responsif terhadap perubahan ukuran layar | P0 |

### 4.7 Mobile Interface

| ID | Requirement | Priority |
|----|-------------|----------|
| **MOB-01** | Auto-detect device mobile/tablet → redirect to /mobile | P0 |
| **MOB-02** | Mobile-optimized dashboard dengan card layout | P0 |
| **MOB-03** | Bottom navigation: Dashboard, Devices, Desktop, Logout | P0 |
| **MOB-04** | FAB (Floating Action Button) untuk menu tambahan | P0 |
| **MOB-05** | Bottom sheet modal untuk tambah perangkat | P0 |
| **MOB-06** | Compact device cards dengan status dan info | P0 |
| **MOB-07** | Preview peta lokasi dengan marker | P0 |

### 4.8 Device Detail Page

| ID | Requirement | Priority |
|----|-------------|----------|
| **DET-01** | Informasi detail perangkat (ID, type, location, status) | P0 |
| **DET-02** | Live indicator jika perangkat online | P0 |
| **DET-03** | Grid sensor cards dengan nilai real-time | P0 |
| **DET-04** | Sensor gauge bar visual | P0 |
| **DET-05** | Timeline aktivitas perangkat | P1 |
| **DET-06** | Auto-refresh setiap 10 detik | P0 |
| **DET-07** | Tombol kembali ke dashboard | P0 |
| **DET-08** | Tampilkan WiFi SSID dan uptime | P0 |

### 4.9 Background System

| ID | Requirement | Priority |
|----|-------------|----------|
| **BGK-01** | Background thread untuk cek status perangkat | P0 |
| **BGK-02** | Cek status setiap 60 detik | P0 |
| **BGK-03** | Set status offline jika tidak ada data dalam 15 menit | P0 |
| **BGK-04** | Handle error dengan print log | P1 |
| **BGK-05** | Daemon thread (tidak blocking startup) | P0 |

### 4.10 Theme Support

| ID | Requirement | Priority |
|----|-------------|----------|
| **THE-01** | Dark mode default | P0 |
| **THE-02** | Light mode toggle | P0 |
| **THE-03** | Theme preference saved di localStorage | P0 |
| **THE-04** | Apply theme ke semua halaman (login, dashboard, mobile, detail) | P0 |
| **THE-05** | Chart colors adapt sesuai theme | P0 |
| **THE-06** | Map filter adapt sesuai theme (invert untuk dark) | P0 |

---

## 5. Non-Functional Requirements

### 5.1 Performance

| ID | Requirement | Target |
|----|-------------|--------|
| **NFR-01** | Dashboard load time | < 2 detik |
| **NFR-02** | API response time | < 500ms |
| **NFR-03** | Concurrent device support | 100+ devices |
| **NFR-04** | Data history retention | 500 records per device |
| **NFR-05** | Auto-refresh interval | 30 detik |

### 5.2 Security

| ID | Requirement | Priority |
|----|-------------|----------|
| **NFR-06** | Secret key via environment variable | P0 |
| **NFR-07** | Credentials via environment variable | P0 |
| **NFR-08** | SQLite database with parameterized queries (SQL injection prevention) | P0 |
| **NFR-09** | API key per device (not global) | P0 |

### 5.3 Reliability

| ID | Requirement | Priority |
|----|-------------|----------|
| **NFR-10** | Systemd service for auto-restart | P0 |
| **NFR-11** | Database init with migration support | P0 |
| **NFR-12** | Thread safety untuk database operations | P0 |

### 5.4 Usability

| ID | Requirement | Priority |
|----|-------------|----------|
| **NFR-13** | Intuitive navigation with sidebar | P0 |
| **NFR-14** | Visual feedback untuk actions (toast) | P0 |
| **NFR-15** | Loading states untuk async operations | P0 |
| **NFR-16** | Responsive design untuk semua devices | P0 |

### 5.5 Maintainability

| ID | Requirement | Priority |
|----|-------------|----------|
| **NFR-17** | Modular code structure | P0 |
| **NFR-18** | Documentation in README | P0 |
| **NFR-19** | MIT License | P0 |

---

## 6. User Interface & UX Specifications

### 6.1 Layout Structure

```
┌──────────────────────────────────────────────────────────────────────┐
│ [SIDEBAR 248px] │ [TOP BAR]                                         │
│  NEXUS           │  Page Title  │  [Search]  [Add]  [Time]         │
│  ─────────────── │──────────────────────────────────────────────────│
│  📊 Dashboard    │                                                   │
│  🗺️ Peta        │   CONTENT AREA                                    │
│  📈 Analitik     │                                                   │
│  ─────────────── │   ┌────────────────────────────────────────────┐ │
│  💻 Perangkat    │   │  OVERVIEW GRID                             │ │
│                  │   │  [Ring Card] [Stats Cards]                 │ │
│  🌙 Tema         │   └────────────────────────────────────────────┘ │
│  🚪 Logout       │   ┌────────────────────────────────────────────┐ │
└──────────────────┘   │  TABLE / CHART / MAP                      │
                       │                                           │
                       └────────────────────────────────────────────┘
```

### 6.2 Color Palette

| Element | Dark Mode | Light Mode |
|---------|-----------|------------|
| Background | `#000000` | `#f0f0f5` |
| Surface | `rgba(28,28,30,0.55)` | `rgba(255,255,255,0.72)` |
| Surface 2 | `rgba(255,255,255,0.045)` | `rgba(0,0,0,0.05)` |
| Text Primary | `#f5f5f7` | `#1c1c1e` |
| Text Secondary | `rgba(235,235,245,0.72)` | `rgba(60,60,67,0.75)` |
| Text Tertiary | `rgba(235,235,245,0.45)` | `rgba(60,60,67,0.50)` |
| Primary Blue | `#0a84ff` | `#007aff` |
| Success Green | `#30d158` | `#34c759` |
| Danger Red | `#ff453a` | `#ff3b30` |
| Warning Orange | `#ff9f0a` | `#ff9500` |
| Purple | `#bf5af2` | `#af52de` |

### 6.3 Typography

| Element | Font | Weight | Size |
|---------|------|--------|------|
| Headline | Inter | 800 | 20px |
| Section Title | Inter | 700 | 14.5px |
| Body Text | Inter | 400 | 13px |
| Mono (IDs, time) | JetBrains Mono | 500 | 12px |
| Small Label | Inter | 700 | 10px |

### 6.4 Spacing System

| Spacing | Value |
|---------|-------|
| XS | 4px |
| S | 8px |
| M | 12px |
| L | 16px |
| XL | 24px |
| XXL | 34px |

### 6.5 Breakpoints

| Breakpoint | Width | Layout |
|------------|-------|--------|
| Mobile | < 768px | Single column, compact |
| Tablet | 768px - 992px | 2 columns |
| Desktop | > 992px | Full layout, sidebar |
| Large | > 1200px | Expanded content |

---

## 7. API Specifications

### 7.1 POST /api/v1/data
*Endpoint untuk menerima data dari perangkat IoT*

**Request:**
```json
{
    "device_id": "ESP32-001",
    "api_key": "a1b2c3d4e5f6...",
    "sensor_type": "DHT22",
    "wifi_ssid": "MyWiFi",
    "uptime_seconds": 3600,
    "data": {
        "temperature": 29.4,
        "humidity": 68.0
    }
}
```

**Response (200):**
```json
{
    "success": true,
    "message": "Data received",
    "timestamp": "2026-08-31T14:30:25+07:00"
}
```

**Error Responses:**
| Code | Response |
|------|----------|
| 400 | `{"success": false, "error": "Missing: device_id"}` |
| 401 | `{"success": false, "error": "Invalid device_id or api_key"}` |
| 500 | `{"success": false, "error": "Database error"}` |

### 7.2 GET /api/v1/dashboard
*Endpoint untuk data dashboard*

**Response:**
```json
{
    "success": true,
    "summary": {
        "total_devices": 10,
        "online_devices": 7,
        "offline_devices": 3
    },
    "devices": [
        {
            "device_id": "ESP32-001",
            "device_name": "Sensor Suhu",
            "device_type": "ESP32",
            "location": "Ruang Server",
            "latitude": -6.2088,
            "longitude": 106.8456,
            "status": "online",
            "last_seen": "2026-08-31T14:30:25+07:00",
            "latest_wifi_ssid": "MyWiFi",
            "latest_uptime_seconds": 3600
        }
    ]
}
```

### 7.3 GET /api/v1/devices
*Endpoint untuk daftar semua perangkat*

**Response:**
```json
{
    "success": true,
    "devices": [
        {
            "device_id": "ESP32-001",
            "device_name": "Sensor Suhu",
            "device_type": "ESP32",
            "location": "Ruang Server",
            "latitude": 0,
            "longitude": 0,
            "description": "",
            "status": "online",
            "last_seen": "2026-08-31T14:30:25+07:00",
            "created_at": "2026-08-31T10:00:00+07:00"
        }
    ]
}
```

### 7.4 POST /api/v1/devices
*Endpoint untuk menambah perangkat baru*

**Request:**
```json
{
    "device_id": "ESP32-002",
    "device_name": "Sensor Kelembaban",
    "device_type": "ESP8266",
    "location": "Greenhouse"
}
```

**Response:**
```json
{
    "success": true,
    "device": {
        "device_id": "ESP32-002",
        "device_name": "Sensor Kelembaban",
        "api_key": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
    }
}
```

### 7.5 GET /api/v1/devices/{device_id}
*Endpoint untuk detail perangkat*

**Response:**
```json
{
    "success": true,
    "device": {
        "device_id": "ESP32-001",
        "device_name": "Sensor Suhu",
        "device_type": "ESP32",
        "location": "Ruang Server",
        "status": "online",
        "last_seen": "2026-08-31T14:30:25+07:00",
        "latest_data": {
            "sensor_type": "DHT22",
            "data": {"temperature": 29.4, "humidity": 68.0},
            "wifi_ssid": "MyWiFi",
            "uptime_seconds": 3600,
            "timestamp": "2026-08-31T14:30:25+07:00"
        }
    }
}
```

### 7.6 GET /api/v1/devices/{device_id}/history
*Endpoint untuk histori data sensor*

**Parameters:**
- `hours` (query, optional, default=3, max=24)

**Response:**
```json
{
    "success": true,
    "history": [
        {
            "sensor_type": "DHT22",
            "data": {"temperature": 29.4, "humidity": 68.0},
            "wifi_ssid": "MyWiFi",
            "uptime_seconds": 3600,
            "timestamp": "2026-08-31T14:30:25+07:00"
        }
    ],
    "data_count": 120
}
```

### 7.7 PUT /api/v1/devices/{device_id}
*Endpoint untuk update perangkat*

**Request:**
```json
{
    "device_name": "Sensor Baru",
    "device_type": "ESP32",
    "location": "Lantai 2",
    "latitude": -6.2088,
    "longitude": 106.8456,
    "description": "Sensor di ruang meeting"
}
```

### 7.8 DELETE /api/v1/devices/{device_id}
*Endpoint untuk hapus perangkat (cascade)*

---

## 8. Database Schema

### 8.1 Devices Table
```sql
CREATE TABLE devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT UNIQUE NOT NULL,
    device_name TEXT NOT NULL,
    device_type TEXT DEFAULT 'ESP32',
    location TEXT DEFAULT '',
    latitude REAL DEFAULT 0,
    longitude REAL DEFAULT 0,
    description TEXT DEFAULT '',
    api_key TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'offline',
    last_seen DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 8.2 Sensor Data Table
```sql
CREATE TABLE sensor_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    sensor_type TEXT NOT NULL,
    data TEXT NOT NULL,
    wifi_ssid TEXT DEFAULT '',
    uptime_seconds INTEGER DEFAULT 0,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES devices (device_id)
);
```

### 8.3 Alerts Table
```sql
CREATE TABLE alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    message TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES devices (device_id)
);
```

### 8.4 Indexes
```sql
CREATE INDEX idx_sensor_data_device_timestamp 
ON sensor_data (device_id, timestamp);
```

---

## 9. Deployment Requirements

### 9.1 System Requirements
| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 1 core | 2+ cores |
| RAM | 512 MB | 1+ GB |
| Storage | 5 GB | 10+ GB |
| OS | Ubuntu 22.04+ | Ubuntu 24.04 LTS |
| Python | 3.8+ | 3.11+ |

### 9.2 Environment Variables
```env
IOT_USERNAME=admin
IOT_PASSWORD=admin123
SECRET_KEY=your-secret-key-here
```

### 9.3 Service Setup (Systemd)
```ini
[Unit]
Description=NEXUS IoT Platform
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/nexus-iot
Environment="PATH=/opt/nexus-iot/venv/bin"
ExecStart=/opt/nexus-iot/venv/bin/python /opt/nexus-iot/app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 9.4 Port Configuration
| Service | Port |
|---------|------|
| Flask App | 5000 |
| (Development) | 5000 |

---

## 10. Device Firmware (ESP32)

### 10.1 Requirements
| Component | Specification |
|-----------|---------------|
| Board | ESP32, ESP8266, Arduino with WiFi |
| Sensor | DHT22, DHT11, BME280, MQ series, etc. |
| Firmware | MicroPython |
| Network | WiFi 2.4GHz |

### 10.2 Configuration Parameters
| Parameter | Description | Default |
|-----------|-------------|---------|
| WIFI_SSID | WiFi network name | (required) |
| WIFI_PASSWORD | WiFi password | (required) |
| API_URL | Server API endpoint | (required) |
| DEVICE_ID | Unique device identifier | (required) |
| API_KEY | API key from dashboard | (required) |
| SENSOR_TYPE | Sensor type | (required) |
| SEND_INTERVAL | Data send interval (seconds) | 600 |
| DHT_PIN | GPIO pin for DHT sensor | 4 |

### 10.3 Data Format
```python
payload = {
    "device_id": DEVICE_ID,
    "api_key": API_KEY,
    "sensor_type": SENSOR_TYPE,
    "wifi_ssid": WIFI_SSID,
    "uptime_seconds": uptime,
    "data": {
        "temperature": temp,
        "humidity": humidity,
        # additional custom fields
    }
}
```

---

## 11. Testing Requirements

### 11.1 Unit Tests
| ID | Test Case | Priority |
|----|-----------|----------|
| **TST-01** | Device registration with valid data | P0 |
| **TST-02** | Device registration with duplicate ID → error | P0 |
| **TST-03** | Data reception with valid API key → success | P0 |
| **TST-04** | Data reception with invalid API key → 401 | P0 |
| **TST-05** | Device status auto-update online/offline | P0 |
| **TST-06** | Dashboard data aggregation | P0 |
| **TST-07** | Device deletion (cascade) | P0 |

### 11.2 Integration Tests
| ID | Test Case | Priority |
|----|-----------|----------|
| **TST-08** | Full flow: device registration → data send → dashboard | P0 |
| **TST-09** | ESP32 simulation → API → database | P0 |
| **TST-10** | Multi-device concurrent data send | P1 |

### 11.3 UI Tests
| ID | Test Case | Priority |
|----|-----------|----------|
| **TST-11** | Dashboard load and display | P0 |
| **TST-12** | Map rendering and markers | P0 |
| **TST-13** | Chart rendering with data | P0 |
| **TST-14** | Mobile redirect and layout | P0 |
| **TST-15** | Theme toggle functionality | P0 |

---

## 12. Roadmap

### Phase 1: Current (v2.0) — Production Ready
- ✅ Authentication system
- ✅ Device management CRUD
- ✅ Real-time data reception
- ✅ Dashboard with stats and table
- ✅ Interactive map
- ✅ Multi-chart analytics
- ✅ Mobile responsive design
- ✅ Dark/Light theme
- ✅ ESP32 firmware

### Phase 2: Next (v2.1) — Q4 2026
| Feature | Description | Priority |
|---------|-------------|----------|
| User Management | Multiple users with roles | P1 |
| Email Alerts | Notifikasi via email | P1 |
| Data Export | CSV/JSON export | P1 |
| Custom Dashboards | User-defined dashboard layouts | P2 |
| API Rate Limiting | Prevent abuse | P2 |
| WebSocket | Real-time data push (no polling) | P2 |

### Phase 3: Future (v3.0) — Q1 2027
| Feature | Description | Priority |
|---------|-------------|----------|
| PostgreSQL Support | Production-grade database | P2 |
| Docker Support | Containerized deployment | P2 |
| Rule Engine | Custom alert rules | P2 |
| Mobile App | Native iOS/Android app | P3 |
| MQTT Support | Alternative protocol | P3 |

---

## 13. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Database corruption | Low | High | Regular backups, transaction support |
| High concurrent traffic | Medium | Medium | API rate limiting, optimization |
| Security breach | Low | High | Environment variables, API key rotation |
| ESP32 disconnection | High | Low | Auto-reconnect on device side |
| Data loss | Low | High | Regular database backups |
| Server downtime | Medium | High | Systemd auto-restart, monitoring |

---

## 14. Metrics & KPIs

| Metric | Target | Measurement |
|--------|--------|-------------|
| Devices per user | > 10 | Database count |
| Data reception rate | > 95% success | API logs |
| Dashboard load time | < 2s | Browser DevTools |
| Uptime | > 99.5% | Server monitoring |
| API response time | < 500ms | Server logs |

---

## 15. Success Criteria

### Launch Success (v2.0)
- [x] All core features functional
- [x] Production deployment on Proxmox LXC
- [x] ESP32 firmware tested with real hardware
- [x] Documentation complete
- [x] MIT License

### Growth Success (v2.1+)
- [ ] 50+ active devices
- [ ] 10+ active users
- [ ] Email alert system operational
- [ ] Custom dashboard feature

---

## 16. Appendix

### A. Project Structure
```
nexus-iot/
├── app.py                 # Main Flask application
├── database.py            # Database initialization and connection
├── requirements.txt       # Python dependencies
├── .env.example           # Environment variables template
├── README.md              # Project documentation
├── LICENSE                # MIT License
├── esp32/
│   └── main.py           # ESP32 MicroPython firmware
└── templates/
    ├── login.html         # Authentication page
    ├── dashboard.html     # Main dashboard (desktop)
    ├── mobile.html        # Mobile-optimized interface
    └── device_detail.html # Per-device detail page
```

### B. Dependencies
```
Flask==3.1.3
flask-cors==6.0.5
python-dotenv==1.2.3
Werkzeug==3.1.8
Jinja2==3.1.6
```

### C. External Libraries (CDN)
| Library | Version | Purpose |
|---------|---------|---------|
| Chart.js | 4.4.0 | Charts and graphs |
| Leaflet.js | 1.9.4 | Interactive maps |
| Font Awesome | 6.5.1 | Icons |
| Google Fonts | — | Fonts (Inter, JetBrains Mono) |

### D. Glossary
| Term | Definition |
|------|------------|
| Device ID | Unique identifier for each IoT device |
| API Key | 32-character hex key for device authentication |
| Uptime | Time since device last reboot/startup |
| WIB | Waktu Indonesia Barat (UTC+7) |
| FAB | Floating Action Button (mobile UI) |
| PRD | Product Requirements Document |

---

**Last Updated:** 31 Agustus 2026
**Version:** 2.0
