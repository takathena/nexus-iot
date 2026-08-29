Baik! Berikut **README.md** lengkap untuk project NEXUS IoT Platform:

---

```markdown
# NEXUS IoT - Universal IoT Monitoring Platform

Platform monitoring IoT universal dengan dashboard real-time, peta interaktif, dan multi-chart analytics. Dibangun menggunakan Flask, Chart.js, dan Leaflet.js.

![Version](https://img.shields.io/badge/version-2.0-blue)
![Python](https://img.shields.io/badge/python-3.8+-green)
![Flask](https://img.shields.io/badge/flask-2.0+-red)
![License](https://img.shields.io/badge/license-MIT-yellow)

---

## 📋 DAFTAR ISI

- [Fitur](#-fitur)
- [Arsitektur](#-arsitektur)
- [Prasyarat](#-prasyarat)
- [Instalasi](#-instalasi)
- [Konfigurasi](#-konfigurasi)
- [Penggunaan](#-penggunaan)
- [API Endpoints](#-api-endpoints)
- [Setup ESP32](#-setup-esp32)
- [Deploy ke Proxmox LXC](#-deploy-ke-proxmox-lxc)
- [Troubleshooting](#-troubleshooting)
- [Lisensi](#-lisensi)

---

## ✨ FITUR

- 🔐 **Sistem Login** - Autentikasi sebelum masuk dashboard
- 📊 **Dashboard Real-time** - Monitoring semua perangkat dalam satu tampilan
- 🗺️ **Peta Interaktif** - Lokasi perangkat dengan Leaflet.js
- 📈 **Multi Chart** - Grafik gabungan + 2 grafik individual per perangkat
- 📱 **Responsive** - Tampilan khusus mobile/tablet dengan auto-detection
- 🔄 **Auto-deteksi Online/Offline** - Device dianggap offline jika tidak kirim data dalam 15 menit
- 🔑 **API Key per Device** - Setiap perangkat memiliki API key unik
- 📡 **Multi-Sensor Support** - DHT22, MQ Sensor, dan sensor lainnya
- ⏰ **Timezone WIB** - Waktu Jakarta (UTC+7)
- 🎨 **Dark Theme** - Tampilan gelap modern dengan glassmorphism

---

## 🏗️ ARSITEKTUR

```
ESP32/ESP8266/Raspberry Pi
           │
           ▼
      WiFi/Internet
           │
           ▼
   Cloudflare Tunnel (Opsional)
           │
           ▼
   Flask API Server (Port 5000)
           │
           ├── Database (SQLite)
           │
           ├── Dashboard Desktop
           │
           ├── Mobile Dashboard
           │
           └── REST API Endpoints
```

---

## 📋 PRASYARAT

### Server:
- Linux (Ubuntu 20.04+ / 22.04 / 24.04)
- Python 3.8+
- pip
- systemd (untuk service)
- Cloudflared (opsional, untuk akses publik)

### Perangkat IoT:
- ESP32 / ESP8266
- Sensor (DHT22, MQ-2, dll)
- MicroPython firmware

---

## 🛠️ INSTALASI

### 1. Clone Repository

```bash
git clone https://github.com/takathena/nexus-iot.git
cd nexus-iot
```

### 2. Buat Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Buat File .env

```bash
cp .env.example .env
nano .env
```

Isi:

```env
SECRET_KEY=ubah-dengan-random-secret-key
IOT_USERNAME=admin
IOT_PASSWORD=admin123
```

Generate secret key:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 5. Inisialisasi Database

```bash
mkdir -p database
python database.py
```

### 6. Jalankan Aplikasi

```bash
python app.py
```

Akses: `http://localhost:5000`

---

## ⚙️ KONFIGURASI

### Login Default:
- **Username:** `admin`
- **Password:** `admin123`

> ⚠️ **Ubah di file `.env` sebelum production!**

### Waktu Offline:
- Default: **15 menit** (900 detik)
- Ubah di `app.py`: `OFFLINE_TIMEOUT = 900`

### Interval Kirim Data ESP32:
- Default: **5 menit** (300 detik)
- Ubah di `esp32/main.py`: `SEND_INTERVAL = 300`

---

## 📖 PENGGUNAAN

### 1. Login

1. Buka `http://localhost:5000/login`
2. Masukkan username dan password
3. Klik "Masuk"

### 2. Tambah Perangkat

1. Klik tombol **"Tambah"** di topbar
2. Isi form:
   - **Device ID:** Contoh: `ESP32-001`
   - **Nama:** Contoh: `Sensor Suhu Ruangan`
   - **Tipe:** ESP32 / ESP8266 / Arduino / Raspberry Pi
   - **Lokasi:** Contoh: `Ruang Server` (opsional)
3. Klik **"Simpan"**
4. **API Key akan muncul - SIMPAN!** (hanya muncul sekali)

### 3. Setup ESP32

Lihat [Setup ESP32](#-setup-esp32)

### 4. Monitoring Dashboard

- **Dashboard:** Ringkasan statistik, daftar perangkat, peta lokasi
- **Peta:** Klik peta untuk set lokasi perangkat
- **Analitik:** Grafik gabungan semua perangkat + 2 grafik individual
- **Perangkat:** Tabel semua perangkat dengan aksi

### 5. Mobile Dashboard

Buka dari HP/tablet, otomatis redirect ke tampilan mobile dengan bottom navigation.

---

## 🔌 API ENDPOINTS

### Data Endpoint (Untuk ESP32)

```
POST /api/v1/data
```

**Format JSON:**

```json
{
    "device_id": "ESP32-001",
    "api_key": "your-api-key",
    "sensor_type": "DHT22",
    "wifi_ssid": "WiFi-Name",
    "uptime_seconds": 3600,
    "data": {
        "temperature": 29.4,
        "humidity": 68.0
    }
}
```

**Response Sukses:**

```json
{
    "success": true,
    "message": "Data received",
    "timestamp": "2026-08-29T10:00:00+07:00"
}
```

### Device Management

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/api/v1/devices` | List semua device |
| POST | `/api/v1/devices` | Tambah device baru |
| GET | `/api/v1/devices/{id}` | Detail device |
| PUT | `/api/v1/devices/{id}` | Update device |
| DELETE | `/api/v1/devices/{id}` | Hapus device |

### Data History

```
GET /api/v1/devices/{id}/history?hours=24
```

### Dashboard Summary

```
GET /api/v1/dashboard
```

---

## 📟 SETUP ESP32

### 1. Flash MicroPython

1. Download Thonny IDE dari [thonny.org](https://thonny.org)
2. Install driver USB ESP32 (CH340/CP2102)
3. Download firmware dari [micropython.org](https://micropython.org/download/esp32/)
4. Flash firmware via Thonny: `Tools → Options → Interpreter → Install or update MicroPython`

### 2. Upload Kode

1. Buka `esp32/main.py`
2. Update konfigurasi:

```python
WIFI_SSID = "NAMA_WIFI_ANDA"
WIFI_PASSWORD = "PASSWORD_WIFI_ANDA"
API_URL = "https://domain-anda.com/api/v1/data"
DEVICE_ID = "ESP32-001"  # Sesuai yang didaftarkan di dashboard
API_KEY = "API_KEY_DARI_DASHBOARD"  # API key dari dashboard
SENSOR_TYPE = "DHT22"
DHT_PIN = 4  # GPIO4
SEND_INTERVAL = 300  # 5 menit
```

3. Simpan ke ESP32 dengan nama `main.py`

### 3. Wiring DHT22

```
ESP32       DHT22
-----       ------
3.3V   -->  VCC (+)
GND    -->  GND (-)
GPIO4  -->  DATA (out)
```

### 4. Test

Serial monitor akan menampilkan:

```text
ESP32 DHT22 Monitor
WiFi: Connected
Suhu: 29.4C | Hum: 68.0%
-> Data terkirim
```

---

## 🚀 DEPLOY KE PROXMOX LXC

### 1. Buat Container

```
CT ID: (otomatis)
Hostname: nexus-iot
Template: ubuntu-24.04-standard
CPU: 1-2 core
RAM: 512MB - 1GB
Disk: 8GB
```

### 2. Setup di Container

```bash
# Update system
apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv

# Buat folder
mkdir -p /opt/nexus-iot

# Clone dari GitHub
cd /opt/nexus-iot
git clone https://github.com/takathena/nexus-iot.git .

# Setup venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Buat .env
cp .env.example .env
nano .env  # Edit username & password

# Init database
python database.py

# Buat service
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

# Start service
systemctl daemon-reload
systemctl enable nexus-iot.service
systemctl start nexus-iot.service
```

---

## 🔍 TROUBLESHOOTING

### Service tidak berjalan

```bash
journalctl -u nexus-iot.service -n 50 --no-pager
```

### Database error

```bash
cd /opt/nexus-iot
python database.py
```

### Permission denied saat install pip

```bash
sudo chown -R $USER:$USER /opt/nexus-iot
```

### ESP32 tidak terhubung

- Cek WiFi credentials
- Cek API URL
- Cek API Key
- Cek koneksi internet

### Device selalu offline

- Cek `OFFLINE_TIMEOUT` di `app.py` (default: 900 detik)
- Pastikan ESP32 mengirim data dengan interval yang benar
- Cek log service

---

## 📁 STRUKTUR PROJECT

```
nexus-iot/
│
├── app.py                  # Main Flask application
├── database.py             # Database setup
├── requirements.txt        # Python dependencies
├── .env.example            # Template environment variables
├── .gitignore              # Git ignore rules
├── README.md               # Dokumentasi
├── LICENSE                 # Lisensi MIT
│
├── esp32/
│   └── main.py             # Kode ESP32 DHT22
│
├── templates/
│   ├── login.html          # Halaman login
│   ├── dashboard.html      # Dashboard desktop
│   ├── mobile.html         # Dashboard mobile
│   └── device_detail.html  # Detail perangkat
│
└── database/
    └── iot.db              # SQLite database (auto-generated)
```

---

## 🤝 KONTRIBUSI

Silakan buat pull request atau laporkan issue!

---

## 📄 LISENSI

MIT License - Lihat file [LICENSE](LICENSE)

---

## 🙏 CREDITS

- **Flask** - Web framework
- **Leaflet.js** - Peta interaktif
- **Chart.js** - Visualisasi data
- **Font Awesome** - Ikon
- **Plus Jakarta Sans** - Font

---

## 📞 KONTAK

- GitHub: [takathena](https://github.com/takathena)
- Website: [iot.takathena.my.id](https://iot.takathena.my.id)

---

## 🚀 QUICK START

```bash
git clone https://github.com/takathena/nexus-iot.git
cd nexus-iot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Buka `http://localhost:5000` | Login: `admin` / `admin123`
```

---

Simpan sebagai `README.md` di folder project kamu! Ini dokumentasi lengkap yang siap di-upload ke GitHub.
