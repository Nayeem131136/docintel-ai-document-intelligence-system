# Web app

React 18 + TypeScript + Vite + Tailwind CSS. State and polling use TanStack Query; routing uses React Router.
No UI kit: the small set of components in `src/components/ui.tsx` (including the animated accents - shimmer
button, border beam, gradient text, number ticker) is written in plain Tailwind and CSS, so there is no heavy
animation dependency. Animations respect `prefers-reduced-motion`.

## Pages

| Route | Purpose |
|---|---|
| `/login` | Token sign-in |
| `/` | Dashboard: statistics, status breakdown, upload zone, recent documents |
| `/documents` | Upload, filter by status / name, retry failed, delete. Auto-refreshes while anything is processing |
| `/documents/:id` | Invoices (review + correct), cross-verification, extracted text per page, original file, activity timeline |
| `/invoices` | All invoices with filters (supplier, customer, currency, status, dates, totals, open issues) and sorting |
| `/search` | Hybrid / keyword / semantic search with filters and highlighted snippets (state kept in the URL) |

## How it talks to the API

- `src/lib/api.ts` is the only place that calls the backend (`fetch`; `XMLHttpRequest` for uploads because
  `fetch` cannot report upload progress). It attaches the token, turns error responses into readable messages
  and field errors, and signs the user out on an expired token.
- Development: Vite proxies `/api` to `http://localhost:8000` (no CORS setup). Docker: nginx serves the
  built app and proxies `/api` to the `api` service.
- The token is kept in `localStorage`. This is simple and works for a single-page app, but any XSS bug could
  read it, which is why the UI never renders server text as HTML (React escapes it; search highlighting splits
  text instead of using `innerHTML`) and the API sends restrictive headers. A production deployment would
  consider short-lived tokens or HttpOnly cookies.
- The original file is fetched with the auth header and shown from a temporary `blob:` URL.

## Review and correction

`InvoiceEditor` shows the validation issues (with an Accept button for each), highlights the fields that have
issues, validates input before saving (currency code, 2-decimal amounts), and sends only the changed fields.
The server re-validates and re-runs cross-checks; the change history shows old and new values with the note.

## Commands

```bash
npm run dev        # development server
npm test           # unit/component tests (Vitest + Testing Library)
npm run build      # type-check and production build into dist/
```

Re-theme the app by editing the `brand` and `accent` colours in `tailwind.config.js`.
