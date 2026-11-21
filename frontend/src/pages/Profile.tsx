import { useState } from "react";
import { Check, Copy, Eye, EyeOff, KeyRound, LogOut } from "lucide-react";
import { Alert, Button, PageHeader, Skeleton } from "../components/ui";
import { getToken } from "../lib/api";
import { useAuth } from "../lib/auth";
import { formatDuration } from "../lib/format";
import { useStats } from "../lib/hooks";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 py-3 text-sm">
      <dt className="text-slate-500">{label}</dt>
      <dd className="font-medium text-slate-800">{value}</dd>
    </div>
  );
}

export default function Profile() {
  const { user, logout } = useAuth();
  const stats = useStats();
  const token = getToken() ?? "";
  const [show, setShow] = useState(false);
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(token);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setShow(true); // clipboard blocked: show the token so it can be copied by hand
    }
  }

  const s = stats.data;
  return (
    <div className="space-y-6">
      <PageHeader title="Your profile" subtitle="Account details, your usage and the API token for scripts." />

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card p-6" aria-labelledby="account-h">
          <div className="flex items-center gap-4">
            <span aria-hidden className="flex h-14 w-14 items-center justify-center rounded-full bg-brand-900 text-xl font-semibold text-white">
              {(user?.username ?? "?").charAt(0).toUpperCase()}
            </span>
            <div>
              <h2 id="account-h" className="text-lg font-semibold text-brand-900">{user?.username}</h2>
              <p className="text-sm text-slate-500">{user?.is_staff ? "Staff account" : "Member account"}</p>
            </div>
          </div>
          <dl className="mt-4 divide-y divide-slate-100">
            <Row label="Access" value={user?.is_staff ? "All users' documents" : "Your own documents only"} />
            <Row label="Sign-in" value="Token (stored in this browser)" />
          </dl>
          <Button className="mt-4" icon={<LogOut className="h-4 w-4" />} onClick={logout}>Sign out</Button>
        </section>

        <section className="card p-6" aria-labelledby="usage-h">
          <h2 id="usage-h" className="text-lg font-semibold text-brand-900">Your usage</h2>
          {stats.isLoading ? (
            <Skeleton className="mt-4 h-28" />
          ) : s ? (
            <dl className="mt-2 divide-y divide-slate-100">
              <Row label="Documents" value={String(s.documents.total)} />
              <Row label="Invoices extracted" value={String(s.invoices.total)} />
              <Row label="Invoices needing review" value={String(s.invoices.needs_review)} />
              <Row label="Open issues" value={String(s.open_issues)} />
              <Row label="Success rate" value={s.processing.success_rate == null ? "-" : `${Math.round(s.processing.success_rate * 100)}%`} />
              <Row label="Average processing time" value={s.processing.avg_time_ms == null ? "-" : formatDuration(s.processing.avg_time_ms)} />
            </dl>
          ) : (
            <p className="mt-3 text-sm text-slate-500">Statistics are not available right now.</p>
          )}
        </section>
      </div>

      <section className="card p-6" aria-labelledby="token-h">
        <div className="flex items-center gap-2">
          <KeyRound className="h-5 w-5 text-accent-600" />
          <h2 id="token-h" className="text-lg font-semibold text-brand-900">API token</h2>
        </div>
        <p className="mt-1 text-sm text-slate-500">Use it to call the REST API from scripts. Treat it like a password.</p>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <code data-testid="token" className="min-w-0 flex-1 truncate rounded-lg bg-slate-100 px-3 py-2 font-mono text-xs text-slate-700">
            {show ? token : "•".repeat(24)}
          </code>
          <Button small icon={show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />} onClick={() => setShow((v) => !v)}>
            {show ? "Hide" : "Show"}
          </Button>
          <Button small icon={copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />} onClick={copy}>
            {copied ? "Copied" : "Copy"}
          </Button>
        </div>
        <pre className="mt-4 overflow-x-auto rounded-lg bg-brand-900 p-4 text-xs leading-relaxed text-brand-100">
{`curl -H "Authorization: Token <your token>" \\
     -F files=@invoice.pdf \\
     http://localhost:8000/api/documents/`}
        </pre>
        <div className="mt-4">
          <Alert kind="info" title="Keep it private">
            Anyone with this token can act as you. Sign out on shared computers.
          </Alert>
        </div>
      </section>
    </div>
  );
}
