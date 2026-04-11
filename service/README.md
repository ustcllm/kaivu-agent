# Kaivu Service

This package provides a minimal FastAPI service layer for Kaivu（开物）, the Python research-agent core.

## What it serves

- workflow submission and status
- final report retrieval
- usage and token/cost summary
- scientific memory search/save/review
- claim/evidence graph retrieval
- a minimal browser UI mounted from `/app`

## Install

```powershell
pip install -r C:\Users\liand\Documents\agent\service\requirements.txt
```

## Run

```powershell
python C:\Users\liand\Documents\agent\scripts\run_service.py
```

Then open:

- `http://127.0.0.1:8000/app/` for the browser UI
- `http://127.0.0.1:8000/docs` for the API docs

## Main endpoints

- `POST /workflow/run`
- `GET /workflow/{run_id}`
- `GET /reports/{run_id}`
- `GET /usage/{run_id}`
- `POST /memory/search`
- `POST /memory/save`
- `POST /memory/review`
- `GET /graph/{run_id}`
- `GET /health`

