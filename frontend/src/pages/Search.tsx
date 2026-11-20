import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { FileText, ReceiptText, Search as SearchIcon, SlidersHorizontal, Sparkles } from "lucide-react";
import Filters, { EMPTY_FILTERS, type FilterValues } from "../components/Filters";
import Highlight from "../components/Highlight";
import { ReviewBadge } from "../components/StatusBadge";
import { Alert, Badge, Button, EmptyState, PageHeader, Spinner, cx } from "../components/ui";
import { api } from "../lib/api";
import { formatDate, formatMoney } from "../lib/format";
import { useDebounced } from "../lib/useDebounced";

const MODES = [
  { value: "hybrid", label: "Hybrid", hint: "Exact words and related meaning, combined" },
  { value: "keyword", label: "Keyword", hint: "Every word must appear" },
  { value: "semantic", label: "Semantic", hint: "Finds related wording, not only identical words" },
];
const KINDS = [{ value: "", label: "Everything" }, { value: "invoice", label: "Invoices" }, { value: "page", label: "Page text" }];

export default function SearchPage() {
  const [params, setParams] = useSearchParams();
  const [text, setText] = useState(params.get("q") ?? "");
  const [mode, setMode] = useState(params.get("mode") ?? "hybrid");
  const [kind, setKind] = useState(params.get("kind") ?? "");
  const [filters, setFilters] = useState<FilterValues>(EMPTY_FILTERS);
  const [showFilters, setShowFilters] = useState(false);
  const debounced = useDebounced({ text: text.trim(), filters });
  const ready = debounced.text.length >= 2;

  const search = useQuery({
    queryKey: ["search", debounced, mode, kind],
    queryFn: () => api.search({ q: debounced.text, mode, kind: kind || undefined, limit: 30, ...debounced.filters }),
    enabled: ready,
    placeholderData: (previous) => previous,
  });

  const sync = (next: Record<string, string>) => {
    const merged = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) v ? merged.set(k, v) : merged.delete(k);
    setParams(merged, { replace: true });
  };
  const activeFilters = Object.values(filters).filter(Boolean).length;
  const data = search.data;

  return (
    <div>
      <PageHeader title="Search" subtitle="Find invoices and document text by number, supplier, item or meaning." />

      <div className="card mb-4 space-y-4 p-4">
        <div className="relative">
          <SearchIcon className="pointer-events-none absolute left-3.5 top-3 h-5 w-5 text-slate-400" />
          <input className="input py-2.5 pl-11 text-base" autoFocus placeholder='Try "INV-1001", "office furniture" or a supplier name' aria-label="Search query"
            value={text} onChange={(e) => { setText(e.target.value); sync({ q: e.target.value }); }} />
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="inline-flex rounded-lg bg-slate-100 p-1" role="radiogroup" aria-label="Search mode">
            {MODES.map((m) => (
              <button key={m.value} role="radio" aria-checked={mode === m.value} title={m.hint}
                onClick={() => { setMode(m.value); sync({ mode: m.value }); }}
                className={cx("rounded-md px-3 py-1.5 text-sm font-medium transition", mode === m.value ? "bg-white text-brand-900 shadow-sm" : "text-slate-500 hover:text-slate-800")}>
                {m.label}
              </button>
            ))}
          </div>
          <div className="inline-flex rounded-lg bg-slate-100 p-1" role="radiogroup" aria-label="Result type">
            {KINDS.map((k) => (
              <button key={k.value} role="radio" aria-checked={kind === k.value} onClick={() => { setKind(k.value); sync({ kind: k.value }); }}
                className={cx("rounded-md px-3 py-1.5 text-sm font-medium transition", kind === k.value ? "bg-white text-brand-900 shadow-sm" : "text-slate-500 hover:text-slate-800")}>
                {k.label}
              </button>
            ))}
          </div>
          <Button small icon={<SlidersHorizontal className="h-3.5 w-3.5" />} onClick={() => setShowFilters((v) => !v)} aria-expanded={showFilters}>
            Filters{activeFilters ? ` (${activeFilters})` : ""}
          </Button>
        </div>
        {showFilters && (
          <div className="border-t border-slate-100 pt-4">
            <Filters values={filters} onChange={setFilters} />
            <p className="mt-2 text-xs text-slate-500">Invoice filters limit the search to invoice records.</p>
          </div>
        )}
      </div>

      {!ready ? (
        <div className="card"><EmptyState icon={<Sparkles className="h-6 w-6" />} title="Search your documents" hint="Type at least two characters. Hybrid mode finds both exact matches and related wording." /></div>
      ) : search.isError ? (
        <Alert kind="error">{(search.error as Error).message}</Alert>
      ) : search.isLoading ? <Spinner label="Searching..." /> : data && (
        <div className="space-y-3">
          <p className="text-sm text-slate-500">
            {data.count} result{data.count === 1 ? "" : "s"}
            {data.semantic_model && (
              <> - meaning search by <code className="rounded bg-slate-100 px-1 text-xs">{data.semantic_model}</code>
                {data.semantic_model.startsWith("hashing") && <span className="text-amber-700"> (basic offline fallback - the full model was not available)</span>}</>
            )}
            {search.isFetching && " - updating..."}
          </p>
          {data.results.length === 0 && <div className="card"><EmptyState icon={<SearchIcon className="h-6 w-6" />} title="No matches" hint="Try fewer or different words, or switch to Semantic mode." /></div>}
          <ul className="stagger space-y-3">
            {data.results.map((hit, i) => (
              <li key={`${hit.document.id}-${hit.kind}-${hit.page_number}-${hit.invoice?.id ?? i}`}>
                <Link to={`/documents/${hit.document.id}`} className="card block p-4 transition hover:-translate-y-0.5 hover:border-accent-400 hover:shadow-md">
                  <div className="flex flex-wrap items-center gap-2">
                    {hit.kind === "invoice" ? <ReceiptText className="h-4 w-4 text-accent-600" /> : <FileText className="h-4 w-4 text-slate-400" />}
                    <span className="font-semibold text-brand-900">
                      {hit.kind === "invoice" ? `Invoice ${hit.invoice?.invoice_number ?? "(no number)"}` : `Page ${hit.page_number ?? "?"}`}
                    </span>
                    <span className="text-sm text-slate-500">in {hit.document.filename}</span>
                    {hit.invoice && <ReviewBadge status={hit.invoice.review_status} />}
                    <span className="ml-auto flex gap-1.5">
                      {hit.keyword_score !== null && <Badge tone="blue">keyword</Badge>}
                      {hit.semantic_score !== null && <Badge tone="accent">meaning {Math.round(hit.semantic_score * 100)}%</Badge>}
                    </span>
                  </div>
                  {hit.invoice && (
                    <p className="mt-1.5 text-sm text-slate-600">
                      {hit.invoice.supplier_name ?? "Unknown supplier"} - {formatDate(hit.invoice.invoice_date)} -{" "}
                      <span className="font-medium tabular-nums text-slate-800">{formatMoney(hit.invoice.total, hit.invoice.currency)}</span>
                    </p>
                  )}
                  <p className="mt-2 text-sm leading-relaxed text-slate-600"><Highlight text={hit.snippet} terms={data.terms} /></p>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
