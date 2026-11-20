import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { FileCheck2, ScanSearch, SearchCheck, ShieldCheck } from "lucide-react";
import { Alert, BorderBeam, GradientText, ShimmerButton } from "../components/ui";
import { useAuth } from "../lib/auth";

const POINTS = [
  { icon: ScanSearch, text: "OCR and AI extraction from PDFs, scans and spreadsheets" },
  { icon: ShieldCheck, text: "Automatic checks: totals, duplicates, missing fields, cross-verification" },
  { icon: SearchCheck, text: "Keyword and semantic search across every invoice" },
];

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(username, password);
      navigate((location.state as { from?: string } | null)?.from ?? "/", { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sign in failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="dot-pattern grid min-h-screen bg-brand-900 lg:grid-cols-2">
      <div className="hidden flex-col justify-center px-14 text-white lg:flex">
        <div className="mb-8 flex h-12 w-12 animate-float items-center justify-center rounded-2xl bg-white/10 ring-1 ring-white/20">
          <FileCheck2 className="h-6 w-6 text-accent-400" />
        </div>
        <h1 className="text-4xl font-bold leading-tight tracking-tight">
          From raw invoices to <GradientText>verified, searchable data</GradientText>
        </h1>
        <ul className="stagger mt-8 space-y-4">
          {POINTS.map(({ icon: Icon, text }) => (
            <li key={text} className="flex items-start gap-3 text-brand-200">
              <Icon className="mt-0.5 h-5 w-5 shrink-0 text-accent-400" />
              {text}
            </li>
          ))}
        </ul>
      </div>
      <div className="flex items-center justify-center p-6">
        <BorderBeam className="w-full max-w-md rounded-2xl">
          <form onSubmit={submit} className="animate-fade-up rounded-2xl bg-white p-8 shadow-2xl" aria-label="Sign in">
            <h2 className="text-2xl font-bold text-brand-900">Welcome back</h2>
            <p className="mt-1 text-sm text-slate-500">Sign in to your DocIntel workspace.</p>
            <div className="mt-6 space-y-4">
              {error && <Alert kind="error">{error}</Alert>}
              <div>
                <label className="label" htmlFor="username">Username</label>
                <input id="username" className="input" autoComplete="username" autoFocus required value={username} onChange={(e) => setUsername(e.target.value)} />
              </div>
              <div>
                <label className="label" htmlFor="password">Password</label>
                <input id="password" type="password" className="input" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
              </div>
              <ShimmerButton type="submit" loading={busy} className="w-full">Sign in</ShimmerButton>
            </div>
            <p className="mt-5 text-xs text-slate-400">
              No account yet? Ask an administrator, or run <code className="rounded bg-slate-100 px-1">python manage.py create_api_user</code>.
            </p>
          </form>
        </BorderBeam>
      </div>
    </div>
  );
}
