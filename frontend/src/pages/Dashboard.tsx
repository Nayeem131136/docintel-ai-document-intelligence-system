import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle2, Clock, FileText, ReceiptText, Timer } from "lucide-react";
import DocumentsTable from "../components/DocumentsTable";
import UploadZone from "../components/UploadZone";
import { Alert, EmptyState, NumberTicker, PageHeader, Skeleton } from "../components/ui";
import { useAuth } from "../lib/auth";
import { formatDuration } from "../lib/format";
import { useDocuments, useStats } from "../lib/hooks";
import type { DocStatus } from "../lib/types";

const SEGMENTS: { status: DocStatus; label: string; color: string }[] = [
  { status: "completed", label: "Completed", color: "bg-emerald-500" },
  { status: "needs_review", label: "Needs review", color: "bg-amber-400" },
  { status: "processing", label: "Processing", color: "bg-sky-400" },
  { status: "queued", label: "Queued", color: "bg-slate-300" },
  { status: "failed", label: "Failed", color: "bg-red-500" },
];

function StatCard({ icon, label, children, hint }: { icon: React.ReactNode; label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div className="card p-5 transition hover:-translate-y-0.5 hover:shadow-md">
      <div className="flex items-center justify-between text-slate-500">
        <span className="text-sm font-medium">{label}</span>
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-50 text-brand-600">{icon}</span>
      </div>
      <p className="mt-3 text-3xl font-bold tracking-tight text-brand-900">{children}</p>
      {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
    </div>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const stats = useStats();
  const recent = useDocuments({ page_size: 5 });
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["documents"] });
    queryClient.invalidateQueries({ queryKey: ["stats"] });
  };

  const s = stats.data;
  const total = s?.documents.total ?? 0;

  return (
    <div>
      <PageHeader title={`Hello, ${user?.username}`} subtitle="Upload invoices and review what the system extracted." />

      <div className="stagger grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {stats.isLoading || !s ? (
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-32" />)
        ) : (
          <>
            <StatCard icon={<FileText className="h-4 w-4" />} label="Documents"><NumberTicker value={s.documents.total} /></StatCard>
            <StatCard icon={<ReceiptText className="h-4 w-4" />} label="Invoices extracted"><NumberTicker value={s.invoices.total} /></StatCard>
            <StatCard icon={<AlertTriangle className="h-4 w-4" />} label="Need review" hint={`${s.open_issues} open issue(s)`}>
              <NumberTicker value={s.invoices.needs_review} />
            </StatCard>
            <StatCard icon={s.processing.avg_time_ms ? <Timer className="h-4 w-4" /> : <Clock className="h-4 w-4" />} label="Success rate"
              hint={`Average ${formatDuration(s.processing.avg_time_ms)} per document`}>
              {s.processing.success_rate === null ? "-" : <NumberTicker value={s.processing.success_rate * 100} format={(n) => `${Math.round(n)}%`} />}
            </StatCard>
          </>
        )}
      </div>

      {stats.isError && <div className="mt-4"><Alert kind="error">Could not load statistics.</Alert></div>}

      {s && total > 0 && (
        <div className="card mt-4 p-5">
          <div className="flex h-2.5 overflow-hidden rounded-full bg-slate-100">
            {SEGMENTS.map(({ status, color }) => {
              const n = s.documents.by_status[status] ?? 0;
              return n ? <div key={status} className={color} style={{ width: `${(n / total) * 100}%` }} title={`${status}: ${n}`} /> : null;
            })}
          </div>
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-600">
            {SEGMENTS.map(({ status, label, color }) => (
              <span key={status} className="flex items-center gap-1.5">
                <span className={`h-2 w-2 rounded-full ${color}`} />
                {label} {s.documents.by_status[status] ?? 0}
              </span>
            ))}
          </div>
        </div>
      )}

      <section className="mt-8">
        <h2 className="mb-3 text-lg font-semibold text-brand-900">Upload documents</h2>
        <UploadZone onUploaded={refresh} />
      </section>

      <section className="mt-8">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-brand-900">Recent documents</h2>
          <Link to="/documents" className="text-sm font-medium text-accent-700 hover:underline">View all</Link>
        </div>
        <div className="card overflow-hidden">
          {recent.isLoading ? (
            <div className="space-y-3 p-4">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-10" />)}</div>
          ) : recent.data && recent.data.results.length > 0 ? (
            <DocumentsTable documents={recent.data.results} compact />
          ) : (
            <EmptyState icon={<CheckCircle2 className="h-6 w-6" />} title="No documents yet" hint="Drop your first invoice above to see the extraction in action." />
          )}
        </div>
      </section>
    </div>
  );
}
