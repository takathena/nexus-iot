# Changelog

## Fase 1 — perbaikan cepat
- **N1** Bulk Import tidak lagi selalu 500: `bulk_import_item_schema` kini diimpor. Target `make lint` ditambahkan agar `undefined name` tertangkap.
- **C2** Semua route tulis (device, regenerate-key, alert-rules per device, bulk-import, cardholders, tes notifikasi) admin-only lewat decorator `admin_required`; pola `_require_admin()` dihapus. Kontrol terkait disembunyikan untuk non-admin di UI desktop dan mobile.
- **C3** Global Alert Rules tersimpan kini dibaca mesin alert (cache TTL 45 dtk, di-invalidate saat PUT/DELETE; JSON korup -> default).
- **C4** Rules per device menimpa global per sensor, bukan mengganti total.
- **H7** `SESSION_COOKIE_SECURE` tidak lagi dipaksa `True` di production (ikut env, default = `ENABLE_HSTS`); HSTS hanya bila `ENABLE_HSTS=True`; peringatan log bila production memakai cookie non-Secure.
