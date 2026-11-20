import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { CheckCircle2, XCircle } from "lucide-react";

interface Toast { id: number; kind: "success" | "error"; text: string }
const ToastContext = createContext<{ notify: (kind: Toast["kind"], text: string) => void } | null>(null);
let counter = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const notify = useCallback((kind: Toast["kind"], text: string) => {
    const id = ++counter;
    setToasts((current) => [...current.slice(-3), { id, kind, text }]);
    setTimeout(() => setToasts((current) => current.filter((t) => t.id !== id)), kind === "error" ? 7000 : 3500);
  }, []);
  const value = useMemo(() => ({ notify }), [notify]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[min(92vw,22rem)] flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} role="status"
            className={`pointer-events-auto flex animate-fade-up items-start gap-2 rounded-xl border bg-white p-3 text-sm shadow-lg ${t.kind === "error" ? "border-red-200" : "border-accent-100"}`}>
            {t.kind === "error" ? <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-500" /> : <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-accent-600" />}
            <span className="text-slate-700">{t.text}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used inside ToastProvider");
  return context;
}
