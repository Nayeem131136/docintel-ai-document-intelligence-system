import { Link } from "react-router-dom";
import { GitCompareArrows } from "lucide-react";
import type { CrossCheck } from "../lib/types";
import { Badge, cx } from "./ui";

const TONE = { match: "green", mismatch: "red", inconclusive: "slate" } as const;
const LABEL = { pdf_pdf: "PDF vs PDF", pdf_excel: "PDF vs Excel" } as const;

export default function CrossCheckPanel({ checks, documentId }: { checks: CrossCheck[]; documentId: string }) {
  if (checks.length === 0) return null;
  return (
    <section className="card p-5" aria-label="Cross-verification">
      <h3 className="mb-3 flex items-center gap-2 font-semibold text-brand-900">
        <GitCompareArrows className="h-4 w-4 text-accent-600" /> Cross-verification
      </h3>
      <div className="space-y-4">
        {checks.map((check) => {
          const other = check.document_a === documentId ? check.document_b : check.document_a;
          const thisIsA = check.document_a === documentId;
          return (
            <div key={check.id} className="rounded-xl border border-slate-200 p-4">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <Badge tone="accent">{LABEL[check.check_type]}</Badge>
                <Badge tone={TONE[check.outcome]}>{check.outcome}</Badge>
                <Link className="text-sm font-medium text-accent-700 hover:underline" to={`/documents/${other}`}>Open the other document</Link>
              </div>
              {check.details.invoices.map((inv, i) => (
                <div key={i} className="overflow-x-auto">
                  <p className="mb-1 text-xs text-slate-500">Invoice {inv.invoice_number ?? "?"}</p>
                  <table className="w-full min-w-[420px] text-sm">
                    <thead className="text-left text-xs uppercase text-slate-500">
                      <tr><th className="py-1 font-medium">Field</th><th className="py-1 font-medium">This document</th><th className="py-1 font-medium">Other document</th></tr>
                    </thead>
                    <tbody>
                      {Object.entries(inv.fields).map(([field, v]) => (
                        <tr key={field} className={cx("border-t border-slate-100", !v.match && "bg-red-50/60")}>
                          <td className="py-1.5 pr-3 text-slate-600">{field.replace(/_/g, " ")}</td>
                          <td className="py-1.5 pr-3">{(thisIsA ? v.a : v.b) ?? "-"}</td>
                          <td className={cx("py-1.5", !v.match && "font-semibold text-red-700")}>{(thisIsA ? v.b : v.a) ?? "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </section>
  );
}
