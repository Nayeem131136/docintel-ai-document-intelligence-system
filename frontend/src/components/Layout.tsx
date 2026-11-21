import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  FileText, HeartPulse, LayoutDashboard, LogOut, Menu, ReceiptText, ScanSearch, Search, ShieldCheck, X,
} from "lucide-react";
import { checkHealth } from "../lib/api";
import { useAuth } from "../lib/auth";
import { cx } from "./ui";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/documents", label: "Documents", icon: FileText },
  { to: "/invoices", label: "Invoices", icon: ReceiptText },
  { to: "/search", label: "Search", icon: Search },
];

/** Title shown in the header for the current route. */
export function titleFor(pathname: string): string {
  if (pathname === "/") return "Dashboard";
  if (pathname.startsWith("/documents/")) return "Document";
  if (pathname === "/profile") return "Profile";
  const match = NAV.find((item) => !item.end && pathname.startsWith(item.to));
  return match ? match.label : "DocIntel";
}

export function Logo({ light }: { light?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-white/10 ring-1 ring-white/20">
        <ScanSearch className="h-5 w-5 text-accent-400" />
      </div>
      <div className="leading-tight">
        <p className={cx("text-lg font-bold tracking-tight", light ? "text-white" : "text-brand-900")}>DocIntel</p>
        <p className="text-[10px] uppercase tracking-[.18em] text-accent-400">Document intelligence</p>
      </div>
    </div>
  );
}

function ApiStatus() {
  const { data, isLoading } = useQuery({ queryKey: ["health"], queryFn: checkHealth, refetchInterval: 30_000, retry: false });
  const online = data === true;
  const label = isLoading ? "Checking API" : online ? "API online" : "API offline";
  return (
    <span
      role="status"
      title={online ? "The server is reachable" : "Cannot reach the server"}
      className={cx(
        "hidden items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 sm:inline-flex",
        isLoading ? "bg-slate-100 text-slate-500 ring-slate-200" : online ? "bg-accent-50 text-accent-700 ring-accent-100" : "bg-red-50 text-red-700 ring-red-200",
      )}
    >
      <span className={cx("h-1.5 w-1.5 rounded-full", isLoading ? "bg-slate-400" : online ? "bg-accent-500" : "bg-red-500")} />
      {label}
    </span>
  );
}

function QuickSearch() {
  const navigate = useNavigate();
  const [text, setText] = useState("");
  function submit(event: FormEvent) {
    event.preventDefault();
    const query = text.trim();
    if (query) navigate(`/search?q=${encodeURIComponent(query)}`);
  }
  return (
    <form onSubmit={submit} role="search" className="relative hidden w-full max-w-sm md:block">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        aria-label="Quick search"
        placeholder="Search invoices and documents"
        className="input pl-9"
      />
    </form>
  );
}

function AppHeader({ onMenu }: { onMenu: () => void }) {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();
  const initial = (user?.username ?? "?").charAt(0).toUpperCase();
  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/85 backdrop-blur">
      <div className="flex items-center gap-3 px-4 py-3 sm:px-8">
        <button aria-label="Open menu" onClick={onMenu} className="rounded-lg p-2 text-brand-900 hover:bg-slate-100 lg:hidden">
          <Menu className="h-5 w-5" />
        </button>
        <Link to="/" className="lg:hidden" aria-label="DocIntel home">
          <Logo />
        </Link>
        <h2 className="hidden text-base font-semibold tracking-tight text-brand-900 lg:block" data-testid="page-title">
          {titleFor(pathname)}
        </h2>
        <div className="ml-auto flex flex-1 items-center justify-end gap-3">
          <QuickSearch />
          <Link to="/search" aria-label="Search" className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 md:hidden">
            <Search className="h-5 w-5" />
          </Link>
          <ApiStatus />
          <div className="flex items-center gap-2 border-l border-slate-200 pl-3">
            <Link to="/profile" aria-label="Your profile" title="Your profile" className="flex items-center gap-2 rounded-lg p-1 hover:bg-slate-100">
              <span aria-hidden className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-900 text-sm font-semibold text-white">
                {initial}
              </span>
              <div className="hidden leading-tight sm:block">
                <p className="max-w-[9rem] truncate text-sm font-medium text-slate-800">{user?.username}</p>
                <p className="text-[11px] text-slate-500">{user?.is_staff ? "Staff" : "Member"}</p>
              </div>
            </Link>
            <button onClick={logout} aria-label="Sign out" title="Sign out" className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-800">
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}

export function AppFooter() {
  const year = new Date().getFullYear();
  return (
    <footer className="mt-12 border-t border-slate-200 bg-white">
      <div className="mx-auto grid max-w-7xl gap-8 px-4 py-8 sm:px-8 md:grid-cols-[1.4fr_1fr_1fr]">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-900">
              <ScanSearch className="h-4 w-4 text-accent-400" />
            </span>
            <span className="text-base font-bold tracking-tight text-brand-900">DocIntel</span>
          </div>
          <p className="mt-3 max-w-sm text-sm text-slate-500">
            From raw invoices to verified, searchable data. OCR and an LLM read your documents; every number is checked against the source.
          </p>
        </div>
        <nav aria-label="Footer product" className="text-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Product</p>
          <ul className="mt-3 space-y-2">
            {NAV.map(({ to, label }) => (
              <li key={to}>
                <NavLink to={to} end={to === "/"} className="text-slate-600 hover:text-accent-700">{label}</NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="text-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Good to know</p>
          <ul className="mt-3 space-y-2 text-slate-600">
            <li className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-accent-600" /> Missing values stay empty, never guessed</li>
            <li><NavLink to="/profile" className="hover:text-accent-700">Your profile and API token</NavLink></li>
            <li className="flex items-center gap-2"><HeartPulse className="h-4 w-4 text-accent-600" />
              <a href="/api/health/" target="_blank" rel="noreferrer" className="hover:text-accent-700">API health check</a>
            </li>
          </ul>
        </div>
      </div>
      <div className="border-t border-slate-100">
        <div className="mx-auto flex max-w-7xl flex-col gap-1 px-4 py-4 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <p>&copy; {year} DocIntel. Always review extracted values before relying on them.</p>
          <p>Built with Django, Celery, React and Tailwind CSS.</p>
        </div>
      </div>
    </footer>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);

  const sidebar = (
    <div className="dot-pattern flex h-full flex-col bg-brand-900 px-4 py-6">
      <Logo light />
      <nav className="mt-8 flex flex-1 flex-col gap-1" aria-label="Main">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={() => setOpen(false)}
            className={({ isActive }) =>
              cx(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition",
                isActive ? "bg-white/10 text-white shadow-inner ring-1 ring-white/10" : "text-brand-200 hover:bg-white/5 hover:text-white",
              )
            }
          >
            <Icon className="h-[18px] w-[18px]" />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="rounded-xl bg-white/5 p-3 ring-1 ring-white/10">
        <NavLink to="/profile" onClick={() => setOpen(false)} className="block truncate text-sm font-medium text-white hover:underline">{user?.username}</NavLink>
        <p className="text-xs text-brand-300">{user?.is_staff ? "Staff - sees all documents" : "Your workspace"}</p>
        <button onClick={logout} className="mt-2 flex items-center gap-2 text-xs font-medium text-accent-400 hover:text-accent-100">
          <LogOut className="h-3.5 w-3.5" /> Sign out
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[16rem_1fr]">
      <aside className="sticky top-0 hidden h-screen lg:block">{sidebar}</aside>

      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-64 animate-fade-up">
            {sidebar}
            <button aria-label="Close menu" onClick={() => setOpen(false)} className="absolute right-2 top-2 rounded-lg p-2 text-white hover:bg-white/10">
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>
      )}

      <div className="flex min-h-screen min-w-0 flex-col">
        <AppHeader onMenu={() => setOpen(true)} />
        <main className="min-w-0 flex-1 px-4 py-6 sm:px-8 lg:py-8">
          <div className="mx-auto max-w-7xl">
            <Outlet />
          </div>
        </main>
        <AppFooter />
      </div>
    </div>
  );
}
