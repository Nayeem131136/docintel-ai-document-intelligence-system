import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileStack, RotateCw, Search } from "lucide-react";
import DocumentsTable from "../components/DocumentsTable";
import UploadZone from "../components/UploadZone";
import { Alert, Button, EmptyState, PageHeader, Pagination, Spinner, cx } from "../components/ui";
import { api } from "../lib/api";
import { STATUS_META } from "../lib/format";
import { useDocuments } from "../lib/hooks";
import { useToast } from "../lib/toast";
import type { Doc, DocStatus } from "../lib/types";

const PAGE_SIZE = 20;
const FILTERS: { value: DocStatus | ""; label: string }[] = [
  { value: "", label: "All" },
  ...(["processing", "queued", "completed", "needs_review", "failed"] as DocStatus[]).map((v) => ({ value: v, label: STATUS_META[v].label })),
];

export default function Documents() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [status, setStatus] = useState<DocStatus | "">("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const documents = useDocuments({ status: status || undefined, q: q || undefined, page, page_size: PAGE_SIZE });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["documents"] });
    queryClient.invalidateQueries({ queryKey: ["stats"] });
  };
  const retry = useMutation({
    mutationFn: (doc: Doc) => api.reprocess(doc.id),
    onSuccess: () => { notify("success", "Queued for reprocessing."); refresh(); },
    onError: (e: Error) => notify("error", e.message),
  });
  const retryAll = useMutation({
    mutationFn: api.reprocessFailed,
    onSuccess: (r) => { notify("success", r.queued ? `${r.queued} document(s) queued again.` : "No failed documents."); refresh(); },
    onError: (e: Error) => notify("error", e.message),
  });
  const remove = useMutation({
    mutationFn: (doc: Doc) => api.deleteDocument(doc.id),
    onSuccess: () => { notify("success", "Document deleted."); refresh(); },
    onError: (e: Error) => notify("error", e.message),
  });

  const data = documents.data;
  return (
    <div>
      <PageHeader
        title="Documents"
        subtitle="Everything you have uploaded. Statuses update automatically while files are processing."
        actions={<Button icon={<RotateCw className="h-4 w-4" />} loading={retryAll.isPending} onClick={() => retryAll.mutate()}>Retry all failed</Button>}
      />
      <UploadZone onUploaded={refresh} />

      <div className="mb-3 mt-8 flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Filter by status">
          {FILTERS.map((f) => (
            <button key={f.value} role="tab" aria-selected={status === f.value}
              onClick={() => { setStatus(f.value); setPage(1); }}
              className={cx("rounded-full px-3 py-1 text-xs font-medium transition", status === f.value ? "bg-brand-900 text-white" : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50")}>
              {f.label}
            </button>
          ))}
        </div>
        <div className="relative ml-auto w-full sm:w-64">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
          <input className="input pl-9" placeholder="Filter by file name" aria-label="Filter by file name" value={q}
            onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        </div>
      </div>

      <div className="card overflow-hidden">
        {documents.isLoading ? <Spinner /> : documents.isError ? (
          <div className="p-4"><Alert kind="error">{(documents.error as Error).message}</Alert></div>
        ) : data && data.results.length > 0 ? (
          <>
            <DocumentsTable documents={data.results} onReprocess={(d) => retry.mutate(d)}
              onDelete={(d) => window.confirm(`Delete "${d.original_filename}" and its extracted data?`) && remove.mutate(d)} />
            <Pagination page={page} count={data.count} pageSize={PAGE_SIZE} onChange={setPage} />
          </>
        ) : (
          <EmptyState icon={<FileStack className="h-6 w-6" />} title="No documents found" hint={status || q ? "Try clearing the filters." : "Upload a file to get started."} />
        )}
      </div>
    </div>
  );
}
