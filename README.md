
# NEXUS IoT

Platform monitoring IoT real-time dengan dashboard web, peta interaktif, dan multi-chart analytics. Mendukung ESP32, ESP8266, Arduino, dan Raspberry Pi.

![Version](https://img.shields.io/badge/version-4.0-blue)
![Python](https://img.shields.io/badge/python-3.11+-green)
![License](https://img.shields.io/badge/license-MIT-yellow)

---

## Fitur

- **Dashboard real-time** — auto-refresh, health ring, status device
- **Peta interaktif** — lokasi device dengan Leaflet.js
- **Multi-chart analytics** — 10+ tipe visualisasi, drag & resize
- **Alert system** — threshold per sensor, lifecycle (healthy → warning → danger), notifikasi Telegram
- **Absensi RFID** — registrasi kartu, riwayat tap
- **Mobile UI** — bottom navigation, theme dark/light
- **Multi-device** — support ESP32, ESP8266, Arduino, Raspberry Pi
- **Production ready** — rate limiting, CSRF, auto backup, data retention

---

## Quick Start

### Docker (Recommended)

```bash
git clone https://github.com/takathena/nexus-iot.git
cd nexus-iot

cp .env.example .env
nano .env  # Set SECRET_KEY dan IOT_PASSWORD

mkdir -p database logs backup
chown -R 1000:1000 database logs backup

docker compose up -d --build
```

Akses: **http://localhost:5008**

### Manual (Development)

```bash
git clone https://github.com/takathena/nexus-iot.git
cd nexus-iot

make dev     # Setup venv + install deps + create .env
nano .env    # Set SECRET_KEY dan IOT_PASSWORD
make run     # Start dev server
```

Akses: **http://localhost:5000**

---

## Environment Variables

Copy `.env.example` ke `.env`, lalu minimal set ini:

```env
# WAJIB — generate dengan: python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=your-64-char-hex-secret-key
IOT_USERNAME=admin
IOT_PASSWORD=ganti-dengan-password-kuat

# Opsional
PORT=5000
NGINX_PORT=5008
DATA_RETENTION_DAYS=30
OFFLINE_TIMEOUT=900

# Telegram notifications (opsional)
NOTIFY_ENABLED=False
TELEGRAM_ENABLED=False
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

Semua variabel lain ada di `.env.example` dengan komentar.

---

## Setup Device (ESP32)

1. Tambah device di dashboard → catat **API Key** (hanya muncul sekali)
2. Edit `esp32/main.py`:

```python
WIFI_SSID = "NamaWiFi"
WIFI_PASSWORD = "PasswordWiFi"
API_URL = "http://IP-SERVER:5000/api/v1/data"
DEVICE_ID = "ESP32-001"
API_KEY = "api-key-dari-dashboard"
SENSOR_TYPE = "DHT22"
DHT_PIN = 4
SEND_INTERVAL = 60  # detik
```

3. Upload ke ESP32:

```bash
pip install adafruit-ampy
ampy --port /dev/ttyUSB0 put esp32/main.py
ampy --port /dev/ttyUSB0 reset
```

4. Monitor:

```bash
screen /dev/ttyUSB0 115200
```

---

## API Endpoints

| Endpoint | Method | Auth | Deskripsi |
|----------|--------|------|-----------|
| `/api/v1/data` | POST | API Key | Terima data device |
| `/api/v1/dashboard` | GET | Session | Data dashboard |
| `/api/v1/devices` | GET/POST | Session | List / tambah device |
| `/api/v1/devices/{id}` | GET/PUT/DELETE | Session | Detail / update / hapus |
| `/api/v1/devices/{id}/history` | GET | Session | Histori sensor |
| `/api/v1/alerts` | GET | Session | List alert aktif |
| `/api/v1/attendance` | GET | Session | Riwayat absensi |
| `/health` | GET | None | Health check |

**Kirim data dari device:**

```bash
curl -X POST http://localhost:5000/api/v1/data \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "ESP32-001",
    "api_key": "your-api-key",
    "sensor_type": "DHT22",
    "data": {"temperature": 25.5, "humidity": 60.0}
  }'
```

---

## Struktur Project

```
nexus-iot/
├── app/                    # Application package
│   ├── __init__.py         # App factory
│   ├── api.py              # API routes
│   ├── auth.py             # Authentication
│   ├── views.py            # Web views
│   ├── alerts.py           # Alert system
│   ├── background.py       # Background tasks
│   ├── database.py         # DB layer + migrations
│   ├── notifier.py         # Telegram notifier
│   └── ...
├── templates/              # Jinja2 templates
├── static/                 # CSS & JS
├── esp32/                  # ESP32 firmware
├── nginx/                  # Nginx config
├── run.py                  # Entry point
├── Dockerfile
├── docker-compose.yml
├── Makefile
└── requirements.txt
```

---

## Commands

```bash
make dev              # Setup environment
make run              # Dev server
make run-prod         # Production (Gunicorn)
make test             # Test health endpoint
make backup           # Backup database
make clean            # Clean venv & cache

make docker-build     # Build image
make docker-up        # Start container
make docker-down      # Stop container
make docker-logs      # Live logs
make docker-rebuild   # Rebuild from scratch
make docker-shell     # Shell ke container
```

---

## Deploy Production

### Docker (Recommended)

```bash
# Di server
git clone https://github.com/takathena/nexus-iot.git
cd nexus-iot
cp .env.example .env
nano .env

mkdir -p database logs backup
chown -R 1000:1000 database logs backup

docker compose up -d --build
```

### Systemd (Bare Metal)

```bash
# 1. Setup user & folder
sudo useradd -r -s /bin/false nexus
sudo mkdir -p /opt/nexus-iot
sudo chown nexus:nexus /opt/nexus-iot

# 2. Install
cd /opt/nexus-iot
sudo -u nexus git clone https://github.com/takathena/nexus-iot.git .
sudo -u nexus python3 -m venv venv
sudo -u nexus venv/bin/pip install -r requirements.txt
sudo -u nexus cp .env.example .env
sudo nano .env

# 3. Systemd service
sudo nano /etc/systemd/system/nexus-iot.service
```

Isi service file:

```ini
[Unit]
Description=NEXUS IoT Platform
After=network.target

[Service]
Type=simple
User=nexus
Group=nexus
WorkingDirectory=/opt/nexus-iot
Environment="PATH=/opt/nexus-iot/venv/bin"
ExecStart=/opt/nexus-iot/venv/bin/gunicorn -w 4 -k gthread --threads 4 -b 0.0.0.0:5000 run:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable nexus-iot
sudo systemctl start nexus-iot
sudo systemctl status nexus-iot
```

---

## Troubleshooting

**Permission denied di Docker:**
```bash
docker compose down
chown -R 1000:1000 database logs backup
docker compose up -d
```

**Container unhealthy:**
```bash
docker compose logs nexus-iot | tail -50
```

**Login gagal (CSRF error):**
Hard refresh browser (Ctrl+Shift+R).

**Session hilang setiap restart:**
Set `SECRET_KEY` permanen di `.env`.

**Database locked:**
```bash
sqlite3 database/iot.db "PRAGMA journal_mode;"
# Harus: wal
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Flask 3.1, Python 3.11 |
| Database | SQLite (WAL mode) |
| Frontend | Vanilla JS, Chart.js 4.4, Leaflet 1.9 |
| Server | Gunicorn 21.2 |
| Container | Docker, Docker Compose |

---

## License

MIT — lihat [LICENSE](LICENSE)