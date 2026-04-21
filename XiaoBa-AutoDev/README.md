# XiaoBa-AutoDev

XiaoBa-AutoDev is a lightweight case platform for the `Inspector -> Engineer -> Reviewer` loop.

This scaffold is intentionally pragmatic:

- `FastAPI` for API and server-rendered pages
- `PyMySQL` for platform state and metadata
- `MinIO` for artifact body storage
- local workdir copies under `data/cases/` so later agents can still read files with bash and read-file tools

## What It Does

- create cases
- append artifacts
- append events
- transition case states
- browse case queue and case detail pages
- upload artifacts into MinIO while preserving a local working copy

## Directory Layout

- `app/`: backend and server-rendered frontend
- `docs/`: platform contract
- `data/cases/`: local working copies of uploaded artifacts

## Run

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8090 --app-dir .
```

Then open `http://127.0.0.1:8090` and you will land on the case board at `/cases`.

## Docker

```bash
docker compose up --build
```

This compose file assumes MySQL and MinIO are external and reads connection settings from `.env`.
