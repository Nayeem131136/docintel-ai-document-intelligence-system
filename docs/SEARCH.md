# Search

Three modes over the signed-in user's own data: **keyword**, **semantic** and **hybrid** (default).

## What is indexed

After a document is processed, `SearchChunk` rows are created:

- one **invoice** chunk per extracted invoice: number, supplier, customer, date, total and line-item descriptions;
- **page** chunks: the extracted text of each page, split into ~1000-character overlapping pieces
  (first `EMBED_MAX_PAGES` = 3000 pages per document).

Manual corrections re-index the affected invoice. Reprocessing rebuilds the document's chunks; deleting a
document removes them. Indexing is a best-effort step: if embedding fails, the document still completes and
stays keyword-searchable.

## Modes

| Mode | How it works |
|---|---|
| `keyword` | Every query word must appear (case-insensitive). Ranked by word frequency, boosted for invoice records and exact invoice-number matches. |
| `semantic` | The query is embedded and compared with chunk vectors by cosine similarity (floor: `SEMANTIC_MIN_SCORE`). Finds related wording, not only identical words. |
| `hybrid` | Both rankings merged with reciprocal rank fusion (k=60), so exact matches and related matches both surface. |

Results are collapsed to the best hit per invoice / per page.

## Embeddings (no API key, no cost)

- Default model: `BAAI/bge-small-en-v1.5` via `fastembed` (ONNX, CPU, ~130 MB). It downloads the first
  time it is used and is cached in `.cache/fastembed` (a Docker volume in compose).
- If the model cannot be loaded (offline, blocked network) the app automatically uses a built-in hashing
  embedder (word + character n-grams). It finds shared words and spelling variants but not synonyms, so
  semantic quality is lower until the real model is available. `semantic_model` in the response tells you
  which one was used.
- Vectors are stored with the name of the model that produced them and only compared with vectors from the
  same model. After changing `EMBEDDING_MODEL`/`EMBEDDING_BACKEND` run `python manage.py reindex_search`.

## Scaling note

Vectors are stored as raw float32 bytes and compared with NumPy, which works identically on SQLite and
PostgreSQL and is fast for tens of thousands of chunks (`SEMANTIC_MAX_CANDIDATES`, default 50,000). For much
larger collections the natural next step is a pgvector column with an HNSW index (the compose database image
already ships the extension); the search interface would stay the same.

## Filters

`kind`, `file_type`, `document`, `supplier`, `customer`, `currency`, `review_status`, `date_from`, `date_to`,
`min_total`, `max_total`. Invoice-field filters restrict the search to invoice records.
