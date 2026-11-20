import { useEffect, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, Loader2, XCircle } from "lucide-react";

export const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(" ");

type Variant = "primary" | "secondary" | "ghost" | "danger";
interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  loading?: boolean;
  small?: boolean;
  icon?: ReactNode;
}
const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand-900 text-white hover:bg-brand-700 shadow-sm",
  secondary: "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50",
  ghost: "text-slate-600 hover:bg-slate-100",
  danger: "border border-red-200 bg-white text-red-600 hover:bg-red-50",
};
export function Button({ variant = "secondary", loading, small, icon, className, children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition active:scale-[.98] disabled:cursor-not-allowed disabled:opacity-60",
        small ? "px-2.5 py-1.5 text-xs" : "px-4 py-2 text-sm",
        VARIANTS[variant],
        className,
      )}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : icon}
      {children}
    </button>
  );
}

/** Magic UI "shimmer button": a light sweeps across a dark button. */
export function ShimmerButton({ className, children, loading, disabled, ...rest }: ButtonProps) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={cx(
        "group relative inline-flex items-center justify-center gap-2 overflow-hidden rounded-lg bg-brand-900 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-brand-900/20 transition active:scale-[.98] disabled:cursor-not-allowed disabled:opacity-60",
        className,
      )}
    >
      <span className="pointer-events-none absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-white/25 to-transparent" />
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      <span className="relative">{children}</span>
    </button>
  );
}

/** Magic UI "animated gradient text". */
export function GradientText({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={cx("animate-gradient bg-gradient-to-r from-accent-400 via-sky-300 to-accent-400 bg-[length:200%_auto] bg-clip-text text-transparent", className)}>
      {children}
    </span>
  );
}

/** Magic UI "number ticker": counts up to the value. */
export function NumberTicker({ value, format }: { value: number; format?: (n: number) => string }) {
  const [shown, setShown] = useState(0);
  const frame = useRef<number>();
  useEffect(() => {
    const reduce = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setShown(value);
      return;
    }
    const start = performance.now();
    const from = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / 900);
      setShown(from + (value - from) * (1 - Math.pow(1 - t, 3)));
      if (t < 1) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => {
      if (frame.current) cancelAnimationFrame(frame.current);
    };
  }, [value]);
  const text = format ? format(shown) : Math.round(shown).toLocaleString("en-US");
  return <span>{text}</span>;
}

export function BorderBeam({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("beam-wrap", className)}>{children}</div>;
}

const TONES: Record<string, string> = {
  slate: "bg-slate-100 text-slate-700 ring-slate-200",
  blue: "bg-sky-50 text-sky-700 ring-sky-200",
  green: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  amber: "bg-amber-50 text-amber-800 ring-amber-200",
  red: "bg-red-50 text-red-700 ring-red-200",
  accent: "bg-accent-50 text-accent-700 ring-accent-100",
};
export function Badge({ tone = "slate", children, pulse }: { tone?: string; children: ReactNode; pulse?: boolean }) {
  return (
    <span className={cx("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset", TONES[tone] ?? TONES.slate)}>
      {pulse && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />}
      {children}
    </span>
  );
}

export function ProgressBar({ value, tone = "accent" }: { value: number; tone?: "accent" | "red" }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
      <div className={cx("h-full rounded-full transition-all duration-500", tone === "red" ? "bg-red-500" : "bg-gradient-to-r from-accent-500 to-accent-400")} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-slate-500" role="status">
      <Loader2 className="h-5 w-5 animate-spin text-accent-600" />
      {label ?? "Loading..."}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("animate-pulse rounded-lg bg-slate-200/70", className)} />;
}

const ALERTS = {
  error: { icon: XCircle, cls: "border-red-200 bg-red-50 text-red-800" },
  warning: { icon: AlertTriangle, cls: "border-amber-200 bg-amber-50 text-amber-900" },
  info: { icon: Info, cls: "border-sky-200 bg-sky-50 text-sky-900" },
  success: { icon: CheckCircle2, cls: "border-emerald-200 bg-emerald-50 text-emerald-900" },
};
export function Alert({ kind = "info", title, children }: { kind?: keyof typeof ALERTS; title?: string; children?: ReactNode }) {
  const { icon: Icon, cls } = ALERTS[kind];
  return (
    <div role={kind === "error" ? "alert" : "status"} className={cx("flex gap-3 rounded-xl border p-3 text-sm", cls)}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div>
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className={title ? "mt-0.5" : ""}>{children}</div>}
      </div>
    </div>
  );
}

export function EmptyState({ icon, title, hint, action }: { icon: ReactNode; title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center px-6 py-14 text-center">
      <div className="mb-3 flex h-12 w-12 animate-float items-center justify-center rounded-2xl bg-brand-50 text-brand-500">{icon}</div>
      <p className="font-semibold text-slate-800">{title}</p>
      {hint && <p className="mt-1 max-w-sm text-sm text-slate-500">{hint}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-brand-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Pagination({ page, count, pageSize, onChange }: { page: number; count: number; pageSize: number; onChange: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(count / pageSize));
  if (pages <= 1) return null;
  return (
    <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3 text-sm text-slate-500">
      <span>{count.toLocaleString("en-US")} total</span>
      <div className="flex items-center gap-2">
        <Button small disabled={page <= 1} onClick={() => onChange(page - 1)}>Previous</Button>
        <span>Page {page} of {pages}</span>
        <Button small disabled={page >= pages} onClick={() => onChange(page + 1)}>Next</Button>
      </div>
    </div>
  );
}

export function ConfirmButton({ label, confirm, onConfirm, ...rest }: { label: ReactNode; confirm: string; onConfirm: () => void } & Omit<ButtonProps, "onClick">) {
  return (
    <Button
      {...rest}
      onClick={() => {
        if (window.confirm(confirm)) onConfirm();
      }}
    >
      {label}
    </Button>
  );
}
