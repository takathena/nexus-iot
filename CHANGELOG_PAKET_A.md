# Paket A — Privasi absensi dan peran

## Catatan rilis (baca dulu)
Setelah rilis ini, user non-admin **kehilangan akses absensi** sampai diberi izin
`attendance.view` atau `attendance.manage` oleh admin. Ini perilaku yang disengaja (celah A1).

## Backend
- Migrasi v18 (`app/database.py`):
  - `users.role` (superadmin | admin | moderator | user). Akun seed `IOT_USERNAME` jadi superadmin; is_admin lain jadi admin; bila tidak ada superadmin, admin tertua dijadikan superadmin.
  - tabel `user_permissions`. Migrasi tidak memberi izin ke siapa pun.
- `app/permissions.py`: `has_permission`, `effective_permissions`, `permission_required`, `role_required`, `set_user_permissions`. Izin dibaca dari DB setiap request, jadi pencabutan langsung berlaku.
- Izin absensi diterapkan di:
  - `/attendance`, `/attendance/report|stats|today|unregistered|last-unknown|export`, `GET /cardholders` (attendance.view)
  - `POST` dan `DELETE /cardholders` (attendance.manage)
  - `/system/info`: `attendance_count` dan `cardholder_count` dihilangkan tanpa izin
  - chat AI: tool absensi tidak dikirim ke LLM dan ditolak bila dipanggil (lapis ganda)
- Endpoint baru: `GET/PUT /users/<id>/permissions` (admin). Tidak berlaku untuk admin/superadmin (sudah punya semua izin).
- Aturan peran:
  - Superadmin tidak bisa dihapus atau diubah peran-nya.
  - Admin biasa tidak bisa mengubah atau menghapus admin/superadmin lain.
  - Hanya superadmin yang bisa memberi peran admin.
  - Tidak bisa mengubah peran akun sendiri tanpa superadmin.
  - Aturan "admin terakhir" tetap berlaku.
- `POST /users` dan `PUT /users/<id>` menerima `role`. `is_admin` tetap diterima untuk kompatibilitas.
- `GET /users/me` mengembalikan `role` dan `permissions`. `GET /users` mengembalikan `role`.
- Perubahan peran dan izin dicatat di `audit_log` (`user.role`, `user.permissions`, `user.create`).
- Telegram: tidak ada nama karyawan di pesan (diperiksa, tidak ada perubahan).

## Frontend
- Desktop: menu Absensi hanya untuk pemegang izin. `#attendance` tanpa izin dialihkan ke dashboard dengan toast. Bila izin dicabut saat di halaman absensi, polling berhenti dan user kembali ke dashboard. Tombol "Daftarkan kartu" butuh attendance.manage.
- Mobile: tab Absensi dan tombol Daftar Kartu mengikuti izin. Info sistem menampilkan "—" untuk jumlah absensi tanpa izin.
- Kelola Pengguna: peran User, Moderator, Admin (Admin hanya untuk superadmin). Izin absensi: "Boleh melihat absensi" dan "Boleh mengelola kartu" (manage otomatis mencentang view). Superadmin ditampilkan tanpa bisa diubah.

## Keterbatasan (sengaja ditunda)
- Moderator saat ini berperilaku seperti user. Perilaku "lihat semua dashboard" menunggu Paket B.
- Mobile tidak otomatis menyembunyikan absensi bila izin dicabut saat sesi berjalan. Server tetap menolak; yang terlihat hanya pesan galat.
- Peran dan izin di Kelola Pengguna belum tercatat di audit untuk perubahan yang gagal (hanya yang berhasil).

## Tes
- `tests/test_paket_a_permissions.py` (19): migrasi, penolakan 403, grant/revoke, manage→view, aturan peran, system/info, chat, audit.
- `tests/test_paket_a_ui.py` (8): gerbang UI desktop/mobile, drawer pengguna, logika perm di ui.js.
- `tests/test_phase1_authz.py`: satu tes diperbarui. Daftar kartu untuk user tanpa izin sekarang mengharapkan 403 PERMISSION_DENIED.
- Dijalankan dengan runner pengganti dan stub untuk paket yang tidak tersedia di sandbox (flask_cors, flask_wtf, flask_limiter, marshmallow). Tidak ada regresi dibanding kode asli (47 kegagalan yang sama sudah ada di kode asli karena stub).
- Belum dijalankan dengan pytest asli, belum diuji di browser.

# Redesain Fase 3 (sebagian): status

## Ditambahkan
- Beranda: kartu "Mulai dengan perangkat pertama" dengan 3 langkah (tambah perangkat, salin API key ke firmware, menunggu data pertama). Tampil hanya bila belum ada perangkat dan hanya untuk editor. Hilang otomatis setelah perangkat ada.
- Halaman Perangkat: tombol utama "Tambah perangkat" (hanya editor). Menu ⋯ berisi "Impor massal" (hanya admin).
- `data-proxy` sekarang berfungsi di seluruh aplikasi, tidak hanya di Pengaturan.

## Belum (sisa Fase 3)
- Tabel Perangkat yang ramping (kolom lokasi, tipe, uptime, WiFi pindah ke laci detail).
- Laci detail perangkat dengan tab Ringkasan, Data, Alert, Pengaturan.
- Edit Perangkat sebagai laci (saat ini masih modal panjang).
- Wizard tambah perangkat 3 langkah (saat ini masih modal yang ada).
- Kartu perangkat dengan sparkline dan sakelar Kartu/Tabel di beranda.
- Aksi massal (F6) dan sisa Fase 0/1 (pemecahan dashboard.js, topbar).

## Verifikasi
- `tests/test_redesain_fase3.py` (6 tes) lolos. Full suite: 275 lolos, 47 kegagalan identik dengan kode asli (stub).
- Belum diuji di browser.

# Perbaikan: kembali ke dashboard default dari "Semua perangkat"

- Penyebab: di halaman /all, dashboard default tetap dianggap aktif (currentDashboardId). Klik dashboard default di switcher dihentikan oleh pengecekan "sudah aktif", sehingga user tidak bisa kembali.
- Perbaikan: pengecekan "sudah aktif" dilewati saat mode Semua perangkat (static/js/dashboard.js, switchDashboard).
- Tes: tests/test_switcher_view_all.py (3 tes).
