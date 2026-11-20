import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Plus, RotateCw, ScrollText, Trash2 } from "lucide-react";
import CrossCheckPanel from "../components/CrossCheckPanel";
import { FileIcon } from "../components/DocumentsTable";
import FilePreview from "../components/FilePreview";
import InvoiceEditor from "../components/InvoiceEditor";
import { StatusBadge } from "../components/StatusBadge";
import { Alert, Badge, Button, EmptyState, Pagination, ProgressBar, Skeleton, Spinner, cx } from "../components/ui";
import { ApiError, api } from "../lib/api";
import { formatBytes, formatDateTime, formatDuration, isActive, issueLabel } from "../lib/format";
import { useToast } from "../lib/toast";

type Tab = "invoices" | "text" | "original" | "activity";

export default function DocumentDetail() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [tab, setTab] = useState<Tab>("invoices");
  const [adding, setAdding] = useState(false);
  const [pageNo, setPageNo] = useState(1);

  const results = useQuery({
    queryKey: ["results", id],
    queryFn: () => api.documentResults(id),
    refetchInterval: (q) => (q.state.data && isActive(q.state.data.document.status) ? 2000 : false),
  });
  const doc = results.data?.document;
  const active = doc ? isActive(doc.status) : false;

  // When processing finishes, refresh the lists that show this document's status.
  const wasActive = useRef(false);
  useEffect(() => {
    if (wasActive.current && doc && !active) {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey: ["stats"] });
    }
    wasActive.current = active;
  }, [active, doc, queryClient]);

  const activity = useQuery({
    queryKey: ["docstatus", id],
    queryFn: () => api.documentStatus(id),
    enabled: tab === "activity" || active,
    refetchInterval: active ? 2000 : false,
  });
  const pages = useQuery({
    queryKey: ["pages", id, pageNo],
    queryFn: () => api.documentPages(id, pageNo),
    enabled: tab === "text",
    placeholderData: keepPreviousData,
  });

  const reprocess = useMutation({
    mutationFn: (force: boolean) => api.reprocess(id, force),
    onSuccess: () => {
      notify("success", "Queued for reprocessing.");
      queryClient.invalidateQueries({ queryKey: ["results", id] });
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: (e: Error) => notify("error", e.message),
  });
  const remove = useMutation({
    mutationFn: () => api.deleteDocument(id),
    onSuccess: () => {
      notify("success", "Document deleted.");
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey: ["stats"] });
      navigate("/documents", { replace: true });
    },
    onError: (e: Error) => notify("error", e.message),
  });

  if (results.isLoading) return <div className="space-y-4"><Skeleton className="h-24" /><Skeleton className="h-64" /></div>;
  if (results.isError || !results.data || !doc) {
    const notFound = results.error instanceof ApiError && results.error.status === 404;
    return (
      <div className="space-y-4">
        <Link to="/documents" className="inline-flex items-center gap-1 text-sm text-slate-600 hover:text-brand-900"><ArrowLeft className="h-4 w-4" /> Documents</Link>
        <Alert kind="error">{notFound ? "This document does not exist or you do not have access to it." : (results.error as Error)?.message}</Alert>
      </div>
    );
  }

  const { results: invoices, document_issues: docIssues, cross_checks: checks } = results.data;
  const openDocIssues = docIssues.filter((i) => !i.resolved);
  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: "invoices", label: "Invoices", count: invoices.length },
    { key: "text", label: "Extracted text" },
    { key: "original", label: "Original file" },
    { key: "activity", label: "Activity" },
  ];

  return (
    <div>
      <Link to="/documents" className="mb-4 inline-flex items-center gap-1 text-sm text-slate-600 hover:text-brand-900"><ArrowLeft className="h-4 w-4" /> Documents</Link>

      <div className="card mb-6 p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            <FileIcon type={doc.file_type} />
            <div className="min-w-0">
              <h1 className="truncate text-xl font-bold text-brand-900">{doc.original_filename}</h1>
              <p className="text-sm text-slate-500">
                {doc.file_type.toUpperCase()} - {formatBytes(doc.size_bytes)} - {doc.page_count || 0} page(s) - uploaded {formatDateTime(doc.uploaded_at)}
                {doc.processing_time_ms ? ` - processed in ${formatDuration(doc.processing_time_ms)}` : ""}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={doc.status} />
            {!active && (
              <Button small icon={<RotateCw className="h-3.5 w-3.5" />} loading={reprocess.isPending}
                onClick={() => {
                  if (doc.status === "failed") reprocess.mutate(false);
                  else if (window.confirm("Process this document again? Manual corrections to its invoices will be replaced.")) reprocess.mutate(true);
                }}>
                {doc.status === "failed" ? "Retry" : "Reprocess"}
              </Button>
            )}
            {!active && (
              <Button small variant="danger" icon={<Trash2 className="h-3.5 w-3.5" />}
                onClick={() => window.confirm("Delete this document and its extracted data?") && remove.mutate()}>Delete</Button>
            )}
          </div>
        </div>
        {active && (
          <div className="mt-4">
            <div className="mb-1 flex justify-between text-xs text-slate-500">
              <span>{doc.status === "queued" ? "Waiting for a worker..." : `Processing${doc.page_count ? ` page ${doc.pages_processed} of ${doc.page_count}` : "..."}`}</span>
              <span>{doc.progress}%</span>
            </div>
            <ProgressBar value={doc.progress} />
          </div>
        )}
        {doc.status === "failed" && <div className="mt-4"><Alert kind="error" title="Processing failed">{doc.error_message || "Unknown error."} You can retry above.</Alert></div>}
        {doc.status !== "failed" && doc.error_message && <div className="mt-4"><Alert kind="warning">{doc.error_message}</Alert></div>}
      </div>

      <div className="mb-5 flex gap-1 overflow-x-auto border-b border-slate-200" role="tablist">
        {tabs.map((t) => (
          <button key={t.key} role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}
            className={cx("-mb-px whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium transition", tab === t.key ? "border-accent-500 text-brand-900" : "border-transparent text-slate-500 hover:text-slate-800")}>
            {t.label}{t.count !== undefined && <span className="ml-1.5 rounded-full bg-slate-100 px-1.5 py-0.5 text-xs">{t.count}</span>}
          </button>
        ))}
      </div>

      {tab === "invoices" && (
        <div className="space-y-5">
          {openDocIssues.map((issue) => (
            <Alert key={issue.id} kind={issue.severity === "error" ? "error" : issue.severity === "warning" ? "warning" : "info"} title={issueLabel(issue.code)}>{issue.message}</Alert>
          ))}
          <CrossCheckPanel checks={checks} documentId={id} />
          {invoices.map((invoice) => <InvoiceEditor key={invoice.id} documentId={id} invoice={invoice} />)}
          {invoices.length === 0 && !active && !adding && (
            <div className="card"><EmptyState icon={<ScrollText className="h-6 w-6" />} title="No invoice was extracted" hint="You can read the extracted text, or enter the invoice details yourself."
              action={<Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setAdding(true)}>Add invoice manually</Button>} /></div>
          )}
          {invoices.length === 0 && active && <Spinner label="Reading the document..." />}
          {adding && <InvoiceEditor documentId={id} invoice={null} onDone={() => setAdding(false)} />}
          {invoices.length > 0 && !adding && !active && (
            <Button icon={<Plus className="h-4 w-4" />} onClick={() => setAdding(true)}>Add another invoice manually</Button>
          )}
        </div>
      )}

      {tab === "text" && (
        <div className="space-y-4">
          {pages.isLoading ? <Spinner /> : pages.isError ? <Alert kind="error">{(pages.error as Error).message}</Alert> : pages.data && pages.data.results.length > 0 ? (
            <>
              {pages.data.results.map((p) => (
                <div key={p.page_number} className="card overflow-hidden">
                  <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 bg-slate-50/60 px-4 py-2 text-sm">
                    <span className="font-semibold text-brand-900">{p.sheet_name ? `Sheet: ${p.sheet_name}` : `Page ${p.page_number}`}</span>
                    <Badge tone={p.source === "ocr" ? "amber" : "slate"}>{p.source}</Badge>
                    {p.ocr_confidence ? <span className="text-xs text-slate-500">OCR confidence {Math.round(p.ocr_confidence * 100)}%</span> : null}
                    {p.has_error && <Badge tone="red">Could not be read</Badge>}
                  </div>
                  <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words p-4 font-mono text-xs leading-relaxed text-slate-700">{p.text || p.error_message || "(no text)"}</pre>
                </div>
              ))}
              <div className="card"><Pagination page={pageNo} count={pages.data.count} pageSize={20} onChange={setPageNo} /></div>
            </>
          ) : <EmptyState icon={<ScrollText className="h-6 w-6" />} title="No text yet" hint="Text appears once processing has read the document." />}
        </div>
      )}

      {tab === "original" && <FilePreview id={id} type={doc.file_type} name={doc.original_filename} />}

      {tab === "activity" && (
        <div className="card p-5">
          {activity.isLoading ? <Spinner /> : (
            <ol className="relative space-y-4 border-l border-slate-200 pl-5">
              {activity.data?.events.map((e, i) => (
                <li key={i} className="relative">
                  <span className={cx("absolute -left-[1.62rem] top-1.5 h-2.5 w-2.5 rounded-full ring-4 ring-white", e.outcome === "success" ? "bg-emerald-500" : e.outcome === "failed" ? "bg-red-500" : "bg-amber-400")} />
                  <p className="text-sm font-medium text-slate-800">{e.stage.replace(/_/g, " ")} <span className="font-normal text-slate-400">- {e.outcome}</span></p>
                  {e.message && <p className="text-sm text-slate-600">{e.message}</p>}
                  <p className="text-xs text-slate-400">{formatDateTime(e.created_at)}{e.duration_ms ? ` - ${formatDuration(e.duration_ms)}` : ""}</p>
                </li>
              ))}
              {activity.data?.events.length === 0 && <p className="text-sm text-slate-500">No events recorded.</p>}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}
