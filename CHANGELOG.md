# Changelog

## Fase 1 — perbaikan cepat
- **N1** Bulk Import tidak lagi selalu 500: `bulk_import_item_schema` kini diimpor. Target `make lint` ditambahkan agar `undefined name` tertangkap.
- **C2** Semua route tulis (device, regenerate-key, alert-rules per device, bulk-import, cardholders, tes notifikasi) admin-only lewat decorator `admin_required`; pola `_require_admin()` dihapus. Kontrol terkait disembunyikan untuk non-admin di UI desktop dan mobile.
- **C3** Global Alert Rules tersimpan kini dibaca mesin alert (cache TTL 45 dtk, di-invalidate saat PUT/DELETE; JSON korup -> default).
- **C4** Rules per device menimpa global per sensor, bukan mengganti total.
- **H7** `SESSION_COOKIE_SECURE` tidak lagi dipaksa `True` di production (ikut env, default = `ENABLE_HSTS`); HSTS hanya bila `ENABLE_HSTS=True`; peringatan log bila production memakai cookie non-Secure.

## Fase 2 — autentikasi dan data
- **H3** Password `.env` hanya seed admin pertama (tabel users kosong); login selalu lewat `check_password_hash`; hash tidak lagi ditimpa password `.env`.
- **N2** Migrasi v15 menambah `devices.interval_manual`. Interval yang diisi manual tidak ditimpa auto-detect; auto-detect butuh >=5 sampel, abaikan selisih <2 dtk, minimum 10 dtk, hanya menulis bila berubah >20%. Mengosongkan field edit = kembali otomatis.
- **N3** `hadir_hari_ini` hanya menghitung UID terdaftar (kartu asing tetap di `kartu_belum_terdaftar`).
- **N4** UID RFID divalidasi (hex 4-32, boleh `0x`) di `/data` dan `POST /cardholders`; ekspor CSV memakai `csv_safe`.
- **M1** Batas body `/data` (`DATA_MAX_BYTES`, 413), `data` harus dict datar dengan key/nilai tervalidasi, `sensor_type` berpola.

## Fase 3 — keandalan operasional
- **H6** Notifikasi Telegram memakai `parse_mode=HTML` dengan `html.escape` pada semua nilai dinamis; bila Telegram menjawab 400 "can't parse entities", dikirim ulang sebagai teks polos. Teks exception requests tidak lagi di-log (URL memuat token).
- **H4** `Limiter` memakai `RATE_LIMIT_STORAGE` dari config; peringatan bila `memory://` dipakai dengan >1 worker (`WEB_CONCURRENCY`). Kuota `/data` per `device_id` (fallback IP, key function tidak pernah raise) + plafon per IP `RATE_LIMIT_DATA_IP`. Login: throttle kegagalan per username+IP dan per IP, disimpan di DB (migrasi v16, tabel `login_failures`); limit lama tidak dilemahkan.
- **H2** Worker yang tidak mendapat lock background kini mencoba ulang tiap 30 detik dan mengambil alih bila pemilik mati. Heartbeat tiap task di `user_settings` (`bg_hb_*`), tampil di `/system/info` → `background` dengan penanda `stale` (>3× interval). File lock tidak lagi ter-truncate oleh worker yang gagal mengunci.
- **M3** Retensi backup hanya menghapus `iot_*.db`, selalu menyisakan `BACKUP_MIN_KEEP` (default 3) terbaru, tidak pernah menghapus `pre-restore-*.db`. Backup pertama dibuat ~30 detik setelah start bila belum ada backup yang cukup baru. Nama backup memakai waktu WIB.
- **H1** Restore tidak lagi menimpa DB hidup: endpoint menyiapkan `<DB>.restore-pending` + `<DB>.restore-marker`; diterapkan saat start (hapus `-wal`/`-shm`, ganti DB, hapus penanda), ditunda bila DB masih dipakai proses lain.
- **H5** Nginx: `proxy_read_timeout 180s` untuk `/api/v1/chat`; header `Connection` lewat `map` + `upstream` keepalive. Gunicorn: `--timeout 60 --graceful-timeout 30 --max-requests 1000 --max-requests-jitter 100`, worker dari `WEB_CONCURRENCY`.
- **M9** `gunicorn` 21.2.0 → 23.0.0 (CVE-2024-1135). Port publik disamakan ke 5008 (`.env.example`, `CORS_ORIGINS`, compose, README, firmware). Mount kode dipindah dari `docker-compose.yml` ke `docker-compose.override.yml` (dev); `make docker-up` = produksi, `make docker-dev-up` = dev.

## Fase 4 — AI chat dan hal sedang
- **M4** Chat dikeraskan: hanya role `user`/`assistant` dengan `content` string yang diteruskan ke LLM (field lain dibuang), pesan dipotong ke 4000 karakter, maksimum 10 pesan. Hasil tool dibatasi 100 baris / 20 KB (`truncated: true`). Hingga 3 putaran tool (maks 5 panggilan per putaran). Error tool/LLM tidak lagi membocorkan `str(e)` atau URL endpoint; status HTTP upstream kini tampil benar (sebelumnya selalu `?` karena `Response` bernilai False untuk 4xx/5xx). System prompt menandai isi data sebagai data, bukan instruksi. Tool absensi **tetap** terbuka untuk semua user login (keputusan terbuka, lihat di bawah).
- **M7** Logout kini `POST` + CSRF (tombol desktop dan mobile memakai `fetch`); `GET /logout` hanya redirect ke login tanpa menghapus sesi. `/health` memakai konstanta `app.__version__` (6.0.0) dan tidak menampilkan `str(e)` saat gagal. Handler 500 di `api.py` (global alert rules PUT/DELETE, backup, daftar backup, cleanup, tes notifikasi, tes channel, restore) mengembalikan pesan generik; detail ke log.
- **N7** Bila `LLM_API_KEY` kosong: `/api/v1/chat/health` menjawab 200 `{configured:false}`, `POST /api/v1/chat` menjawab 503, dan tombol topbar, FAB mobile, panel, serta `chat.js` tidak dirender (tidak ada polling 503).
- **C1 (sisi kode)** Firmware membaca `WIFI_SSID`, `WIFI_PASSWORD`, `API_URL`, `DEVICE_ID`, `API_KEY` dari `esp32/secrets.py` (di-ignore git); `esp32/secrets.example.py` berisi placeholder. Rotasi key dan pembersihan riwayat git tetap dilakukan manusia.
- Kebersihan: import tak terpakai dihapus (`signal`, `logging` di `app/__init__.py`; `timedelta` di `alerts.py`; `_ConfigClass` di `api.py`; `os`, `logging` di `run.py`).

### Keputusan terbuka (fase 4)
- Apakah tool absensi chat (`get_present_today`, `get_absent_today`, `get_attendance_range`, `get_cardholders`) dibatasi hanya untuk admin? Belum diubah.
- Chat dianggap terkonfigurasi hanya bila `LLM_API_KEY` terisi (sesuai N7). Pengguna LLM lokal yang selama ini mengandalkan default `sk-no-key` perlu mengisi nilai apa saja.

