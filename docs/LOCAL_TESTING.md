# Local Real Testing

## Ready State
- Frontend: http://localhost:3000
- Backend health: http://127.0.0.1:8000/health
- Backend runs from `backend/.venv`.
- FFmpeg is provided by `imageio-ffmpeg`; no system FFmpeg install is required.
- If Docker/Redis is available, `start-local.ps1` starts Redis and two RQ workers.
- If Redis is not running, jobs fall back to FastAPI background tasks for local testing.

## Current Limits
- Metis STT is configured through `.env`.
- Metis direct `response_format=srt` currently fails server-side, so local testing uses chunked text transcription and renders SRT locally.
- Metis chunks run with limited parallelism. Tune `METIS_PARALLEL_CHUNKS` carefully; higher is faster but can hit provider limits.
- Per-user beta controls are enforced by `MAX_JOBS_PER_USER_PER_DAY` and `MAX_ACTIVE_JOBS_PER_USER`.
- YouTube real upload still requires Google OAuth credentials:
  - `GOOGLE_CLIENT_ID`
  - `GOOGLE_CLIENT_SECRET`
  - redirect URI in Google Cloud: `http://localhost:8000/auth/google/callback`
- Without Google credentials, test the real Aparat download + Metis subtitle path up to `awaiting_review`.
- Use `http://localhost:3000` for the UI during YouTube auth. Do not use `127.0.0.1:3000`; the local session cookie is tied to `localhost`.

## Google OAuth Setup
1. In Google Cloud Console, create or select a project.
2. Enable YouTube Data API v3.
3. Configure OAuth consent screen and add your Google account as a test user while the app is in testing.
4. Create an OAuth client with application type `Web application`.
5. Add this authorized redirect URI exactly:
   `http://localhost:8000/auth/google/callback`
6. Put the client values in `.env`:
   `GOOGLE_CLIENT_ID=...`
   `GOOGLE_CLIENT_SECRET=...`
7. Restart local servers.

## Run
```powershell
.\scripts\start-local.ps1
```

Stop:
```powershell
.\scripts\stop-local.ps1
```

## Test Steps
1. Open http://localhost:3000.
2. Paste a public Aparat video URL.
3. Check the ownership confirmation box.
4. Click start processing.
5. Wait until the status reaches review.
6. Edit subtitle text and save.
7. Fill Google OAuth values in `.env`, restart, connect YouTube, then click upload.
