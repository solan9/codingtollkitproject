# TrustNews — Real-world news recommendation platform

This repository is a deployable **full-stack starter**, not a hosted service. It includes a React responsive/PWA frontend, FastAPI backend, PostgreSQL database, secure account registration/login, preferences, bookmarks, feedback, a real-news ingestion endpoint, and a transparent recommendation baseline. You must configure a news provider key and deployment secrets before live news import.

## Included
- React + TypeScript mobile-responsive web app and PWA manifest
- FastAPI REST API
- PostgreSQL persistence (Docker Compose); SQLite fallback for local backend
- Password hashing, JWT bearer sessions, user interests
- Article feed/search/category filter, bookmark, like, hide and read/open feedback
- NewsAPI top-headlines ingestion (server-side key; never put key in frontend)
- Personalized ranking with user interests, reading signals, freshness and credibility metadata
- Category/source diversity re-ranking
- Docker Compose and production web container
- Android packaging instructions (Capacitor) below

## Start locally
1. Install Docker Desktop and Node.js 20+.
2. Copy `.env.example` to `.env`; set long random `POSTGRES_PASSWORD` and `JWT_SECRET`.
3. Set `NEWS_API_KEY` if you have an account/key from NewsAPI. Without it, the backend and UI start, but live import returns a clear configuration error.
4. From this folder:
   ```bash
   docker compose up --build
   ```
5. Open http://localhost:5173. API health: http://localhost:8000/health.

For frontend-only development, `cd frontend && npm install && npm run dev`. Set `VITE_API_URL=http://localhost:8000` in a frontend `.env` if needed.

## Live news provider
The API expects a NewsAPI-compatible key in backend environment variable `NEWS_API_KEY`. The `/admin/ingest` endpoint requires a signed-in account. It imports top headlines for India and deduplicates by canonical article URL. API plans and country/language coverage vary by provider; this app does not bypass paywalls or scrape protected sites. For production, add a provider adapter for licensed feeds/RSS, enforce source allowlists, and monitor rate limits.

## Installable Android app
This web app is a PWA and works in mobile browsers. To package a native Android shell with Capacitor:
```bash
cd frontend
npm install
npm install @capacitor/core @capacitor/cli @capacitor/android
npx cap init TrustNews com.example.trustnews --web-dir dist
npm run build
npx cap add android
npx cap sync android
npx cap open android
```
In Android Studio, configure app signing, app icon, splash screen, and production API URL, then Build > Generate Signed Bundle/APK. **Do not ship `localhost` API URLs**: set `VITE_API_URL` to your deployed HTTPS API before building. `android/` folder is reserved; Capacitor generates the native project.

## Production checklist
- Replace development JWT and database secrets. Use a secret manager.
- Deploy API and PostgreSQL with TLS, backups, migrations, firewall and monitoring.
- Configure exact frontend origin in `CORS_ORIGINS`.
- Configure `VITE_API_URL` to the deployed API, rebuild frontend.
- Use HTTPS; secure cookies or short-lived access/refresh token rotation; rate-limit login/register/ingest.
- Add Alembic migrations (currently tables auto-create for starter deployment).
- Verify NewsAPI/provider license and attribution requirements.
- Validate image domains and use proxy/cache if provider policies permit.
- Add email verification, password reset, account deletion/export, moderation, abuse monitoring.
- Run security and load tests before public launch.

## Research limitations (important)
The supplied research proposal calls for HIN meta-path reasoning, GNN learning (PyG/DGL), independent credibility labels, temporal benchmarks, simulation, baseline comparisons, ablation, statistical tests, and exposure fairness. This starter implements an operational web product and transparent heuristic ranking, but **does not claim those research experiments are implemented or validated**. The current credibility value is neutral metadata, not fact-checking. The graph/GNN training pipeline and benchmark evaluation are follow-on research modules. User clicks are implicit feedback, not ground truth satisfaction or trust.

## API overview
- `POST /auth/register` JSON `{name,email,password}`
- `POST /auth/login` form fields `username=email`, `password`
- `GET /auth/me`
- `PUT /auth/preferences` JSON `{interests:["Technology","Science"]}`
- `GET /articles?category=Technology&q=AI&limit=40`
- `GET /recommendations` authenticated
- `POST /articles/{id}/feedback` JSON `{action:"open|read|like|dislike|hide"}`
- `GET /bookmarks`, `POST /bookmarks/{id}`, `DELETE /bookmarks/{id}`
- `POST /admin/ingest` authenticated, provider key required
- `GET /stats`, `GET /health`

## Data / privacy
Password hashes only are stored, not plaintext passwords. User feedback and preferences are personal data. Publish a privacy notice, provide deletion/export, set retention, and restrict admin/provider keys before public deployment.
