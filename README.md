# CB Failed Assistant

Production-ready redesign of the original Streamlit CB Failed MVP. The app uses a FastAPI backend, React/Vite frontend, schema-based dictionary detection, deterministic validation, optional AI-assisted comment interpretation, and Railway deployment support.

## Architecture

- `backend/`: FastAPI API, processing services, temp-file lifecycle, auth, validation, export.
- `frontend/`: React + Vite + TypeScript + Tailwind UI.
- `app.py`: original Streamlit MVP retained as legacy reference.

## Privacy Rules

The app never sends patient fields to AI: `patientLast`, `patientFirst`, `DOB`, `AccNumber`. It also excludes `SIN` from AI payloads. Uploaded files and PHI-heavy rows are kept only in temporary files with TTL cleanup. Ordinary UI APIs, logs, audit metrics, feedback, and optional database records must remain PHI-free.

Full Excel export may include original patient columns for immediate operational download only.

## Local Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

For local auth, use `APP_PASSWORD=local-dev-password` unless you change it.

## Local Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Railway Deployment

1. Create a Railway service from this repository.
2. Set environment variables from `.env.example`.
3. Use strong values for `APP_PASSWORD` or `APP_ACCESS_TOKEN` and `SESSION_SECRET`.
4. Set `AI_ENABLED=true` and `OPENAI_API_KEY` only when AI interpretation should be enabled.
5. Railway uses `Dockerfile` and `railway.json`; healthcheck path is `/health`.

## Operational Flow

1. Login.
2. Upload CB Failed report, provider dictionaries, and optional USAP correction files.
3. Review detected file types, columns, row counts, and warnings.
4. Start processing.
5. Review summary, results, manual review queue, and row details.
6. Export full, manual review, high-confidence, or summary workbook.

## Tests

```bash
pytest backend/tests
cd frontend
npm run build
```

