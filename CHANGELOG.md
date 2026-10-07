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
