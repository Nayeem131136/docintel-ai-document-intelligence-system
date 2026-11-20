import type { DocStatus, ReviewStatus } from "../lib/types";
import { REVIEW_META, STATUS_META } from "../lib/format";
import { Badge } from "./ui";

export function StatusBadge({ status }: { status: DocStatus }) {
  const meta = STATUS_META[status] ?? { label: status, tone: "slate" };
  return <Badge tone={meta.tone} pulse={status === "processing"}>{meta.label}</Badge>;
}

export function ReviewBadge({ status }: { status: ReviewStatus }) {
  const meta = REVIEW_META[status] ?? { label: status, tone: "slate" };
  return <Badge tone={meta.tone}>{meta.label}</Badge>;
}
