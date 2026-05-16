# Uptube

MVP for moving an Aparat video to a creator's YouTube channel with Persian SRT subtitles generated through Metis Whisper.

## Structure

- `frontend/`: Next.js UI for link intake, YouTube connection, job progress, subtitle review, and upload.
- `backend/`: FastAPI API, DB models, service adapters, and worker pipeline.
- `PROJECT_CONTEXT.md`: short source of truth for locked decisions. Keep it under 200 lines.

## Secrets

Copy `.env.example` to `.env` and fill real values locally. Do not commit real keys. The Metis key shared during planning should be rotated before production use.

## Backend

```powershell
cd backend
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Run tests:

```powershell
cd backend
python -m unittest discover tests
```

## Local Real Test

See `docs/LOCAL_TESTING.md`.

## Contributing

For teammate setup and Git workflow, see `CONTRIBUTING.md`.

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` when the backend is running elsewhere.

Use `http://localhost:3000` for local YouTube OAuth. The session cookie is set on `localhost`.
