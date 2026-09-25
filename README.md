# 🌍 Terra GIS - Backend API

Backend REST API untuk platform **Terra GIS**, dibangun menggunakan **FastAPI**, **SQLAlchemy 2.0 Async**, dan **PostgreSQL**.

---

## 🚀 Fitur Utama
- 🔐 **Autentikasi & Otorisasi**: OAuth2 JWT, Role-Based Access Control (`superadmin`, `admin`, `user`), integrasi Google SSO & Firebase.
- 💳 **Sistem Langganan & Pembayaran**: Integrasi Midtrans Snap & DOKU Payment Gateway, webhook sinkronisasi otomatis, skema upgrade proration & paket antrean (*status quo*).
- 👥 **Paket Bersama (Team Management)**: Manajemen tim hingga 5 surveyor, undangan email dengan deeplink langsung ke aplikasi mobile.
- 📧 **Layanan Email Keamanan**: Notifikasi masuk (login alert), OTP reset kata sandi, dan undangan tim via Google SMTP.
- 🐳 **Production-Ready**: Dilengkapi Docker, Docker Compose, dan alur CI/CD otomatis via GitHub Actions.

---

## 🛠️ Persyaratan Lingkungan (Production)
- Docker & Docker Compose
- Nginx / Caddy sebagai Reverse Proxy dengan SSL (HTTPS)
- Domain / Subdomain yang mengarah ke IP VPS (misal: `api.domainanda.com`)

---

## 📦 Deployment ke Production VPS (Manual Pertama Kali)

1. **Clone repository pada VPS**:
   ```bash
   git clone git@github.com:afanray/core-gis.git ~/core-gis
   cd ~/core-gis
   ```

2. **Siapkan konfigurasi `.env`**:
   ```bash
   cp .env.example .env
   nano .env
   ```
   *Sesuaikan `POSTGRES_PASSWORD`, `DATABASE_URL`, `SECRET_KEY`, dan `APP_WEB_BASE_URL`.*

3. **Jalankan container Docker**:
   ```bash
   docker compose up -d --build
   ```

4. **Periksa status container**:
   ```bash
   docker compose ps
   docker compose logs -f api
   ```

---

## 🔄 Otomasi CI/CD (GitHub Actions)
Setiap kali Anda melakukan `git push origin master`, GitHub Actions akan:
1. Menjalankan pengujian otomatis (`pytest`).
2. Menghubungi VPS Anda melalui SSH.
3. Menjalankan `git pull origin master` dan `docker compose up -d --build` secara otomatis tanpa downtime yang lama.

Konfigurasikan **Repository Secrets** pada GitHub:
- `VPS_HOST`: Alamat IP VPS Anda
- `VPS_USERNAME`: User SSH (misal `root` atau `ubuntu`)
- `VPS_SSH_KEY`: Private SSH Key untuk masuk ke VPS
- `VPS_SSH_PORT`: Port SSH (default `22`)
- `VPS_APP_DIR`: Direktori proyek pada VPS (default: `/root/core-gis` atau `/home/ubuntu/core-gis`)
