import type { ReactNode } from "react";

export interface FilterValues {
  supplier: string; customer: string; currency: string; review_status: string;
  date_from: string; date_to: string; min_total: string; max_total: string;
}
export const EMPTY_FILTERS: FilterValues = {
  supplier: "", customer: "", currency: "", review_status: "", date_from: "", date_to: "", min_total: "", max_total: "",
};

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <div><label className="label">{label}</label>{children}</div>;
}

export default function Filters({ values, onChange }: { values: FilterValues; onChange: (next: FilterValues) => void }) {
  const set = (key: keyof FilterValues) => (e: { target: { value: string } }) => onChange({ ...values, [key]: e.target.value });
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Field label="Supplier"><input className="input" aria-label="Supplier" value={values.supplier} onChange={set("supplier")} /></Field>
      <Field label="Customer"><input className="input" aria-label="Customer" value={values.customer} onChange={set("customer")} /></Field>
      <Field label="Currency"><input className="input" aria-label="Currency" maxLength={3} placeholder="USD" value={values.currency} onChange={set("currency")} /></Field>
      <Field label="Review status">
        <select className="input" aria-label="Review status" value={values.review_status} onChange={set("review_status")}>
          <option value="">Any</option><option value="ok">OK</option><option value="needs_review">Needs review</option><option value="reviewed">Reviewed</option>
        </select>
      </Field>
      <Field label="Date from"><input className="input" type="date" aria-label="Date from" value={values.date_from} onChange={set("date_from")} /></Field>
      <Field label="Date to"><input className="input" type="date" aria-label="Date to" value={values.date_to} onChange={set("date_to")} /></Field>
      <Field label="Min total"><input className="input" inputMode="decimal" aria-label="Min total" value={values.min_total} onChange={set("min_total")} /></Field>
      <Field label="Max total"><input className="input" inputMode="decimal" aria-label="Max total" value={values.max_total} onChange={set("max_total")} /></Field>
    </div>
  );
}
