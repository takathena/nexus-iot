# NEXUS IoT - Universal IoT Monitoring Platform

Platform monitoring IoT dengan dashboard real-time, peta interaktif, dan multi-chart analytics. Dibangun menggunakan Flask, Chart.js, dan Leaflet.js.

![Version](https://img.shields.io/badge/version-2.3-blue)
![Python](https://img.shields.io/badge/python-3.8+-green)
![Flask](https://img.shields.io/badge/flask-2.0+-red)
![License](https://img.shields.io/badge/license-MIT-yellow)

---

## Fitur

- 🔐 **Sistem Login** - Autentikasi sebelum masuk dashboard
- 📊 **Dashboard Real-time** - Monitoring semua perangkat dalam satu tampilan
- 🗺️ **Peta Interaktif** - Lokasi perangkat dengan Leaflet.js
- 📈 **Multi Chart** - Grafik gabungan + grafik individual per perangkat
- 📱 **Responsive** - Tampilan khusus mobile/tablet
- 🔄 **Auto-deteksi Online/Offline** - Offline jika tidak kirim data dalam 15 menit
- 🔑 **API Key per Device** - Setiap perangkat memiliki API key unik
- ⏰ **Timezone WIB** - Waktu Jakarta (UTC+7)

---

## Instalasi

### 1. Clone Repository

```bash
git clone https://github.com/takathena/nexus-iot.git
cd nexus-iot
```

### 2. Setup Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Konfigurasi

```bash
cp .env.example .env
nano .env
```

Isi file `.env`:
```env
IOT_USERNAME=admin
IOT_PASSWORD=admin123
```

Generate secret key:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 4. Inisialisasi Database

```bash
python database.py
```

### 5. Jalankan

```bash
python app.py
```

Akses: `http://localhost:5000` | Login: `admin` / `admin123`

---

## API Endpoints

### Kirim Data (ESP32)

```
POST /api/v1/data
```

```json
{
    "device_id": "ESP32-001",
    "api_key": "your-api-key",
    "sensor_type": "DHT22",
    "data": {
        "temperature": 29.4,
        "humidity": 68.0
    }
}
```

### Management Device

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/api/v1/devices` | List semua device |
| POST | `/api/v1/devices` | Tambah device |
| GET | `/api/v1/devices/{id}` | Detail device |
| PUT | `/api/v1/devices/{id}` | Update device |
| DELETE | `/api/v1/devices/{id}` | Hapus device |

### Lainnya

```
GET /api/v1/devices/{id}/history?hours=24
GET /api/v1/dashboard
```

---

## Setup ESP32

### Konfigurasi

Buka `esp32/main.py` dan sesuaikan:

```python
WIFI_SSID = "NAMA_WIFI"
WIFI_PASSWORD = "PASSWORD_WIFI"
API_URL = "http://server-ip:5000/api/v1/data"
DEVICE_ID = "ESP32-001"
API_KEY = "API_KEY_DARI_DASHBOARD"
SENSOR_TYPE = "DHT22"
DHT_PIN = 4
SEND_INTERVAL = 300  # 5 menit
```

### Wiring DHT22

```
ESP32       DHT22
-----       ------
3.3V   -->  VCC
GND    -->  GND
GPIO4  -->  DATA
```

---

## Deploy ke Proxmox LXC

### 1. Buat Container

```
Template: ubuntu-24.04-standard
CPU: 1-2 core | RAM: 512MB-1GB | Disk: 8GB
```

### 2. Setup

```bash
apt update && apt install -y python3 python3-pip python3-venv git

cd /opt
git clone https://github.com/takathena/nexus-iot.git
cd nexus-iot

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env  # Edit username & password

python database.py
```

### 3. Buat Systemd Service

```bash
cat > /etc/systemd/system/nexus-iot.service << 'EOF'
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
EOF

systemctl daemon-reload
systemctl enable nexus-iot.service
systemctl start nexus-iot.service
```

---

## Troubleshooting

### Service Error
```bash
journalctl -u nexus-iot.service -n 50 --no-pager
```

### Reset Database
```bash
rm -rf database/iot.db
python database.py
```

### ESP32 Tidak Terhubung
- Cek WiFi dan API URL
- Pastikan API Key benar
- Cek koneksi internet

---

## Struktur Project

```
nexus-iot/
├── app.py
├── database.py
├── requirements.txt
├── .env.example
├── esp32/
│   └── main.py
├── templates/
│   ├── login.html
│   ├── dashboard.html
│   ├── mobile.html
│   └── device_detail.html
└── database/
    └── iot.db
```

---

## Lisensi

MIT License - Lihat file [LICENSE](LICENSE)

---

## Kontak

- GitHub: [takathena](https://github.com/takathena)
- Website: [iot.takathena.my.id](https://iot.takathena.my.id)
