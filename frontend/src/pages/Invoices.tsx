import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ArrowDown, ArrowUp, ReceiptText, Search, SlidersHorizontal } from "lucide-react";
import Filters, { EMPTY_FILTERS, type FilterValues } from "../components/Filters";
import { ReviewBadge } from "../components/StatusBadge";
import { Alert, Badge, Button, EmptyState, PageHeader, Pagination, Spinner, cx } from "../components/ui";
import { api } from "../lib/api";
import { formatDate, formatMoney } from "../lib/format";
import { useDebounced } from "../lib/useDebounced";

const PAGE_SIZE = 25;
const COLUMNS = [
  { key: "invoice_number", label: "Invoice" },
  { key: "supplier_name", label: "Supplier" },
  { key: "invoice_date", label: "Date" },
  { key: "total", label: "Total" },
];

export default function Invoices() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [filters, setFilters] = useState<FilterValues>(EMPTY_FILTERS);
  const [showFilters, setShowFilters] = useState(false);
  const [issuesOnly, setIssuesOnly] = useState(false);
  const [ordering, setOrdering] = useState("-created_at");
  const [page, setPage] = useState(1);
  const debounced = useDebounced({ q, filters });

  const query = useQuery({
    queryKey: ["invoices", debounced, issuesOnly, ordering, page],
    queryFn: () => api.invoices({ q: debounced.q || undefined, ...debounced.filters, has_issues: issuesOnly || undefined, ordering, page, page_size: PAGE_SIZE }),
    placeholderData: (previous) => previous,
  });

  const sortBy = (key: string) => { setOrdering((c) => (c === key ? `-${key}` : key)); setPage(1); };
  const activeFilters = Object.values(filters).filter(Boolean).length;
  const data = query.data;

  return (
    <div>
      <PageHeader title="Invoices" subtitle="Every invoice extracted from your documents. Click a row to review or correct it." />
      <div className="card mb-4 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative min-w-[14rem] flex-1">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <input className="input pl-9" placeholder="Invoice number, supplier or customer" aria-label="Search invoices" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
          </div>
          <Button icon={<SlidersHorizontal className="h-4 w-4" />} onClick={() => setShowFilters((v) => !v)} aria-expanded={showFilters}>
            Filters{activeFilters ? ` (${activeFilters})` : ""}
          </Button>
          <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-600">
            <input type="checkbox" className="h-4 w-4 rounded border-slate-300 accent-accent-600" checked={issuesOnly} onChange={(e) => { setIssuesOnly(e.target.checked); setPage(1); }} />
            With open issues
          </label>
        </div>
        {showFilters && (
          <div className="mt-4 border-t border-slate-100 pt-4">
            <Filters values={filters} onChange={(f) => { setFilters(f); setPage(1); }} />
            {activeFilters > 0 && <Button small variant="ghost" className="mt-3" onClick={() => setFilters(EMPTY_FILTERS)}>Clear filters</Button>}
          </div>
        )}
      </div>

      <div className="card overflow-hidden">
        {query.isLoading ? <Spinner /> : query.isError ? (
          <div className="p-4"><Alert kind="error">{(query.error as Error).message}</Alert></div>
        ) : data && data.results.length > 0 ? (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-left text-sm">
                <thead className="border-b border-slate-100 text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    {COLUMNS.map((c) => (
                      <th key={c.key} className="px-4 py-3 font-medium" aria-sort={ordering === c.key ? "ascending" : ordering === `-${c.key}` ? "descending" : "none"}>
                        <button className="flex items-center gap-1 uppercase hover:text-brand-900" onClick={() => sortBy(c.key)}>
                          {c.label}
                          {ordering === c.key && <ArrowUp className="h-3 w-3" />}
                          {ordering === `-${c.key}` && <ArrowDown className="h-3 w-3" />}
                        </button>
                      </th>
                    ))}
                    <th className="px-4 py-3 font-medium">Customer</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                    <th className="px-4 py-3 font-medium">Source</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.results.map((inv) => (
                    <tr key={inv.id} tabIndex={0} className="cursor-pointer transition hover:bg-slate-50" onClick={() => navigate(`/documents/${inv.document}`)}
                      onKeyDown={(e) => e.key === "Enter" && navigate(`/documents/${inv.document}`)}>
                      <td className="px-4 py-3 font-medium text-brand-900">{inv.invoice_number ?? <span className="text-slate-400">-</span>}</td>
                      <td className="max-w-[14rem] truncate px-4 py-3">{inv.supplier_name ?? <span className="text-slate-400">-</span>}</td>
                      <td className="whitespace-nowrap px-4 py-3 text-slate-600">{formatDate(inv.invoice_date)}</td>
                      <td className="whitespace-nowrap px-4 py-3 font-medium tabular-nums">{formatMoney(inv.total, inv.currency)}</td>
                      <td className="max-w-[12rem] truncate px-4 py-3 text-slate-600">{inv.customer_name ?? "-"}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1.5">
                          <ReviewBadge status={inv.review_status} />
                          {inv.open_issues > 0 && <Badge tone="amber">{inv.open_issues} issue{inv.open_issues > 1 ? "s" : ""}</Badge>}
                        </div>
                      </td>
                      <td className={cx("max-w-[12rem] truncate px-4 py-3 text-xs text-slate-500")}>{inv.filename}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={page} count={data.count} pageSize={PAGE_SIZE} onChange={setPage} />
          </>
        ) : (
          <EmptyState icon={<ReceiptText className="h-6 w-6" />} title="No invoices found" hint={q || activeFilters || issuesOnly ? "Try changing or clearing the filters." : "Upload documents to see their invoices here."} />
        )}
      </div>
    </div>
  );
}
