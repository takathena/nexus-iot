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
WIFI_SSID = "peo"
WIFI_PASSWORD = "12345678"
API_URL = "http://192.168.1.6:5008/api/v1/data"
DEVICE_ID = "1"
API_KEY = "01394efb170d74fae7ea5d424aac98e5a6c67f20e9b265636b354c2acac4f660"
SENSOR_TYPE = "DHT22"
DHT_PIN = 4
SEND_INTERVAL = 5
TIMEZONE_OFFSET = 7 * 3600

# ============ INISIALISASI ============
dht_sensor = dht.DHT22(machine.Pin(DHT_PIN))
wlan = network.WLAN(network.STA_IF)
boot_ticks = time.ticks_ms()


def connect_wifi():
    wlan.active(True)
    if not wlan.isconnected():
        print("[WiFi] Connecting to {}...".format(WIFI_SSID))
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        timeout = 20
        while not wlan.isconnected() and timeout > 0:
            time.sleep(1)
            timeout -= 1
    if wlan.isconnected():
        print("[WiFi] Connected! IP: {}".format(wlan.ifconfig()[0]))
    else:
        print("[WiFi] FAILED to connect!")
    return wlan.isconnected()


def sync_time():
    try:
        ntptime.settime()
        print("[NTP] Time synced")
    except Exception as e:
        print("[NTP] Failed: {}".format(e))


def get_local_time():
    try:
        epoch_utc = time.time()
        return time.localtime(epoch_utc + TIMEZONE_OFFSET)
    except Exception as e:
        print("[TIME] Error: {}".format(e))
        return time.localtime()


def format_datetime(t):
    return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
        t[0], t[1], t[2], t[3], t[4], t[5]
    )


def get_uptime():
    return time.ticks_diff(time.ticks_ms(), boot_ticks) // 1000


def read_dht22():
    try:
        dht_sensor.measure()
        return {
            "temperature": round(dht_sensor.temperature(), 1),
            "humidity": round(dht_sensor.humidity(), 1)
        }
    except Exception as e:
        print("[DHT22] Read error: {}".format(e))
        return None


def send_data(sensor_data):
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
        body = response.text
        response.close()

        if status == 200:
            return True
        else:
            print("[HTTP] Status: {} | Body: {}".format(status, body[:150]))
            return False

    except OSError as e:
        print("[HTTP] Network error: {}".format(e))
        return False
    except Exception as e:
        print("[HTTP] Error: {} | Type: {}".format(e, type(e).__name__))
        return False


def main():
    print("=" * 60)
    print("ESP32 DHT22 Monitor")
    print("Device ID: {}".format(DEVICE_ID))
    print("API URL  : {}".format(API_URL))
    print("=" * 60)

    if not connect_wifi():
        print("WiFi gagal, restart...")
        machine.reset()

    sync_time()
    print("\n--- Starting main loop ---")

    success_count = 0
    fail_count = 0
    consecutive_fails = 0

    while True:
        try:
            sensor_data = read_dht22()

            if sensor_data:
                t = get_local_time()
                print("\n[{}] Suhu: {}C | Hum: {}% | Uptime: {}s".format(
                    format_datetime(t),
                    sensor_data["temperature"],
                    sensor_data["humidity"],
                    get_uptime()
                ))

                if send_data(sensor_data):
                    success_count += 1
                    consecutive_fails = 0
                    print("-> OK Terkirim (ok: {}, fail: {})".format(success_count, fail_count))
                else:
                    fail_count += 1
                    consecutive_fails += 1
                    print("-> Gagal (ok: {}, fail: {})".format(success_count, fail_count))

                    if consecutive_fails >= 5:
                        print("[WiFi] Too many failures, reconnecting...")
                        try:
                            wlan.disconnect()
                        except:
                            pass
                        time.sleep(2)
                        connect_wifi()
                        consecutive_fails = 0
            else:
                print("-> Gagal baca sensor")

            gc.collect()
            time.sleep(SEND_INTERVAL)

        except Exception as e:
            print("[MAIN] Error: {} | Type: {}".format(e, type(e).__name__))
            time.sleep(5)


if __name__ == "__main__":
    main()
