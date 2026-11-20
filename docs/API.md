# REST API

Base URL (local): `http://localhost:8000/api/`. All endpoints except `health/` and `auth/token/` need
`Authorization: Token <token>`. Responses are JSON. Lists are paginated:
`{"count", "next", "previous", "results"}` (`?page=`, `?page_size=` up to 100).

## Authentication

Create a user and get a token:

```bash
python manage.py create_api_user alice            # prompts for a password, prints the token
python manage.py create_api_user admin --staff    # staff users can see every user's documents
```

Or log in over HTTP:

```bash
curl -X POST http://localhost:8000/api/auth/token/ -d username=alice -d password=...
# {"token": "..."}
```

Every user sees only their own documents (404 for anything else). Staff see all.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health/` | Liveness + database check (public) |
| POST | `/auth/token/` | Exchange username/password for a token (20/min limit) |
| GET | `/auth/me/` | Current user |
| POST | `/documents/` | Upload one or more files (`files` field, multipart). Returns **202** immediately; processing runs in the background |
| GET | `/documents/` | List. Filters: `status`, `file_type`, `q` (filename), `ordering` |
| GET | `/documents/{id}/` | Document detail |
| DELETE | `/documents/{id}/` | Delete document, file and results |
| GET | `/documents/{id}/status/` | Status, progress %, processing events (poll this) |
| GET | `/documents/{id}/results/` | Extracted invoices, line items, issues, cross-checks |
| POST | `/documents/{id}/results/` | Manually enter an invoice (when nothing was extracted) |
| GET | `/documents/{id}/pages/` | Extracted text per page (`?include_text=false` for a light list) |
| GET | `/documents/{id}/file/` | Original file (`?download=1` forces download) |
| POST | `/documents/{id}/reprocess/` | Re-run a failed document; finished ones need `{"force": true}` |
| POST | `/documents/reprocess-failed/` | Re-queue all of your failed documents |
| GET | `/results/{id}/` | One extracted invoice |
| PATCH | `/results/{id}/` | Manual correction (re-validates, re-runs cross-checks, writes audit log) |
| POST | `/results/{id}/approve/` | Mark the invoice as reviewed and resolve its issues |
| POST | `/issues/{id}/resolve/` | Resolve one validation issue |
| GET | `/stats/` | Counts by status, success rate, invoice totals |

## Examples

```bash
TOKEN=...
# upload several files at once
curl -H "Authorization: Token $TOKEN" -F files=@invoice.pdf -F files=@register.xlsx \
     http://localhost:8000/api/documents/

# poll
curl -H "Authorization: Token $TOKEN" http://localhost:8000/api/documents/<id>/status/

# fix a wrong total
curl -X PATCH -H "Authorization: Token $TOKEN" -H "Content-Type: application/json" \
     -d '{"total": "192.50", "note": "typo on the invoice"}' \
     http://localhost:8000/api/results/<id>/
```

Upload response (partial success is allowed):

```json
{"documents": [{"id": "...", "status": "queued", "...": "..."}],
 "rejected": [{"filename": "notes.docx", "error": "Unsupported file type ..."}]}
```

## Status codes

`202` accepted for processing, `400` validation error (all files rejected, bad correction),
`401` missing/invalid token, `404` not found or not yours, `409` conflict (reprocess of an active or
finished document without `force`, edit while processing), `429` rate limited.

## Document statuses

`queued` -> `processing` -> `completed` | `needs_review` | `failed`. `needs_review` means at least
one open error/warning exists (missing field, totals mismatch, duplicate, cross-check mismatch...).
After corrections or approval it becomes `completed`.

## Background processing and reliability

- Upload saves the file, then enqueues a Celery task after the DB commit. If the broker is down the
  document is marked `failed` ("could not be queued") and can be reprocessed.
- Tasks are idempotent: a duplicate message for an already-processed document is skipped; a
  redelivered message after a worker crash resumes the interrupted document.
- Time limits turn runaway jobs into `failed` documents with a clear message.
- `python manage.py recover_stuck_documents --minutes 60` fails documents stuck in `processing` and
  re-queues stale `queued` ones (run it from cron or by hand after a crash).

## Security notes

- Token auth, per-user object isolation, rate limits (login 20/min, uploads 200/h, reprocess 60/h).
- Uploads: extension allow-list, **content sniffing** (magic bytes must match), size and file-count
  limits, zip-bomb and image-bomb guards, random on-disk names, sanitised display names.
- Original files are served with `nosniff` and a sandboxing CSP; non-PDF/image types are forced to download.
- Error messages never include server paths or stack traces (details go to server logs only).
- Extracted text is passed to the LLM inside delimited tags and the output is strictly parsed
  (prompt-injection hardening).
