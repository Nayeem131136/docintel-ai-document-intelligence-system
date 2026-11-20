import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { FileText, LayoutDashboard, LogOut, Menu, ReceiptText, ScanSearch, Search, X } from "lucide-react";
import { useAuth } from "../lib/auth";
import { cx } from "./ui";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/documents", label: "Documents", icon: FileText },
  { to: "/invoices", label: "Invoices", icon: ReceiptText },
  { to: "/search", label: "Search", icon: Search },
];

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
        <p className="truncate text-sm font-medium text-white">{user?.username}</p>
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

      <header className="sticky top-0 z-30 flex items-center justify-between bg-brand-900 px-4 py-3 lg:hidden">
        <Logo light />
        <button aria-label="Open menu" onClick={() => setOpen(true)} className="rounded-lg p-2 text-white hover:bg-white/10">
          <Menu className="h-5 w-5" />
        </button>
      </header>
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

      <main className="min-w-0 px-4 py-6 sm:px-8 lg:py-8">
        <div className="mx-auto max-w-7xl">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
