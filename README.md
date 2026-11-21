<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0f172a,45:0d9488,100:34d399&height=230&section=header&text=DocIntel&fontSize=76&fontColor=ffffff&fontAlignY=36&animation=fadeIn&desc=From%20raw%20invoices%20to%20verified%2C%20searchable%20data&descSize=20&descAlignY=58" alt="DocIntel banner" width="100%"/>

<img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=22&duration=2800&pause=900&color=10B981&center=true&vCenter=true&width=820&height=50&lines=OCR+%2B+LLM+invoice+extraction+%F0%9F%94%8D;It+never+invents+a+value+%E2%80%94+missing+stays+empty+%E2%9C%85;PDF+%E2%86%94+PDF+and+PDF+%E2%86%94+Excel+cross-verification+%E2%9A%96%EF%B8%8F;Keyword%2C+semantic+and+hybrid+search+%E2%9A%A1;1000-page+PDF+in+12+seconds+%F0%9F%9A%80" alt="Typing animation"/>

<br/>

<img src="https://img.shields.io/badge/Django-5.2-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django"/>
<img src="https://img.shields.io/badge/DRF-REST%20API-A30000?style=for-the-badge&logo=django&logoColor=white" alt="DRF"/>
<img src="https://img.shields.io/badge/Celery-Background%20Jobs-37814A?style=for-the-badge&logo=celery&logoColor=white" alt="Celery"/>
<img src="https://img.shields.io/badge/Redis-Queue-DC382D?style=for-the-badge&logo=redis&logoColor=white" alt="Redis"/>
<img src="https://img.shields.io/badge/PostgreSQL-Database-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL"/>
<br/>
<img src="https://img.shields.io/badge/React-18-20232A?style=for-the-badge&logo=react&logoColor=61DAFB" alt="React"/>
<img src="https://img.shields.io/badge/TypeScript-Strict-3178C6?style=for-the-badge&logo=typescript&logoColor=white" alt="TypeScript"/>
<img src="https://img.shields.io/badge/Tailwind-CSS-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white" alt="Tailwind"/>
<img src="https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker"/>
<img src="https://img.shields.io/badge/Groq-LLM-F55036?style=for-the-badge" alt="Groq"/>
<img src="https://img.shields.io/badge/License-MIT-10b981?style=for-the-badge" alt="MIT"/>

<br/><br/>

<img src="https://img.shields.io/badge/Precision-99.3%25-10b981?style=flat-square&labelColor=0f172a" alt="Precision"/>
<img src="https://img.shields.io/badge/Recall-98.2%25-10b981?style=flat-square&labelColor=0f172a" alt="Recall"/>
<img src="https://img.shields.io/badge/Problems%20detected-17%2F17-0d9488?style=flat-square&labelColor=0f172a" alt="Problems detected"/>
<img src="https://img.shields.io/badge/Hybrid%20search%20Hit%405-100%25-6366f1?style=flat-square&labelColor=0f172a" alt="Hybrid search"/>
<img src="https://img.shields.io/badge/Tests-239%20backend%20%2B%2039%20frontend-f59e0b?style=flat-square&labelColor=0f172a" alt="Tests"/>
<img src="https://img.shields.io/badge/Coverage-90%25-22c55e?style=flat-square&labelColor=0f172a" alt="Coverage"/>

<br/><br/>

<img src="docs/images/dashboard.png" alt="DocIntel dashboard" width="92%"/>

</div>

<br/>

> **An AI-powered document intelligence system.** It reads PDF, JPG/PNG/TIFF, XLSX/XLS and CSV files (including
> scanned documents and PDFs of about 1000 pages) with OCR, extracts invoice fields with an LLM **without inventing
> values**, validates the numbers, cross-verifies PDF-vs-PDF and PDF-vs-Excel, and makes everything searchable
> (keyword, semantic and hybrid) through a REST API and a web app.

<div align="center">

### 🎬 Walkthrough video: _add link here_

</div>

---

## ✨ Highlights

<table>
<tr>
<td width="33%" valign="top">

### 🔍 Reads anything
PDF, JPG, PNG, TIFF, XLSX, XLS, CSV. OCR only runs on pages without a text layer, so a 1000-page PDF stays fast.

</td>
<td width="33%" valign="top">

### 🛡️ Never invents values
Every extracted value must appear in the source text. If it does not, it becomes empty and is flagged for review.

</td>
<td width="33%" valign="top">

### ⚖️ Validates and cross-checks
Totals, discounts, duplicates, missing fields, and PDF-vs-PDF / PDF-vs-Excel comparison, field by field.

</td>
</tr>
<tr>
<td valign="top">

### ⚡ Background jobs
Upload returns at once. Celery + Redis process files in the background with retries and time limits.

</td>
<td valign="top">

### 🧠 Hybrid search
Keyword + semantic (local embeddings) fused with reciprocal-rank fusion. No API key needed for search.

</td>
<td valign="top">

### 🎨 Polished web app
Header with quick search and API status, profile with API token, review and correction with audit trail, mobile friendly.

</td>
</tr>
</table>

## 🖼️ Screenshots

<div align="center">

| Review an invoice | Search | Profile and API token |
|:---:|:---:|:---:|
| <img src="docs/images/review.png" alt="Review"/> | <img src="docs/images/search.png" alt="Search"/> | <img src="docs/images/profile.png" alt="Profile"/> |

<img src="docs/images/mobile.png" width="220" alt="Mobile view"/>

</div>

## 🧭 How it works

```mermaid
flowchart LR
    A([📤 Upload]):::in --> B[[⏱️ Celery job]]:::job
    B --> C[📄 Read file<br/>PDF text · OCR · sheets]:::proc
    C --> D[✂️ Split into invoices]:::proc
    D --> E[🤖 LLM extraction<br/>rule-based fallback]:::ai
    E --> F{{🛡️ Grounding check}}:::guard
    F --> G[✅ Validation]:::proc
    G --> H[⚖️ Cross-verification]:::proc
    H --> I[(🔎 Search index)]:::db
    classDef in fill:#10b981,stroke:#065f46,color:#fff
    classDef job fill:#6366f1,stroke:#3730a3,color:#fff
    classDef proc fill:#0d9488,stroke:#115e59,color:#fff
    classDef ai fill:#f59e0b,stroke:#b45309,color:#111
    classDef guard fill:#ef4444,stroke:#991b1b,color:#fff
    classDef db fill:#0f172a,stroke:#10b981,color:#fff
```

Upload -> background job (Celery) -> read the file (PDF text, OCR only where needed, spreadsheet rows) ->
split into invoices -> LLM extraction (rule-based fallback) -> grounding check (values must appear in the
document) -> validation -> cross-verification -> search index. Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

<details>
<summary><b>🗺️ Full pipeline diagram</b></summary>
<br/>

![Pipeline](docs/images/pipeline.png)

</details>

## 📋 Assignment requirements and where they are

| Requirement | Where |
|---|---|
| PDF, JPG, PNG, TIFF, XLSX, XLS, CSV input | [docs/PROCESSING.md](docs/PROCESSING.md) |
| OCR for scans; 1000-page PDFs | RapidOCR, page-by-page streaming; measured in the [rule-based evaluation report](docs/EVALUATION_REPORT_rule_based.md) (section 6, 1000 pages in 12 s) |
| LLM extraction without invented values | [docs/EXTRACTION.md](docs/EXTRACTION.md), [docs/AI_PROMPTS.md](docs/AI_PROMPTS.md) (prompt + grounding check) |
| Validation (missing fields, totals, duplicates) | [docs/EXTRACTION.md](docs/EXTRACTION.md) |
| PDF-PDF and PDF-Excel cross-verification | [docs/EXTRACTION.md](docs/EXTRACTION.md), cross-check panel in the web app |
| REST API with background jobs | [docs/API.md](docs/API.md) |
| Database with keyword and semantic search | [docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md), [docs/SEARCH.md](docs/SEARCH.md) |
| React frontend | [docs/FRONTEND.md](docs/FRONTEND.md) |
| Automated tests and results | [docs/TESTING.md](docs/TESTING.md); 239 backend + 39 frontend tests, 90% backend coverage; CI in `.github/workflows/ci.yml` |
| Evaluation report with measured metrics | [docs/EVALUATION_REPORT.md](docs/EVALUATION_REPORT.md) |
| Architecture diagram and schema | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md) |
| AI prompts and AI-assisted development disclosure | [docs/AI_PROMPTS.md](docs/AI_PROMPTS.md) |

## 📊 Measured results (synthetic benchmark)

Produced by `python manage.py run_evaluation` on 67 files / 116 invoices with exact ground truth (digital and scanned PDFs, photos,
TIFF, XLSX/XLS/CSV; some invoices carry a discount line). This run used the **LLM extractor** (Groq, `openai/gpt-oss-120b`) and the
real embedding model (`BAAI/bge-small-en-v1.5`). The same benchmark with the rule-based fallback is in
[docs/EVALUATION_REPORT_rule_based.md](docs/EVALUATION_REPORT_rule_based.md) (precision 99.7%, recall 97.4%).

| Measure | Result |
|---|---|
| Field extraction (precision / recall / F1) | **99.3% / 98.2% / 98.7%** |
| Invented values | 0.71% of returned values (7 wrong, mostly OCR misreads such as `SI/1422` read as `Sl/1422`; 0 where the document has no value) |
| Invoices found | 116 of 116, no extra invoices |
| Digital PDF and Excel/CSV registers | 100% of invoices fully correct |
| Scans / photos (recall) | 89% / 82%, limited by OCR quality |
| Injected problems detected | **17 of 17** (missing field, total mismatch, duplicate file, duplicate invoice, cross-check) |
| Alarms on files with no injected problem | 1 of 54 (a line-item mismatch) |
| PDF-vs-PDF / PDF-vs-Excel verdicts | 12 of 12 correct |
| Search, hybrid mode (Hit@1 / Hit@5 / MRR) | **94.4% / 100% / 0.972** (keyword alone: 55.6% / 55.6% / 0.556) |
| Speed | LLM mode took a median of about 9 s per file on the free Groq tier; the rule-based path takes about 25 ms per digital PDF |
| 1000-page PDF (200 invoices), rule-based | **12.0 s**, 190 MB peak memory |

> **Limits:** the data is synthetic, so real-world accuracy can be lower; scans and photos are simulated; the run is one
> machine and one seed. Full tables: [docs/EVALUATION_REPORT.md](docs/EVALUATION_REPORT.md).

## ⚠️ Known limitations

- Vectors are compared with NumPy in the application, not in a vector database (fine for tens of thousands of chunks; pgvector is the documented scale-up path).
- LLM mode makes one API call per invoice, so very large files are limited by the free-tier rate limit.
- OCR runs on CPU, so scans are slower than digital PDFs.
- The auth token is kept in `localStorage` (simple, but exposed to XSS); a production deployment would use HttpOnly cookies.
- Only English and Latin-script documents were evaluated.

## 🤖 AI-assisted development

AI tools were used to help write this project. The honest description, the prompts used by the product, and how
the output was checked are in [docs/AI_PROMPTS.md](docs/AI_PROMPTS.md).

## 🧰 Tech stack

| Layer | Technology |
|---|---|
| **Backend** | Python, Django, Django REST Framework |
| **Background jobs** | Celery + Redis |
| **Database** | PostgreSQL (SQLite for no-Docker local mode) |
| **Document processing** | PyMuPDF (PDF), RapidOCR (OCR, runs locally on CPU), openpyxl / xlrd / csv (spreadsheets) |
| **Search** | keyword + semantic (local `fastembed` embeddings, no API key) + hybrid ranking |
| **LLM** | Groq API (OpenAI-compatible, JSON mode); rule-based fallback when unavailable |
| **Frontend** | React 18, Vite, TypeScript, Tailwind CSS, TanStack Query, Vitest |

## 🚀 Setup

### Option A: Docker (recommended)

Requires Docker Desktop.

```bash
cp .env.example .env        # Windows PowerShell: copy .env.example .env
docker compose up --build
```

Then open the web app at http://localhost:3000 (API health: http://localhost:8000/api/health/ - expected):

```json
{"status": "ok", "service": "docintel-api", "database": "ok", "debug": true}
```

Create an admin user to browse the database at http://localhost:8000/admin/ :

```bash
docker compose exec api python manage.py createsuperuser
```

<details>
<summary><b>Option B: Local mode (no Docker)</b></summary>
<br/>

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

</details>

<details>
<summary><b>Web app (frontend) for local development</b></summary>
<br/>

Docker mode already serves it at http://localhost:3000. For local development (needs Node 20+):

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173 - forwards /api to http://localhost:8000
```

Create a login first: `python manage.py create_api_user alice` (run inside `backend/`, or via
`docker compose exec api python manage.py create_api_user alice`). Without Redis, set
`CELERY_TASK_ALWAYS_EAGER=true` in `.env` so uploads are processed immediately.

</details>

**Features:** sign in, multi-file drag-and-drop upload with per-file progress, live processing status,
a header with quick search and an API status indicator, a profile page (usage and API token), a footer, invoice review with validation issues (including discount), inline correction (audit trail), manual invoice entry,
PDF-vs-PDF / PDF-vs-Excel cross-check view, original file preview, extracted text per page,
invoice list with filters, and keyword / semantic / hybrid search.

### 🧪 Run the tests

```bash
cd backend
pip install -r requirements-dev.txt     # adds xlwt, used to build .xls test files
python manage.py test
```

Frontend tests and production build: `cd frontend && npm test && npm run build`.

Inside Docker: `docker compose exec api python manage.py test` (the XLS test is skipped there
because test-only packages are not installed in the image).

## 🔌 Use the REST API

Full reference: [docs/API.md](docs/API.md).

```bash
# Docker: the worker container runs background jobs automatically
docker compose exec api python manage.py create_api_user alice      # prints a token

# Local mode without Redis: run jobs inline (set in .env) ...
#   CELERY_TASK_ALWAYS_EAGER=true
# ... or with Redis, start a worker in a second terminal:
#   celery -A config worker -l info          (Windows: add --pool=solo)

TOKEN=<paste token>
curl -H "Authorization: Token $TOKEN" -F files=@invoice.pdf http://localhost:8000/api/documents/
curl -H "Authorization: Token $TOKEN" http://localhost:8000/api/documents/            # list
```

## 🔎 Search

```bash
curl -H "Authorization: Token $TOKEN" "http://localhost:8000/api/search/?q=acme+invoice&mode=hybrid"
python manage.py reindex_search        # rebuild the index (e.g. after changing the embedding model)
```

The first semantic search/indexing downloads a small embedding model (~130 MB). Without internet access the app
falls back to a built-in embedder automatically. See [docs/SEARCH.md](docs/SEARCH.md).

## 📈 Evaluation

Generate a labelled synthetic dataset and measure the real pipeline (accuracy, validation, cross-checks, search, speed):

```bash
cd backend
python manage.py generate_eval_dataset --out eval_data --seed 42
python manage.py run_evaluation --data eval_data --stress-pages 1000 --report ../docs/EVALUATION_REPORT.md
```

Details and the measured results: [docs/TESTING.md](docs/TESTING.md), [docs/EVALUATION_REPORT.md](docs/EVALUATION_REPORT.md).

## 💻 Try the pipeline from the command line

Run any PDF, image, Excel or CSV file through the full pipeline (OCR, AI extraction, validation,
cross-verification) and print the extracted invoices and any issues:

```bash
cd backend
python manage.py migrate                                   # first time only (local mode)
python manage.py process_files path/to/invoice.pdf path/to/scan.png
python manage.py process_files path/to/folder --json-out summary.json
python manage.py process_files invoice.pdf --show-text      # also print the raw extracted text
python manage.py process_files invoice.pdf --no-llm         # rule-based extraction only
```

To use the LLM, put `GROQ_API_KEY` and `GROQ_MODEL` in `.env` (see `.env.example`).
Without them the pipeline automatically uses the rule-based extractor.
Process an invoice PDF and an Excel register containing the same invoice to see cross-verification.

- [docs/PROCESSING.md](docs/PROCESSING.md): how each file type is read
- [docs/EXTRACTION.md](docs/EXTRACTION.md): AI extraction, validation and cross-verification

## 📚 Documentation

| | |
|---|---|
| 🏗️ [Architecture](docs/ARCHITECTURE.md) | 🗄️ [Database schema](docs/DATABASE_SCHEMA.md) |
| 🔌 [REST API](docs/API.md) | 🔎 [Search](docs/SEARCH.md) |
| 📄 [Document processing](docs/PROCESSING.md) | 🤖 [AI extraction, validation, cross-verification](docs/EXTRACTION.md) |
| 🎨 [Web app](docs/FRONTEND.md) | 🧪 [Testing](docs/TESTING.md) |
| 📊 [Evaluation: LLM run](docs/EVALUATION_REPORT.md) | 📉 [Evaluation: rule-based baseline](docs/EVALUATION_REPORT_rule_based.md) |
| 💬 [AI prompts and disclosure](docs/AI_PROMPTS.md) | |

## 📜 License

MIT

<div align="center">

<br/>

**Built with Django, Celery, React and a lot of care for the details.** ⭐ If you like it, give it a star!

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:34d399,55:0d9488,100:0f172a&height=140&section=footer" alt="footer wave" width="100%"/>

</div>
