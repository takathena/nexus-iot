"""
NEXUS IoT - 10-Minute Full Alert Test
======================================

Simulator ini test SEMUA fitur alerting dalam 10 menit:

  Fase 1 (0-2 menit)  : HEALTHY      — suhu normal, tidak ada alert
  Fase 2 (2-4 menit)  : WARNING      — suhu mulai naik (alert warning)
  Fase 3 (4-6 menit)  : DANGER       — suhu tinggi (alert danger)
  Fase 4 (6-7 menit)  : RECOVERY     — suhu turun perlahan (alert clear)
  Fase 5 (7-8 menit)  : HIGH HUMID   — kelembaban tinggi (alert baru)
  Fase 6 (8-9 menit)  : NORMAL       — semua normal lagi
  Fase 7 (9-10 menit) : OFFLINE SIM  — stop kirim, tunggu offline alert

Cara pakai:
    1. Set DEVICE_ID & API_KEY di bawah
    2. python simulator/demo_10min.py
    3. Buka dashboard, lihat alert muncul/hilang sesuai fase
"""
import sys
import time
import math
import random
from datetime import datetime

try:
    import requests
except ImportError:
    print("❌ Install dulu: pip install requests")
    sys.exit(1)


# ==========================================
# KONFIGURASI — EDIT INI
# ==========================================
API_URL = "http://localhost:5000/api/v1/data"
DEVICE_ID = "ESP-DEMO-001"
API_KEY = "8c2754111f2ec4580e87b0ad9ca84c01f121b250b4bb992be94f691117fb7c9b"

SENSOR_TYPE = "DHT22"
WIFI_SSID = "gendis"
WIFI_PASSWORD = "arekmbois"

# Interval kirim data (detik). 10 detik = 60 data dalam 10 menit.
SEND_INTERVAL = 10

# Durasi tiap fase (detik)
PHASE_DURATIONS = {
    "healthy":     120,   # 0-2 menit
    "warning":     120,   # 2-4 menit
    "danger":      120,   # 4-6 menit
    "recovery":     60,   # 6-7 menit
    "high_humid":   60,   # 7-8 menit
    "normal":       60,   # 8-9 menit
    "offline":      60,   # 9-10 menit (stop kirim, tunggu offline)
}

# Threshold device — HARUS SAMA dengan yang di-set di dashboard!
# Format: {sensor: {severity: {min, max}}}
ALERT_RULES = {
    "temperature": {
        "healthy": {"min": 20, "max": 26},
        "warning": {"min": 15, "max": 30},
        "danger":  {"min": 10, "max": 35},
    },
    "humidity": {
        "healthy": {"min": 40, "max": 70},
        "warning": {"min": 30, "max": 80},
        "danger":  {"min": 20, "max": 90},
    },
}


# ==========================================
# COLORS
# ==========================================
class C:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'


# ==========================================
# SEVERITY HELPER
# ==========================================
def get_severity(sensor, value):
    """Tentukan severity berdasarkan value & ALERT_RULES"""
    rule = ALERT_RULES.get(sensor)
    if not rule:
        return "unknown"

    # Cek danger dulu
    danger = rule.get("danger")
    if danger and (value < danger["min"] or value > danger["max"]):
        return "danger"

    warning = rule.get("warning")
    if warning and (value < warning["min"] or value > warning["max"]):
        return "warning"

    healthy = rule.get("healthy")
    if healthy and (value < healthy["min"] or value > healthy["max"]):
        return "warning"  # default fallback

    return "healthy"


def severity_color(sev):
    return {
        "healthy": C.GREEN,
        "warning": C.YELLOW,
        "danger": C.RED,
    }.get(sev, C.WHITE)


def severity_badge(sev):
    return {
        "healthy": f"{C.BG_GREEN}{C.WHITE} ✓ HEALTHY {C.RESET}",
        "warning": f"{C.BG_YELLOW}{C.WHITE} ⚠ WARNING {C.RESET}",
        "danger":  f"{C.BG_RED}{C.WHITE} 🔥 DANGER {C.RESET}",
    }.get(sev, sev)


# ==========================================
# DATA GENERATOR PER FASE
# ==========================================
def gen_healthy(step):
    """Suhu 22-24°C (dalam healthy range 20-26)"""
    return {
        "temperature": round(22 + math.sin(step / 10) * 1.5 + random.uniform(-0.3, 0.3), 2),
        "humidity": round(55 + random.uniform(-3, 3), 2),
    }


def gen_warning(step):
    """Suhu 28-30°C (di luar healthy, dalam warning 15-30)"""
    return {
        "temperature": round(28 + random.uniform(-0.5, 1.5), 2),
        "humidity": round(60 + random.uniform(-3, 3), 2),
    }


def gen_danger(step):
    """Suhu 36-40°C (di luar warning, danger)"""
    return {
        "temperature": round(37 + random.uniform(-1, 3), 2),
        "humidity": round(60 + random.uniform(-3, 3), 2),
    }


def gen_recovery(step):
    """Suhu turun perlahan dari 35 → 22"""
    # Mulai 35, turun 0.7°C per step
    temp = max(22, 35 - step * 0.7)
    return {
        "temperature": round(temp + random.uniform(-0.3, 0.3), 2),
        "humidity": round(60 + random.uniform(-3, 3), 2),
    }


def gen_high_humid(step):
    """Kelembaban 85-95% (di luar healthy 40-70, danger >90)"""
    return {
        "temperature": round(24 + random.uniform(-0.5, 0.5), 2),
        "humidity": round(88 + random.uniform(-3, 5), 2),
    }


def gen_normal(step):
    """Semua normal lagi"""
    return {
        "temperature": round(23 + random.uniform(-0.5, 0.5), 2),
        "humidity": round(55 + random.uniform(-2, 2), 2),
    }


# ==========================================
# FASE DEFINITION
# ==========================================
PHASES = [
    {
        "name": "HEALTHY",
        "desc": "Suhu normal (22-24°C) — tidak ada alert",
        "color": C.GREEN,
        "gen": gen_healthy,
        "duration": PHASE_DURATIONS["healthy"],
    },
    {
        "name": "WARNING",
        "desc": "Suhu naik (28-30°C) — alert WARNING aktif",
        "color": C.YELLOW,
        "gen": gen_warning,
        "duration": PHASE_DURATIONS["warning"],
    },
    {
        "name": "DANGER",
        "desc": "Suhu tinggi (37-40°C) — alert DANGER aktif",
        "color": C.RED,
        "gen": gen_danger,
        "duration": PHASE_DURATIONS["danger"],
    },
    {
        "name": "RECOVERY",
        "desc": "Suhu turun perlahan (35→22°C) — alert CLEAR",
        "color": C.CYAN,
        "gen": gen_recovery,
        "duration": PHASE_DURATIONS["recovery"],
    },
    {
        "name": "HIGH HUMIDITY",
        "desc": "Kelembaban tinggi (88-93%) — alert DANGER humidity",
        "color": C.MAGENTA,
        "gen": gen_high_humid,
        "duration": PHASE_DURATIONS["high_humid"],
    },
    {
        "name": "BACK TO NORMAL",
        "desc": "Semua parameter normal — semua alert clear",
        "color": C.GREEN,
        "gen": gen_normal,
        "duration": PHASE_DURATIONS["normal"],
    },
    {
        "name": "OFFLINE TEST",
        "desc": "Berhenti kirim data — tunggu offline alert",
        "color": C.RED,
        "gen": None,  # Tidak kirim data
        "duration": PHASE_DURATIONS["offline"],
    },
]


# ==========================================
# SEND DATA
# ==========================================
def send_data(sensor_data, uptime):
    payload = {
        "device_id": DEVICE_ID,
        "api_key": API_KEY,
        "sensor_type": SENSOR_TYPE,
        "wifi_ssid": WIFI_SSID,
        "uptime_seconds": uptime,
        "data": sensor_data,
    }
    try:
        r = requests.post(API_URL, json=payload, timeout=10)
        return r.status_code == 200, r.json() if r.status_code == 200 else r.text[:150]
    except requests.exceptions.ConnectionError:
        return False, "Connection refused"
    except requests.exceptions.Timeout:
        return False, "Timeout"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# ==========================================
# DISPLAY
# ==========================================
def print_banner():
    print(f"\n{C.CYAN}{'═' * 78}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  🧪  NEXUS IoT — 10-Minute Full Alert Test{C.RESET}")
    print(f"{C.CYAN}{'═' * 78}{C.RESET}")
    print(f"  {C.DIM}Server     :{C.RESET} {API_URL}")
    print(f"  {C.DIM}Device     :{C.RESET} {C.BOLD}{DEVICE_ID}{C.RESET}")
    print(f"  {C.DIM}Interval   :{C.RESET} {SEND_INTERVAL}s")
    print(f"  {C.DIM}Total time :{C.RESET} ~10 menit")
    print(f"{C.CYAN}{'═' * 78}{C.RESET}\n")

    # Print threshold reference
    print(f"{C.BOLD}📋 Threshold yang digunakan (pastikan SAMA dengan dashboard!):{C.RESET}")
    for sensor, rules in ALERT_RULES.items():
        print(f"  {C.CYAN}{sensor}{C.RESET}")
        for sev in ["healthy", "warning", "danger"]:
            r = rules.get(sev, {})
            color = severity_color(sev)
            print(f"    {color}{sev:>8}{C.RESET}: "
                  f"{r.get('min', '?'):>5} — {r.get('max', '?'):<5}")
    print()


def print_phase_header(phase, idx, total):
    print(f"\n{C.BOLD}{phase['color']}{'━' * 78}{C.RESET}")
    print(f"{C.BOLD}{phase['color']}  ▶ FASE {idx}/{total}: {phase['name']}{C.RESET}")
    print(f"{C.DIM}  {phase['desc']}{C.RESET}")
    print(f"{C.DIM}  Durasi: {phase['duration']}s{C.RESET}")
    print(f"{C.BOLD}{phase['color']}{'━' * 78}{C.RESET}\n")


def format_row(ts, sensor_data, ok, duration_left):
    if sensor_data is None:
        return f"  [{C.DIM}{ts}{C.RESET}]  {C.RED}⏸  (skip){C.RESET}"

    temp = sensor_data.get("temperature")
    hum = sensor_data.get("humidity")

    temp_sev = get_severity("temperature", temp) if temp is not None else "?"
    hum_sev = get_severity("humidity", hum) if hum is not None else "?"

    temp_str = f"{severity_color(temp_sev)}{temp:>6.2f}°C{C.RESET}"
    hum_str = f"{severity_color(hum_sev)}{hum:>6.2f}%{C.RESET}"

    # Overall severity: yang paling bahaya
    sev_rank = {"healthy": 0, "warning": 1, "danger": 2}
    overall = max([temp_sev, hum_sev], key=lambda s: sev_rank.get(s, -1))

    status = f"{C.GREEN}✅{C.RESET}" if ok else f"{C.RED}❌{C.RESET}"
    badge = severity_badge(overall)

    return f"  [{C.DIM}{ts}{C.RESET}]  {status}  {temp_str}  {hum_str}  {badge}  {C.DIM}({duration_left}s){C.RESET}"


# ==========================================
# MAIN LOOP
# ==========================================
def run_demo():
    print_banner()

    start_time = time.time()
    step = 0
    success_count = 0
    fail_count = 0

    total_phases = len(PHASES)

    for phase_idx, phase in enumerate(PHASES, 1):
        print_phase_header(phase, phase_idx, total_phases)

        phase_start = time.time()
        phase_step = 0

        while True:
            elapsed_in_phase = time.time() - phase_start
            if elapsed_in_phase >= phase["duration"]:
                break

            phase_step += 1
            step += 1
            uptime = int(time.time() - start_time)

            # Kalau fase offline, skip kirim data
            if phase["gen"] is None:
                remaining = int(phase["duration"] - elapsed_in_phase)
                ts = datetime.now().strftime('%H:%M:%S')
                print(f"  [{C.DIM}{ts}{C.RESET}]  {C.RED}⏸  Tidak kirim data "
                      f"— tunggu offline detection ({remaining}s){C.RESET}")
                time.sleep(SEND_INTERVAL)
                continue

            # Generate data
            sensor_data = phase["gen"](phase_step)

            # Kirim
            ok, result = send_data(sensor_data, uptime)
            ts = datetime.now().strftime('%H:%M:%S')
            remaining = int(phase["duration"] - elapsed_in_phase)

            if ok:
                success_count += 1
                print(format_row(ts, sensor_data, True, remaining))
            else:
                fail_count += 1
                print(f"  [{C.DIM}{ts}{C.RESET}]  {C.RED}❌  Gagal: {result}{C.RESET}")

            time.sleep(SEND_INTERVAL)

        # Phase complete
        print(f"\n  {C.DIM}✓ Fase {phase['name']} selesai{C.RESET}")

    # ==========================================
    # SUMMARY
    # ==========================================
    total_time = int(time.time() - start_time)
    print(f"\n{C.CYAN}{'═' * 78}{C.RESET}")
    print(f"{C.BOLD}{C.GREEN}  ✅ TEST SELESAI{C.RESET}")
    print(f"{C.CYAN}{'═' * 78}{C.RESET}")
    print(f"  Total waktu   : {C.BOLD}{total_time}s{C.RESET} ({total_time // 60}m {total_time % 60}s)")
    print(f"  Data terkirim : {C.GREEN}{success_count}{C.RESET}")
    print(f"  Data gagal    : {C.RED}{fail_count}{C.RESET}")
    print(f"  Device ID     : {C.BOLD}{DEVICE_ID}{C.RESET}")
    print(f"{C.CYAN}{'═' * 78}{C.RESET}\n")

    print(f"{C.BOLD}📊 Cek dashboard sekarang:{C.RESET}")
    print(f"   • Alert history    : {C.CYAN}http://localhost:5000/api/v1/alerts/history?device_id={DEVICE_ID}{C.RESET}")
    print(f"   • Device detail    : {C.CYAN}http://localhost:5000/device/{DEVICE_ID}{C.RESET}")
    print(f"   • Alert aktif      : {C.CYAN}http://localhost:5000/api/v1/alerts?device_id={DEVICE_ID}{C.RESET}")
    print()

    print(f"{C.BOLD}💡 Yang harusnya kelihatan di dashboard:{C.RESET}")
    print(f"   1. Fase HEALTHY     → tidak ada alert")
    print(f"   2. Fase WARNING     → alert 🟠 suhu tinggi (warning)")
    print(f"   3. Fase DANGER      → alert naik jadi 🔴 danger")
    print(f"   4. Fase RECOVERY    → alert clear bertahap (danger→warning→clear)")
    print(f"   5. Fase HIGH HUMID  → alert 🔴 kelembaban danger")
    print(f"   6. Fase NORMAL      → semua alert clear")
    print(f"   7. Fase OFFLINE     → device jadi offline + alert 🔴 offline")
    print()


# ==========================================
# ENTRY
# ==========================================
def validate():
    errors = []
    if not API_KEY or API_KEY.startswith("PASTE_"):
        errors.append(
            "API_KEY belum di-set.\n"
            "   Buka dashboard → Tambah Perangkat → copy API key → paste ke script ini."
        )
    if not DEVICE_ID:
        errors.append("DEVICE_ID belum di-set.")
    if errors:
        print(f"\n{C.RED}❌ Configuration Error:{C.RESET}\n")
        for e in errors:
            print(f"  • {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    validate()

    print(f"\n{C.YELLOW}⚠  PENTING:{C.RESET}")
    print(f"   Device {C.BOLD}{DEVICE_ID}{C.RESET} harus sudah didaftarkan di dashboard")
    print(f"   dengan ALERT RULES yang sama seperti di script ini.")
    print(f"   Kalau belum, buka dashboard → Tambah Perangkat → isi rules.")
    print(f"\n   Tekan {C.BOLD}Enter{C.RESET} untuk mulai, atau {C.BOLD}Ctrl+C{C.RESET} untuk batal...")
    try:
        input()
    except KeyboardInterrupt:
        print(f"\n{C.DIM}Dibatalkan.{C.RESET}")
        sys.exit(0)

    try:
        run_demo()
    except KeyboardInterrupt:
        print(f"\n\n{C.YELLOW}⏹  Test dihentikan manual.{C.RESET}\n")
        sys.exit(0)