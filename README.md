# NEXUS IoT - Universal IoT Monitoring Platform

Platform monitoring IoT dengan dashboard real-time, peta interaktif, dan multi-chart analytics. Dibangun menggunakan Flask, Chart.js, dan Leaflet.js dengan fokus pada keamanan dan skalabilitas.

![Version](https://img.shields.io/badge/version-3.0.1-blue)
![Python](https://img.shields.io/badge/python-3.9+-green)
![Flask](https://img.shields.io/badge/flask-3.1+-red)
![License](https://img.shields.io/badge/license-MIT-yellow)
![Docker](https://img.shields.io/badge/docker-ready-blue)

---

## Daftar Isi

- [Fitur](#fitur)
- [Arsitektur](#arsitektur)
- [Instalasi Cepat (Docker)](#instalasi-cepat-docker)
- [Instalasi Manual](#instalasi-manual)
- [Konfigurasi](#konfigurasi)
- [Docker Deployment](#docker-deployment)
- [Deploy ke Production](#deploy-ke-production)
- [API Endpoints](#api-endpoints)
- [Setup ESP32](#setup-esp32)
- [Struktur Project](#struktur-project)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Lisensi](#lisensi)

---

## Fitur

**Core:**
- Autentikasi dengan session management dan CSRF protection
- Dashboard real-time, auto-refresh setiap 30 detik
- Peta interaktif dengan Leaflet.js
- Multi-chart analytics dengan drag dan resize, 10+ tipe visualisasi
- Responsive design dengan mobile UI dan bottom navigation
- Dark/light theme tersimpan di localStorage

**Device Management:**
- Auto-deteksi online/offline, timeout 15 menit (configurable)
- API key unik per device, bisa di-regenerate
- Universal compatibility: ESP32, ESP8266, Arduino, Raspberry Pi
- Timezone WIB konsisten di semua tampilan

**Production:**
- Rate limiting untuk login dan API
- Input validation dengan Marshmallow
- Rotating logs dengan backup otomatis
- Database backup otomatis dengan retention policy
- Data cleanup otomatis (default 30 hari)
- Health check endpoint `/health` dan `/ready`
- Graceful shutdown untuk background task
- Alert system dengan threshold rules
- Pagination untuk list device
- Schema migration dengan versioning
- Multi-stage Docker build dengan non-root user
- Semua konfigurasi dari environment variable

---

## Arsitektur

```
ESP32/ESP8266/Arduino (DHT22, BME280, MQ-2, dll)
                        │
                        │ HTTP POST (JSON)
                        ▼
┌─────────────────────────────────────────────────────┐
│                 NEXUS IoT SERVER                     │
│                                                      │
│  Flask Application Factory                           │
│  ├── API Blueprint        (data, devices, alerts)    │
│  ├── Auth Blueprint       (login, logout)            │
│  ├── Views Blueprint      (dashboard, mobile)        │
│  └── Alerts Module        (threshold checking)       │
│                                                      │
│  Extensions: CSRF, Rate Limiter, CORS, Logging       │
│                                                      │
│  Background Threads (daemon):                        │
│  ├── Status Checker       (set offline > timeout)    │
│  ├── Data Cleanup         (hapus data lama)          │
│  └── Backup Scheduler     (backup database)          │
│                                                      │
│  SQLite Database (WAL Mode)                          │
│  ├── devices                                         │
│  ├── sensor_data                                     │
│  └── alerts                                          │
└─────────────────────────────────────────────────────┘
                        │
                        ▼
        Web Interface (Dashboard / Mobile / Device Detail)
```

**Tech Stack:**

| Layer | Technology | Version |
|-------|-----------|---------|
| Backend | Python Flask | 3.1.3 |
| Database | SQLite | 3.x |
| Frontend | HTML5, CSS3, Vanilla JS | - |
| Charts | Chart.js | 4.4.0 |
| Maps | Leaflet.js | 1.9.4 |
| Icons | Font Awesome | 6.5.1 |
| Server | Gunicorn | 21.2.0 |
| Container | Docker, Docker Compose | - |

---

## Instalasi Cepat (Docker)

### Prasyarat

- Docker Engine 20.10+
- Docker Compose v2.0+
- Git

### Langkah

```bash
# 1. Clone repository
git clone https://github.com/takathena/nexus-iot.git
cd nexus-iot

# 2. Copy environment file
cp .env.example .env

# 3. Generate SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(32))"

# 4. Edit .env, minimal ubah SECRET_KEY dan IOT_PASSWORD
nano .env

# 5. Fix permission folder (wajib)
mkdir -p database logs backup
chown -R 1000:1000 database logs backup

# 6. Beri permission entrypoint script
chmod +x docker-entrypoint.sh

# 7. Build dan jalankan
docker compose up -d --build

# 8. Tunggu 30 detik, lalu cek status
sleep 30
docker compose ps
```

**Expected output:**

```
NAME           STATUS
nexus-iot      Up (healthy)
nexus-nginx    Up (healthy)
```

### Akses

| URL | Deskripsi |
|-----|-----------|
| `http://localhost:5008` | Dashboard |
| `http://localhost:5008/health` | Health check |
| `http://localhost:5008/mobile` | Mobile UI |

---

## Instalasi Manual

### Prasyarat

| Komponen | Minimum | Rekomendasi |
|----------|---------|-------------|
| OS | Ubuntu 20.04+ | Ubuntu 24.04 LTS |
| Python | 3.9+ | 3.11+ |
| RAM | 512 MB | 1+ GB |
| Storage | 1 GB | 5+ GB |

### Langkah

```bash
# 1. Clone
git clone https://github.com/takathena/nexus-iot.git
cd nexus-iot

# 2. Virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4. Setup .env
cp .env.example .env
nano .env  # Edit SECRET_KEY dan IOT_PASSWORD

# 5. Inisialisasi database
python -c "from database import init_db; init_db()"

# 6. Jalankan
python app.py
```

**Atau dengan Makefile:**

```bash
make dev       # Setup environment
make run       # Development server
make run-prod  # Production dengan Gunicorn
```

---

## Konfigurasi

Semua konfigurasi ada di file `.env`. Copy dari `.env.example`.

### Server

```env
HOST=0.0.0.0
PORT=5000
FLASK_ENV=production  # development | production | testing
DEBUG=False
WORKERS=2
THREADS=4
```

### Security

```env
# Generate: python3 -c "import secrets; print(secrets.token_hex(32))"
# Wajib minimal 32 karakter
SECRET_KEY=your-64-char-hex-secret-key

# Set True jika pakai HTTPS
SESSION_COOKIE_SECURE=False
SESSION_LIFETIME_HOURS=24
```

### Authentication

```env
# Wajib di-set
IOT_USERNAME=admin
IOT_PASSWORD=ganti-dengan-password-kuat
```

### Database

```env
DB_PATH=database/iot.db
DATA_RETENTION_DAYS=30

BACKUP_ENABLED=True
BACKUP_INTERVAL_HOURS=24
BACKUP_RETENTION_DAYS=7
BACKUP_DIR=backup
```

### Device Monitoring

```env
OFFLINE_TIMEOUT=900   # 15 menit (detik)
CHECK_INTERVAL=60     # 1 menit (detik)
```

### CORS

```env
CORS_ORIGINS=http://localhost:5000,https://iot.example.com
```

### Rate Limiting

```env
RATE_LIMIT_DEFAULT=200 per minute
RATE_LIMIT_DATA=60 per minute
RATE_LIMIT_LOGIN=5 per minute
```

### Logging

```env
LOG_LEVEL=INFO          # DEBUG | INFO | WARNING | ERROR
LOG_FILE=logs/nexus.log
LOG_MAX_BYTES=10485760  # 10 MB
LOG_BACKUP_COUNT=5
```

### Alerts

```env
ALERT_TEMP_MIN=0
ALERT_TEMP_MAX=40
ALERT_HUMIDITY_MIN=20
ALERT_HUMIDITY_MAX=90
ALERT_GAS_MAX=70
```

### Nginx

```env
NGINX_PORT=5008
```

---

## Docker Deployment

### File yang Dibutuhkan

- `Dockerfile` — Multi-stage build, non-root user dengan gosu
- `docker-entrypoint.sh` — Handle permission dan drop privilege
- `docker-compose.yml` — Flask dan Nginx orchestration
- `.dockerignore` — Exclude file yang tidak perlu
- `.env` — Konfigurasi
- `nginx/` — Config Nginx

### Struktur Volume

| Host | Container | Isi |
|------|-----------|-----|
| `./database` | `/app/database` | SQLite DB |
| `./logs` | `/app/logs` | Log files |
| `./backup` | `/app/backup` | DB backups |
| `./static` | `/static` | Static files (Nginx) |
| `./.env` | `/app/.env` | Config |

### Permission Folder

Container jalan sebagai user `nexus` (UID 1000) untuk security. Folder di host harus dimiliki UID 1000 supaya bisa write:

```bash
# Wajib dijalankan sebelum `docker compose up`
mkdir -p database logs backup
chown -R 1000:1000 database logs backup
```

Kalau tidak, container akan error:

```
PermissionError: [Errno 13] Permission denied: '/app/logs/nexus.log'
```

Penyebabnya, Docker volume yang di-mount mempertahankan ownership dari host. Entrypoint script akan otomatis fix permission saat startup, tapi hanya kalau folder sudah ada dan writeable oleh root.

### Commands

```bash
# Build image
docker compose build

# Build tanpa cache
docker compose build --no-cache

# Jalankan (background)
docker compose up -d

# Lihat log
docker compose logs -f

# Lihat log container tertentu
docker compose logs -f nexus-iot

# Status
docker compose ps

# Restart
docker compose restart

# Stop
docker compose down

# Stop dan hapus volume (hati-hati!)
docker compose down -v

# Shell masuk ke container
docker compose exec nexus-iot bash

# Cek health
docker compose exec nexus-iot curl http://localhost:5000/health
```

### Update Aplikasi

```bash
git pull

docker compose down
docker compose build --no-cache
docker compose up -d

# Cek
sleep 30
docker compose ps
docker compose logs nexus-iot | tail -20
```

### Cara Kerja docker-entrypoint.sh

Script ini otomatis:

1. Buat folder yang dibutuhkan (`database`, `logs`, `backup`)
2. Chown folder ke user `nexus` (UID 1000)
3. Drop privilege dari root ke `nexus`
4. Jalankan Gunicorn sebagai `nexus` (non-root)

Output di log:

```
[entrypoint] Running as root, fixing permissions...
[entrypoint] Permissions OK
[entrypoint] Dropping privileges to nexus user...
[2026-09-12 ...] [INFO] Starting gunicorn 21.2.0
```

---

## Deploy ke Production

### Opsi 1: Systemd Service (Manual)

**Langkah 1: Setup Project**

```bash
# Setup user khusus
sudo useradd -r -s /bin/false nexus
sudo mkdir -p /opt/nexus-iot
sudo chown nexus:nexus /opt/nexus-iot

# Clone dan install
cd /opt
sudo -u nexus git clone https://github.com/takathena/nexus-iot.git
cd nexus-iot

sudo -u nexus python3 -m venv venv
sudo -u nexus venv/bin/pip install -r requirements.txt

# Setup .env
sudo -u nexus cp .env.example .env
sudo nano .env  # Edit credentials dan SECRET_KEY

# Init DB
sudo -u nexus venv/bin/python -c "from database import init_db; init_db()"
```

**Langkah 2: Systemd Unit File**

```bash
sudo nano /etc/systemd/system/nexus-iot.service
```

```ini
[Unit]
Description=NEXUS IoT Platform
Documentation=https://github.com/takathena/nexus-iot
After=network.target

[Service]
Type=simple
User=nexus
Group=nexus
WorkingDirectory=/opt/nexus-iot
Environment="PATH=/opt/nexus-iot/venv/bin"
Environment="PYTHONUNBUFFERED=1"
ExecStart=/opt/nexus-iot/venv/bin/gunicorn -c gunicorn.conf.py wsgi:app
ExecReload=/bin/kill -s HUP $MAINPID
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=nexus-iot

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/nexus-iot/database /opt/nexus-iot/logs /opt/nexus-iot/backup

[Install]
WantedBy=multi-user.target
```

**Langkah 3: Start Service**

```bash
sudo systemctl daemon-reload
sudo systemctl enable nexus-iot
sudo systemctl start nexus-iot
sudo systemctl status nexus-iot

# Lihat log
sudo journalctl -u nexus-iot -f
```

### Opsi 2: Proxmox LXC

**Langkah 1: Buat Container**

```
Template: ubuntu-24.04-standard
CPU: 1-2 core
RAM: 512 MB - 1 GB
Disk: 8 GB
Network: DHCP / Static
```

**Langkah 2: Setup Container**

```bash
apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv git curl
```

**Langkah 3: Deploy**

Ikuti langkah [Systemd Service](#opsi-1-systemd-service-manual) di atas.

### Opsi 3: Nginx Reverse Proxy

**Konfigurasi Nginx:**

```nginx
server {
    listen 80;
    server_name iot.example.com;

    # Redirect ke HTTPS (jika pakai SSL)
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name iot.example.com;

    ssl_certificate /etc/letsencrypt/live/iot.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/iot.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;

    # Gzip
    gzip on;
    gzip_types text/plain text/css application/json application/javascript;

    # Static files
    location /static/ {
        alias /opt/nexus-iot/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Proxy ke Flask
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
```

**Setting `.env` untuk HTTPS:**

```env
SESSION_COOKIE_SECURE=True
CORS_ORIGINS=https://iot.example.com
```

---

## API Endpoints

Base URL: `http://localhost:5000/api/v1`

### Authentication

| Endpoint | Method | Auth | Deskripsi |
|----------|--------|------|-----------|
| `/login` | GET/POST | None | Halaman login |
| `/logout` | GET | Session | Logout |

### Device Data

| Endpoint | Method | Auth | Deskripsi |
|----------|--------|------|-----------|
| `/data` | POST | API Key | Terima data dari device |
| `/dashboard` | GET | None | Data dashboard dan summary |
| `/devices` | GET | None | List devices (paginated) |
| `/devices` | POST | None | Tambah device baru |
| `/devices/{id}` | GET | None | Detail device dan data terbaru |
| `/devices/{id}` | PUT | None | Update device |
| `/devices/{id}` | DELETE | None | Hapus device (cascade) |
| `/devices/{id}/history` | GET | None | Histori data sensor |
| `/devices/{id}/regenerate-key` | POST | None | Generate API key baru |

### Alerts

| Endpoint | Method | Deskripsi |
|----------|--------|-----------|
| `/alerts` | GET | List alert aktif |
| `/alerts/{id}/acknowledge` | POST | Tandai alert sudah dibaca |

### Health

| Endpoint | Method | Deskripsi |
|----------|--------|-----------|
| `/health` | GET | Health check (DB, uptime) |
| `/ready` | GET | Readiness check |

### Contoh Request

**Kirim Data dari Device:**

```bash
curl -X POST http://localhost:5000/api/v1/data \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "ESP32-001",
    "api_key": "your-64-char-api-key",
    "sensor_type": "DHT22",
    "wifi_ssid": "MyWiFi",
    "uptime_seconds": 3600,
    "data": {
      "temperature": 29.4,
      "humidity": 68.0
    }
  }'
```

**Response:**

```json
{
    "success": true,
    "message": "Data received",
    "timestamp": "2026-09-12T14:30:25+07:00"
}
```

**Tambah Device:**

```bash
curl -X POST http://localhost:5000/api/v1/devices \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "ESP32-002",
    "device_name": "Sensor Kelembaban",
    "device_type": "ESP8266",
    "location": "Greenhouse"
  }'
```

**Histori Data:**

```bash
curl "http://localhost:5000/api/v1/devices/ESP32-001/history?hours=24&limit=500"
```

**Health Check:**

```bash
curl http://localhost:5000/health
```

```json
{
    "status": "healthy",
    "timestamp": "2026-09-12T14:30:25+07:00",
    "database": "connected",
    "version": "3.0.0"
}
```

---

## Setup ESP32

### Requirements

| Komponen | Spesifikasi |
|----------|-------------|
| Board | ESP32 / ESP8266 |
| Sensor | DHT22, DHT11, BME280, dll |
| Firmware | MicroPython |
| Network | WiFi 2.4GHz |

### Wiring DHT22

```
ESP32          DHT22
-----          -----
3.3V    ---->  VCC (Pin 1)
GPIO4   ---->  DATA (Pin 2)
GND     ---->  GND (Pin 4)

Tambahkan resistor 10k antara VCC dan DATA
```

### Flash MicroPython

```bash
# Erase flash
esptool.py --chip esp32 --port /dev/ttyUSB0 erase_flash

# Flash firmware (download dulu dari micropython.org)
esptool.py --chip esp32 --port /dev/ttyUSB0 write_flash -z 0x1000 esp32-firmware.bin
```

### Upload Firmware

**Edit `esp32/main.py`:**

```python
# ============ KONFIGURASI ============
WIFI_SSID = "NAMA_WIFI"
WIFI_PASSWORD = "PASSWORD_WIFI"
API_URL = "http://192.168.1.100:5000/api/v1/data"
DEVICE_ID = "ESP32-001"
API_KEY = "API_KEY_DARI_DASHBOARD"
SENSOR_TYPE = "DHT22"
DHT_PIN = 4
SEND_INTERVAL = 300  # 5 menit
```

**Upload:**

```bash
# Install ampy
pip install adafruit-ampy

# Upload
ampy --port /dev/ttyUSB0 put esp32/main.py

# Reset ESP32
ampy --port /dev/ttyUSB0 reset
```

### Monitor Serial

```bash
screen /dev/ttyUSB0 115200
```

**Output contoh:**

```
==================================================
ESP32 DHT22 Monitor
Device ID: ESP32-001
==================================================
WiFi: MyWiFi | IP: 192.168.1.50
Mulai monitoring...
[2026-09-12 14:30:25] Suhu: 29.4C | Hum: 68.0% | Uptime: 3600s
-> Data terkirim
```

---

## Struktur Project

```
nexus-iot/
│
├── app.py                      # Application factory
├── wsgi.py                     # WSGI entry point untuk Gunicorn
├── config.py                   # Configuration management
├── database.py                 # Database layer dan migrations
├── extensions.py               # Flask extensions
├── logging_config.py           # Logging setup
├── validators.py               # Marshmallow schemas
├── auth.py                     # Authentication blueprint
├── api.py                      # API blueprint
├── views.py                    # Web views blueprint
├── background.py               # Background tasks
├── alerts.py                   # Alert system
├── utils.py                    # Utility functions
├── gunicorn.conf.py            # Gunicorn configuration
│
├── requirements.txt            # Python dependencies
├── .env.example                # Environment template
├── .gitignore                  # Git ignore rules
├── .dockerignore               # Docker ignore rules
│
├── Dockerfile                  # Multi-stage Docker build
├── docker-entrypoint.sh        # Entrypoint (fix permission, drop privilege)
├── docker-compose.yml          # Docker compose config
├── Makefile                    # Automation commands
├── LICENSE                     # MIT License
├── README.md                   # This file
│
├── database/                   # SQLite database directory
│   └── iot.db                  # Auto-generated
│
├── logs/                       # Log directory
│   └── nexus.log               # Auto-generated
│
├── backup/                     # Database backup directory
│   └── iot_*.db                # Auto-generated
│
├── esp32/                      # ESP32 firmware
│   └── main.py
│
├── nginx/                      # Nginx configuration
│   ├── nginx.conf
│   └── conf.d/
│       └── nexus.conf
│
├── static/                     # Static files
│   ├── css/
│   │   ├── shared.css
│   │   └── dashboard.css
│   └── js/
│       ├── api.js
│       ├── theme.js
│       ├── toast.js
│       └── dashboard.js
│
└── templates/                  # Jinja2 templates
    ├── base.html
    ├── login.html
    ├── dashboard.html
    ├── mobile.html
    ├── device_detail.html
    └── partials/
        ├── dashboard_section.html
        ├── map_section.html
        ├── graph_section.html
        ├── devices_section.html
        └── modals.html
```

---

## Testing

### Manual Test dengan cURL

**Test 1: Health Check**

```bash
curl -s http://localhost:5000/health | python3 -m json.tool
```

**Test 2: Tambah Device**

```bash
# 1. Login dulu untuk dapat session cookie
curl -c cookies.txt -X POST http://localhost:5000/login \
  -d "username=admin&password=your-password"

# 2. Tambah device
curl -b cookies.txt -X POST http://localhost:5000/api/v1/devices \
  -H "Content-Type: application/json" \
  -d '{"device_id":"TEST-001","device_name":"Test Device"}'
```

**Test 3: Kirim Data**

```bash
curl -X POST http://localhost:5000/api/v1/data \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "TEST-001",
    "api_key": "PASTE_API_KEY_HERE",
    "sensor_type": "DHT22",
    "data": {"temperature": 25.5, "humidity": 60.0}
  }'
```

**Test 4: Rate Limiting**

```bash
# Kirim 10 request cepat, beberapa harus kena 429
for i in {1..10}; do
  curl -X POST http://localhost:5000/login \
    -d "username=wrong&password=wrong" \
    -s -o /dev/null -w "%{http_code}\n"
done
```

### Cek Log

```bash
# Real-time
tail -f logs/nexus.log

# 50 baris terakhir
tail -50 logs/nexus.log

# Filter error
grep ERROR logs/nexus.log

# Docker
docker compose logs -f nexus-iot
```

---

## Troubleshooting

### PermissionError: [Errno 13] Permission denied: '/app/logs/nexus.log'

**Penyebab:** Folder di host dimiliki user lain, container user `nexus` (UID 1000) tidak bisa write.

**Solusi:**

```bash
cd /path/to/nexus-iot
docker compose down

mkdir -p database logs backup
chown -R 1000:1000 database logs backup

# Cek ownership
ls -la database logs backup
# Harusnya: drwxr-xr-x 1000 1000

docker compose up -d
```

**Pencegahan:** Selalu jalankan `chown -R 1000:1000 database logs backup` sebelum `docker compose up` pertama kali.

### Container nexus-iot status: unhealthy

**Cek log:**

```bash
docker compose logs nexus-iot | tail -50
```

**Cek manual health:**

```bash
docker compose exec nexus-iot curl -v http://localhost:5000/health
```

**Kemungkinan penyebab:**

1. Permission issue (lihat di atas)
2. Config validation gagal (cek `.env`)
3. Database tidak bisa di-init

### docker-entrypoint.sh: no such file or directory

**Penyebab:** Line ending CRLF (Windows) bukan LF (Linux).

**Solusi:**

```bash
sed -i 's/\r$//' docker-entrypoint.sh
chmod +x docker-entrypoint.sh
docker compose up -d --build
```

### gosu: command not found

**Penyebab:** Package `gosu` tidak ter-install.

**Solusi:** Pastikan `Dockerfile` ada:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gosu \
    && rm -rf /var/lib/apt/lists/*
```

Rebuild:

```bash
docker compose build --no-cache
docker compose up -d
```

### Warning: version is obsolete

**Penyebab:** `docker-compose.yml` masih pakai `version: '3.8'` yang sudah deprecated.

**Solusi:** Hapus baris `version: '3.8'` di `docker-compose.yml`.

### Port Sudah Dipakai

```bash
# Cek siapa yang pakai port 5008
sudo lsof -i :5008

# Ganti port di .env
NGINX_PORT=5009
```

### Database Locked

**Penyebab:** Concurrent write dari background thread dan request.

**Solusi:** Pastikan WAL mode aktif:

```bash
sqlite3 database/iot.db "PRAGMA journal_mode;"
# Harusnya: wal
```

### ESP32 Tidak Terhubung

**Checklist:**

1. Cek WiFi SSID dan password di firmware
2. Cek `API_URL` (IP server, port, dan `/api/v1/data`)
3. Cek `API_KEY` (harus sama dengan dashboard)
4. Cek `DEVICE_ID` (harus terdaftar)
5. Cek koneksi internet ESP32
6. Lihat serial monitor: `screen /dev/ttyUSB0 115200`

### Login Gagal (400 CSRF)

**Penyebab:** CSRF token tidak dikirim.

**Solusi:**

1. Cek `login.html` harus ada `<input type="hidden" name="csrf_token">`
2. Cek `base.html` harus ada `<meta name="csrf-token">`
3. Restart server, hard refresh browser (Ctrl+Shift+R)

### Session Hilang Setiap Restart

**Penyebab:** `SECRET_KEY` random setiap restart.

**Solusi:** Set `SECRET_KEY` permanen di `.env`:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Copy ke `.env` sebagai `SECRET_KEY`.

### Reset Database

```bash
# Backup dulu
cp database/iot.db backup/iot-manual-$(date +%Y%m%d).db

# Reset
rm database/iot.db database/iot.db-shm database/iot.db-wal
docker compose restart nexus-iot
```

---

## Monitoring & Maintenance

### Health Check Otomatis

```bash
# Cron job untuk cek setiap 5 menit
*/5 * * * * curl -f http://localhost:5000/health || echo "NEXUS down!" | mail -s "Alert" admin@example.com
```

### Backup Manual

```bash
make backup
```

Atau:

```bash
python -c "
import sqlite3
from datetime import datetime
src = sqlite3.connect('database/iot.db')
dst = sqlite3.connect(f'backup/manual-{datetime.now():%Y%m%d_%H%M%S}.db')
src.backup(dst)
dst.close()
src.close()
print('Done')
"
```

### Cek Log Error

```bash
# 24 jam terakhir
grep ERROR logs/nexus.log | tail -50

# Warning
grep WARNING logs/nexus.log | tail -50
```

### Performance Tuning

Kalau lambat:

1. Turunkan `DATA_RETENTION_DAYS` (default 30)
2. Tingkatkan `CHECK_INTERVAL` (default 60)
3. Batasi `per_page` di API pagination
4. Migrasi ke PostgreSQL untuk device lebih dari 100

---

## Changelog

### v3.0.1 (2026-09-12) - Docker Fix

**Fixed:**

- `PermissionError` saat Docker start, folder `/app/logs` tidak writeable
- Container unhealthy karena permission issue
- Warning `version` obsolete di `docker-compose.yml`
- Health check terlalu cepat timeout

**Added:**

- `docker-entrypoint.sh` untuk auto-fix permission dan drop privilege
- `.dockerignore` untuk exclude file yang tidak perlu
- Multi-stage Docker build dengan `gosu`
- Health check `start-period=60s`
- Dokumentasi troubleshooting Docker

**Changed:**

- Dockerfile pakai entrypoint script
- Dockerfile tidak set `USER nexus` langsung, entrypoint handle
- Docker Compose hapus `version` field

### v3.0 (2026-09-12) - Production Ready

**Added:**

- Application factory pattern
- Configurable port via `.env`
- CSRF protection
- Rate limiting (login 5/min, API 60/min)
- Input validation dengan Marshmallow
- Rotating file logging
- Health check endpoint
- Pagination untuk list devices
- Alert system dengan threshold
- Data retention dan auto cleanup
- Auto backup dengan retention
- Graceful shutdown
- API key regeneration
- Schema migration system
- Multi-stage Docker build
- Non-root Docker user
- Makefile untuk automation
- Centralized error handling

**Changed:**

- Refactor `app.py` ke blueprint pattern
- Thread-safe SQLite dengan WAL mode
- Centralized configuration di `config.py`
- Better logging dengan context
- Split templates ke partials

**Fixed:**

- Race condition di SQLite
- Session cookie security
- CORS terlalu permisif
- CSRF token missing di form
- Thread leak saat shutdown

### v2.0 - Initial Release

- Dashboard real-time
- Peta interaktif
- Multi-chart analytics
- Mobile UI
- Dark/Light theme
- ESP32 firmware
