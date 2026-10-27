# Deploy

Backend di **Hugging Face Spaces** (Docker), frontend di **Vercel**. Urutannya: backend dulu (untuk dapat URL API), lalu frontend, lalu sambungkan keduanya lewat `CORS_ORIGINS` dan `APP_DOMAIN`.

```
browser ──▶ Vercel (React build, statis)
   │
   └──── fetch /api/* ──▶ HF Space (FastAPI + scheduler, port 7860) ──▶ Tatum · Walrus · yjs · CoinGecko
```

## File yang dipakai

| File | Fungsi |
|---|---|
| `deploy/huggingface/Dockerfile` | Image Python 3.12, jalan sebagai uid 1000, port 7860 |
| `deploy/huggingface/start.sh` | Pilih lokasi database, seed data saat pertama jalan, lalu start uvicorn |
| `deploy/huggingface/README.md` | Header konfigurasi Space (`sdk: docker`, `app_port: 7860`) |
| `deploy/huggingface/.dockerignore` | `.env`, database lokal, tes dan frontend tidak masuk image |
| `frontend/vercel.json` | Rewrite SPA, header keamanan, cache aset |

## 1. Backend di Hugging Face

### Buat Space

1. huggingface.co → **New Space** → SDK **Docker** → template **Blank** → visibility **Public** (Space privat tidak bisa dipanggil dari browser).
2. Hardware: **CPU basic** cukup.
3. Disarankan: **Settings → Persistent storage** (paket kecil). Tanpa ini, database ada di dalam container dan **hilang setiap Space restart**: akun, kredit, sesi dan jurnal forecast ikut terhapus. Learned state tetap aman karena dibangun ulang dari Walrus.

### Isi repo Space

Repo Space berisi folder `backend/` plus empat file dari `deploy/huggingface/` di root-nya. Dari PowerShell, di folder induk project:

```powershell
git clone https://huggingface.co/spaces/<user>/<space> hf-space
robocopy MarketRecall\backend hf-space\backend /E /XD data tests __pycache__ .pytest_cache
Copy-Item MarketRecall\deploy\huggingface\Dockerfile, MarketRecall\deploy\huggingface\start.sh, MarketRecall\deploy\huggingface\README.md, MarketRecall\deploy\huggingface\.dockerignore hf-space\
cd hf-space
git add . ; git commit -m "Deploy MarketRecall API" ; git push
```

Saat `git push`, login dengan username HF dan **access token (write)** sebagai password.

> `robocopy` dengan `/XD data` penting: `backend/data` berisi database lokal (alamat pengguna, sesi) dan tidak boleh ikut ke repo Space yang publik.

### Secrets dan variables

**Settings → Variables and secrets.** Semua nilai menjadi environment variable di container. Nilai rahasia diambil dari `.env` lokalmu, jangan ditulis di file mana pun.

**Secrets:**

| Nama | Catatan |
|---|---|
| `TATUM_API_KEY` | wajib |
| `MEMWAL_PRIVATE_KEY`, `MEMWAL_ACCOUNT_ID`, `MEMWAL_AGENT_ID` | wajib, untuk Walrus Memory |
| `LLM_API_KEY` | wajib, yjs |
| `COINGECKO_API_KEY` | opsional |
| `ADMIN_TOKEN` | string acak panjang, misalnya dari `python -c "import secrets; print(secrets.token_urlsafe(32))"` |

**Variables:**

| Nama | Nilai |
|---|---|
| `CORS_ORIGINS` | `["https://<project>.vercel.app"]`; sementara isi `[]` sampai frontend jadi |
| `APP_DOMAIN` | `<project>.vercel.app` (tanpa `https://`; muncul di pesan login wallet) |
| `TRUST_PROXY` | `true` (Space berada di belakang proxy HF) |
| `PROXY_HOPS` | `1` |
| `EXPOSE_DOCS` | `false` |
| `BACKFILL_DAYS` | `90` (opsional) |

Variabel lain di `.env.example` sudah punya default yang benar.

### Start pertama

Saat database belum ada, `start.sh` menjalankan:

1. `scripts/backfill.py --days 90`: candle dan snapshot onchain 90 hari terakhir.
2. `scripts/wipe_restore.py`: membangun ulang learned state (credibility, episode, lesson) dari Walrus.

Proses ini butuh beberapa menit; status Space tetap **Building/Starting** sampai selesai (batas `startup_duration_timeout: 1h`). Setelah berhasil, file `marketrecall.db.seeded` dibuat dan start berikutnya langsung menyalakan API.

Cek: `https://<user>-<space>.hf.space/api/health` harus mengembalikan status ok.

## 2. Frontend di Vercel

1. vercel.com → **Add New Project** → import repo GitHub.
2. **Root Directory**: `frontend`. Framework terdeteksi sebagai Vite; `vercel.json` sudah mengatur build dan output.
3. **Environment Variables** (Production):

| Nama | Nilai |
|---|---|
| `VITE_API_BASE` | `https://<user>-<space>.hf.space` (tanpa `/` di akhir) |
| `VITE_ENOKI_API_KEY` | opsional, untuk login Google |
| `VITE_GOOGLE_CLIENT_ID` | opsional, untuk login Google |

4. Deploy.

`VITE_API_BASE` dibaca saat build, termasuk untuk Content-Security-Policy (`connect-src`). Kalau URL backend berubah, **redeploy** frontend.

## 3. Sambungkan

1. Di Space, ubah `CORS_ORIGINS` ke `["https://<project>.vercel.app"]` dan `APP_DOMAIN` ke `<project>.vercel.app`. Kalau pakai custom domain, masukkan juga domain itu ke `CORS_ORIGINS`.
2. Space akan restart otomatis. Tanpa persistent storage, restart ini menjalankan seed ulang.
3. Login Google (opsional): tambahkan `https://<project>.vercel.app` ke *Authorized JavaScript origins* dan *redirect URIs* di Google Cloud Console, dan ke allowed origins di portal Enoki.

### Cek akhir

- Halaman landing menampilkan forecast live (bukan "Loading…").
- DevTools → Console: tidak ada error CORS atau CSP.
- Login dengan wallet: pesan yang ditandatangani menulis `Domain: <project>.vercel.app`.
- Buka satu sesi, ajukan satu pertanyaan, lalu sign out.

## Catatan operasional

- **Satu instance saja.** Jangan jalankan backend lokal dengan scheduler aktif bersamaan dengan Space: keduanya akan menulis episode yang sama ke Walrus dan menghabiskan kuota 150 tulisan per hari. Untuk development lokal, set `SCHEDULER_ENABLED=false`.
- **Space gratis tidur** setelah 48 jam tanpa traffic, dan scheduler ikut berhenti. Saat bangun, collector mengisi gap candle sampai 168 jam. Untuk demo juri, buka Space beberapa jam sebelumnya.
- **Rate limit** disimpan di memori dan reset saat restart. `PROXY_HOPS=1` mengambil IP dari entri paling kanan `X-Forwarded-For`. Kalau semua pengguna terkena 429 bersamaan, berarti IP proxy yang terbaca; naikkan ke `2`.
- **Header keamanan:** backend mengirim header sendiri, dan `vercel.json` menambahkan `X-Frame-Options: DENY` dan `frame-ancestors 'none'` untuk frontend. Karena itu halaman Space di huggingface.co (yang memakai iframe) tampil kosong; pakai URL `*.hf.space` langsung.
- **Update backend:** ulangi `robocopy` dan `git push` di folder `hf-space`. Database di persistent storage tidak tersentuh.
