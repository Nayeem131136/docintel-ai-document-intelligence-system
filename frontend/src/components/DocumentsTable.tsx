import { Link } from "react-router-dom";
import { FileImage, FileSpreadsheet, FileText, RotateCw, Trash2 } from "lucide-react";
import type { Doc } from "../lib/types";
import { formatBytes, formatDateTime, formatDuration, isActive } from "../lib/format";
import { Button, ProgressBar } from "./ui";
import { StatusBadge } from "./StatusBadge";

export function FileIcon({ type }: { type: string }) {
  const cls = "h-5 w-5 shrink-0";
  if (["xlsx", "xls", "csv"].includes(type)) return <FileSpreadsheet className={`${cls} text-emerald-600`} />;
  if (["png", "jpg", "jpeg", "tiff", "tif", "image"].includes(type)) return <FileImage className={`${cls} text-sky-600`} />;
  return <FileText className={`${cls} text-red-500`} />;
}

interface Props {
  documents: Doc[];
  compact?: boolean;
  onReprocess?: (doc: Doc) => void;
  onDelete?: (doc: Doc) => void;
}

export default function DocumentsTable({ documents, compact, onReprocess, onDelete }: Props) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead className="border-b border-slate-100 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-3 font-medium">File</th>
            <th className="px-4 py-3 font-medium">Status</th>
            {!compact && <th className="px-4 py-3 font-medium">Pages</th>}
            <th className="px-4 py-3 font-medium">Invoices</th>
            <th className="px-4 py-3 font-medium">Uploaded</th>
            {!compact && <th className="px-4 py-3 font-medium">Time</th>}
            {!compact && <th className="px-4 py-3" />}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {documents.map((doc) => (
            <tr key={doc.id} className="transition hover:bg-slate-50/70">
              <td className="max-w-[18rem] px-4 py-3">
                <Link to={`/documents/${doc.id}`} className="flex items-center gap-3 font-medium text-brand-900 hover:text-accent-700">
                  <FileIcon type={doc.file_type} />
                  <span className="min-w-0">
                    <span className="block truncate">{doc.original_filename}</span>
                    <span className="block text-xs font-normal text-slate-400">{doc.file_type.toUpperCase()} - {formatBytes(doc.size_bytes)}</span>
                  </span>
                </Link>
              </td>
              <td className="px-4 py-3">
                <div className="w-32 space-y-1.5">
                  <StatusBadge status={doc.status} />
                  {isActive(doc.status) && <ProgressBar value={doc.progress} />}
                  {doc.status === "failed" && doc.error_message && (
                    <p className="line-clamp-2 text-xs text-red-600" title={doc.error_message}>{doc.error_message}</p>
                  )}
                </div>
              </td>
              {!compact && (
                <td className="px-4 py-3 text-slate-600">
                  {isActive(doc.status) && doc.page_count ? `${doc.pages_processed}/${doc.page_count}` : doc.page_count || "-"}
                </td>
              )}
              <td className="px-4 py-3 text-slate-600">
                {doc.invoice_count}
                {doc.review_count > 0 && <span className="ml-1.5 text-xs font-medium text-amber-700">({doc.review_count} to review)</span>}
              </td>
              <td className="whitespace-nowrap px-4 py-3 text-slate-500">{formatDateTime(doc.uploaded_at)}</td>
              {!compact && <td className="whitespace-nowrap px-4 py-3 text-slate-500">{formatDuration(doc.processing_time_ms)}</td>}
              {!compact && (
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-1">
                    {doc.status === "failed" && onReprocess && (
                      <Button small variant="secondary" icon={<RotateCw className="h-3.5 w-3.5" />} onClick={() => onReprocess(doc)}>Retry</Button>
                    )}
                    {onDelete && !isActive(doc.status) && (
                      <Button small variant="ghost" aria-label={`Delete ${doc.original_filename}`} onClick={() => onDelete(doc)}>
                        <Trash2 className="h-4 w-4 text-slate-400 hover:text-red-500" />
                      </Button>
                    )}
                  </div>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
