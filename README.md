# DocIntel

> From raw invoices to verified, searchable data.

AI-powered document intelligence system that processes PDF, image, Excel and CSV files
using OCR and an LLM, extracts structured invoice data, validates totals and duplicates,
cross-verifies documents, and makes everything searchable through an API and web interface.

> **Status: in development, built phase by phase.**
> Phase 1 (foundation) is complete. See the roadmap below.

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| 1 | Foundation: Docker Compose, Django, Celery, database schema, health endpoint | Done |
| 2 | Document processing: PDF, OCR, Excel, CSV pipelines | Planned |
| 3 | AI extraction and validation | Planned |
| 4 | REST API and background jobs | Planned |
| 5 | Keyword and semantic search | Planned |
| 6 | React frontend | Planned |
| 7 | Tests and evaluation | Planned |
| 8 | Documentation and final delivery | Planned |

## Tech stack

- **Backend:** Python, Django, Django REST Framework
- **Background jobs:** Celery + Redis
- **Database:** PostgreSQL with pgvector (SQLite for no-Docker local mode)
- **LLM:** Groq API (from Phase 3)
- **Frontend:** React, Vite, TypeScript, Tailwind CSS (Phase 6)

## Setup

### Option A: Docker (recommended)

Requires Docker Desktop.

```bash
cp .env.example .env        # Windows PowerShell: copy .env.example .env
docker compose up --build
```

Then open http://localhost:8000/api/health/ - expected:

```json
{"status": "ok", "service": "docintel-api", "database": "ok", "debug": true}
```

Create an admin user to browse the database at http://localhost:8000/admin/ :

```bash
docker compose exec api python manage.py createsuperuser
```

### Option B: Local mode (no Docker)

Requires Python 3.11+.

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate                 # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy ..\.env.example ..\.env           # macOS/Linux: cp ../.env.example ../.env
python manage.py migrate
python manage.py runserver
```

### Run the tests

```bash
cd backend
python manage.py test
```

## Documentation

- [Database schema](docs/DATABASE_SCHEMA.md)

## License

MIT
