"""
Universal IoT Monitoring Platform - ESP32 DHT22
Device: ESP32 | Sensor: DHT22 | Firmware: MicroPython
Timezone: Asia/Jakarta (WIB, UTC+7)
"""

import machine
import dht
import time
import network
import urequests
import ujson
import gc
import ntptime

# ============ KONFIGURASI ============
WIFI_SSID = ""
WIFI_PASSWORD = ""
API_URL = ""
DEVICE_ID = "100"
API_KEY = ""
SENSOR_TYPE = ""
DHT_PIN = 4
SEND_INTERVAL = 600
TIMEZONE_OFFSET = 7 * 3600  # WIB (UTC+7)

# ============ INISIALISASI ============
dht_sensor = dht.DHT22(machine.Pin(DHT_PIN))
wlan = network.WLAN(network.STA_IF)
start_time = time.time()  # Untuk hitung uptime

# ============ FUNGSI UTAMA ============
def connect_wifi():
    """Koneksi WiFi"""
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        timeout = 20
        while not wlan.isconnected() and timeout > 0:
            time.sleep(1)
            timeout -= 1
    return wlan.isconnected()

def sync_time():
    """Sinkronisasi NTP"""
    try:
        ntptime.settime()
    except:
        pass

def get_local_time():
    """Waktu WIB"""
    return time.localtime(time.mktime(time.localtime()) + TIMEZONE_OFFSET)

def format_datetime(t):
    """Format datetime"""
    return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(t[0], t[1], t[2], t[3], t[4], t[5])

def get_uptime():
    """Hitung uptime dalam detik"""
    return int(time.time() - start_time)

def read_dht22():
    """Baca sensor DHT22"""
    try:
        dht_sensor.measure()
        return {
            "temperature": round(dht_sensor.temperature(), 1),
            "humidity": round(dht_sensor.humidity(), 1)
        }
    except:
        return None

def send_data(sensor_data):
    """Kirim data ke server"""
    payload = {
        "device_id": DEVICE_ID,
        "api_key": API_KEY,
        "sensor_type": SENSOR_TYPE,
        "wifi_ssid": WIFI_SSID,
        "uptime_seconds": get_uptime(),
        "data": sensor_data
    }
    
    try:
        response = urequests.post(
            API_URL,
            data=ujson.dumps(payload),
            headers={"Content-Type": "application/json"}
        )
        status = response.status_code
        response.close()
        return status == 200
    except:
        return False

# ============ MAIN LOOP ============
def main():
    print("=" * 50)
    print("ESP32 DHT22 Monitor")
    print("Device ID: {}".format(DEVICE_ID))
    print("=" * 50)
    
    if not connect_wifi():
        machine.reset()
    
    sync_time()
    print("WiFi: {} | IP: {}".format(WIFI_SSID, wlan.ifconfig()[0]))
    print("Mulai monitoring...")
    
    while True:
        try:
            sensor_data = read_dht22()
            
            if sensor_data:
                t = get_local_time()
                print("[{}] Suhu: {}C | Hum: {}% | Uptime: {}s".format(
                    format_datetime(t),
                    sensor_data["temperature"],
                    sensor_data["humidity"],
                    get_uptime()
                ))
                
                if send_data(sensor_data):
                    print("-> Data terkirim")
                else:
                    print("-> Gagal kirim")
            else:
                print("-> Gagal baca sensor")
            
            gc.collect()
            time.sleep(SEND_INTERVAL)
            
        except Exception as e:
            print("Error: {}".format(e))
            time.sleep(5)
            machine.reset()

if __name__ == "__main__":
    main()
