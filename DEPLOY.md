# Deploy

Semua gratis, tanpa kartu kredit:

| Bagian | Layanan | Catatan |
|---|---|---|
| Backend (FastAPI + scheduler) | **Render**, free web service | 512 MB RAM, cukup (puncak sekitar 230 MB) |
| Database | **Neon** Postgres, free | 0,5 GB storage, 100 CU-jam per bulan |
| Keep-alive | **cron-job.org** | Ping tiap 10 menit supaya Render tidak tidur |
| Frontend | **Vercel**, Hobby | Build statis |

```
browser ──▶ Vercel (React build)
   │
   └── fetch /api/* ──▶ Render (FastAPI + scheduler) ──▶ Neon Postgres
                              ▲                    └──▶ Tatum · Walrus · yjs · CoinGecko
        cron-job.org ── /api/ping tiap 10 menit
```

Urutannya: database → backend → frontend → sambungkan.

## File yang dipakai

| File | Fungsi |
|---|---|
| `render.yaml` | Blueprint Render: service Docker gratis di Singapore, health check, daftar env |
| `deploy/Dockerfile` | Image Python 3.12 untuk backend |
| `deploy/start.sh` | Kalau database kosong: seed histori + restore dari Walrus; lalu start uvicorn di `$PORT` |
| `.dockerignore` | Hanya `backend/` dan `start.sh` yang masuk image (tanpa `.env`, database lokal, tes) |
| `backend/scripts/copy_db.py` | Salin database lokal ke Neon, sekali saja |
| `frontend/vercel.json` | Rewrite SPA, header keamanan, cache aset |

## 1. Database di Neon

1. neon.com → daftar → **Create project**. Postgres versi terbaru, region **AWS Asia Pacific (Singapore)** supaya dekat dengan Render.
2. Di **Connect**, matikan **Connection pooling**, lalu salin connection string. Bentuknya:
   `postgresql://user:password@ep-xxxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`
3. Salin data lokal ke Neon (dari root project, PowerShell):

   ```powershell
   .venv\Scripts\pip install -r backend\requirements.txt
   .venv\Scripts\python backend\scripts\copy_db.py "postgresql://...neon.tech/neondb?sslmode=require"
   ```

   Script ini membuat tabel, menyalin semua baris (candle, onchain, forecast, memori, akun, kredit, sesi), lalu mengaktifkan RLS. Kalau target sudah berisi, script menolak menimpa.

   Kalau langkah ini dilewati, backend akan seed sendiri saat pertama start (backfill 90 hari + restore dari Walrus, butuh beberapa menit). Jurnal forecast dan akun akan mulai dari nol.

Simpan connection string ini; nanti dipakai sebagai `DATABASE_URL`. Jangan ditulis di file mana pun di repo.

## 2. Backend di Render

1. Push repo ke GitHub dulu.
2. render.com → **New → Blueprint** → hubungkan repo `MarketRecallAI`. Render membaca `render.yaml` dan menyiapkan service `marketrecall-api`.
3. Isi nilai yang diminta (diambil dari `.env` lokalmu):

| Nama | Nilai |
|---|---|
| `DATABASE_URL` | connection string Neon |
| `TATUM_API_KEY` | wajib |
| `MEMWAL_PRIVATE_KEY`, `MEMWAL_ACCOUNT_ID`, `MEMWAL_AGENT_ID` | wajib |
| `LLM_API_KEY` | wajib |
| `COINGECKO_API_KEY` | opsional, boleh kosong |
| `CORS_ORIGINS` | sementara `[]`, diisi di langkah 4 |
| `APP_DOMAIN` | sementara `localhost`, diisi di langkah 4 |

   `ADMIN_TOKEN` dibuat acak otomatis. `TRUST_PROXY`, `PROXY_HOPS` dan `EXPOSE_DOCS` sudah diisi oleh `render.yaml`.

4. **Apply**. Build pertama sekitar 3–5 menit.
5. Cek `https://marketrecall-api.onrender.com/api/health` (nama subdomain bisa berbeda; lihat di dashboard Render).

### Keep-alive di cron-job.org

Render gratis tidur setelah 15 menit tanpa request, dan scheduler ikut berhenti.

1. cron-job.org → daftar → **Create cronjob**.
2. URL: `https://<service>.onrender.com/api/ping`, jadwal **setiap 10 menit**.

`/api/ping` sengaja tidak menyentuh database. Jadi Neon tetap bisa tidur di sela-sela job per jam, dan kuota 100 CU-jam tidak habis. Render memberi 750 jam per bulan, cukup untuk satu service menyala terus.

## 3. Frontend di Vercel

1. vercel.com → **Add New Project** → import repo yang sama.
2. **Root Directory**: `frontend`.
3. **Environment Variables**:

| Nama | Nilai |
|---|---|
| `VITE_API_BASE` | `https://<service>.onrender.com` (tanpa `/` di akhir) |
| `VITE_ENOKI_API_KEY` | opsional, login Google |
| `VITE_GOOGLE_CLIENT_ID` | opsional, login Google |

4. **Deploy**.

`VITE_API_BASE` dibaca saat build, termasuk untuk Content-Security-Policy. Kalau URL backend berubah, redeploy frontend.

## 4. Sambungkan

1. Render → service → **Environment**:
   - `CORS_ORIGINS` = `["https://<project>.vercel.app"]`
   - `APP_DOMAIN` = `<project>.vercel.app`

   Simpan; Render redeploy otomatis. Data aman karena ada di Neon.
2. Login Google (opsional): tambahkan `https://<project>.vercel.app` ke *Authorized JavaScript origins* dan *redirect URIs* di Google Cloud Console, dan ke allowed origins di portal Enoki.

### Cek akhir

- Landing menampilkan forecast live, bukan "Loading…".
- DevTools → Console: tidak ada error CORS atau CSP.
- Pesan login wallet menulis `Domain: <project>.vercel.app`.
- Buka satu sesi, ajukan satu pertanyaan, lalu sign out.
- Setelah lewat menit ke-00, Render → **Logs** menunjukkan job per jam berjalan.

## Catatan operasional

- **Hanya satu scheduler.** Setelah Render jalan, backend lokal harus dijalankan dengan `SCHEDULER_ENABLED=false`. Kalau tidak, keduanya menulis episode yang sama ke Walrus dan menghabiskan kuota 150 tulisan per hari.
- **Update:** push ke GitHub. Render (backend) dan Vercel (frontend) redeploy otomatis.
- **Rate limit** disimpan di memori dan reset saat redeploy. Kalau semua pengguna kena "Too many requests" bersamaan, IP proxy yang terbaca; naikkan `PROXY_HOPS` ke `2`.
- **Kalau ping berhenti**, Render tidur dan request pertama butuh sekitar satu menit. Collector mengisi gap candle sampai 168 jam saat bangun.
- **Tes terhadap Postgres** secara lokal: set `TEST_DATABASE_URL` ke database kosong sebelum `pytest`. Database itu akan dihapus isinya.
