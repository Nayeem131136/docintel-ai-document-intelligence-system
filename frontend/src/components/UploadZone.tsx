import { useCallback, useRef, useState } from "react";
import { CheckCircle2, FileUp, Loader2, UploadCloud, XCircle } from "lucide-react";
import { uploadFile } from "../lib/api";
import { ACCEPTED_EXTENSIONS, MAX_UPLOAD_MB, checkFile, formatBytes } from "../lib/format";
import { BorderBeam, ProgressBar, cx } from "./ui";

interface Item {
  id: number;
  file: File;
  state: "waiting" | "uploading" | "done" | "error";
  progress: number;
  error?: string;
}

let nextId = 1;
const CONCURRENCY = 2;

export default function UploadZone({ onUploaded }: { onUploaded?: () => void }) {
  const [items, setItems] = useState<Item[]>([]);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const running = useRef(0);
  const queue = useRef<Item[]>([]);

  const patch = useCallback((id: number, change: Partial<Item>) => {
    setItems((current) => current.map((item) => (item.id === id ? { ...item, ...change } : item)));
  }, []);

  const pump = useCallback(() => {
    while (running.current < CONCURRENCY && queue.current.length) {
      const item = queue.current.shift()!;
      running.current++;
      patch(item.id, { state: "uploading", progress: 0 });
      uploadFile(item.file, (fraction) => patch(item.id, { progress: fraction }))
        .then(() => patch(item.id, { state: "done", progress: 1 }))
        .catch((error: Error) => patch(item.id, { state: "error", error: error.message }))
        .finally(() => {
          running.current--;
          onUploaded?.();
          pump();
        });
    }
  }, [onUploaded, patch]);

  const add = useCallback(
    (files: FileList | File[]) => {
      const fresh: Item[] = [];
      for (const file of Array.from(files)) {
        const problem = checkFile(file);
        const item: Item = { id: nextId++, file, state: problem ? "error" : "waiting", progress: 0, error: problem ?? undefined };
        fresh.push(item);
        if (!problem) queue.current.push(item);
      }
      setItems((current) => [...fresh, ...current].slice(0, 30));
      pump();
    },
    [pump],
  );

  const busy = items.some((i) => i.state === "uploading" || i.state === "waiting");

  return (
    <div className="space-y-3">
      <BorderBeam className="rounded-2xl">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            if (e.dataTransfer.files.length) add(e.dataTransfer.files);
          }}
          className={cx(
            "dot-pattern-light flex cursor-pointer flex-col items-center rounded-2xl border-2 border-dashed px-6 py-9 text-center transition",
            dragging ? "border-accent-500 bg-accent-50" : "border-slate-300 bg-white hover:border-accent-400",
          )}
          onClick={() => input.current?.click()}
          role="button"
          tabIndex={0}
          aria-label="Upload documents"
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
        >
          <div className={cx("mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-900 text-accent-400", busy && "animate-pulse-ring")}>
            {busy ? <Loader2 className="h-6 w-6 animate-spin" /> : <UploadCloud className="h-6 w-6" />}
          </div>
          <p className="font-semibold text-brand-900">Drop invoices here or click to browse</p>
          <p className="mt-1 text-sm text-slate-500">
            PDF, JPG, PNG, TIFF, XLSX, XLS, CSV - up to {MAX_UPLOAD_MB} MB each. Select several files at once.
          </p>
          <input
            ref={input}
            type="file"
            multiple
            hidden
            accept={ACCEPTED_EXTENSIONS.join(",")}
            data-testid="file-input"
            onChange={(e) => {
              if (e.target.files?.length) add(e.target.files);
              e.target.value = "";
            }}
          />
        </div>
      </BorderBeam>

      {items.length > 0 && (
        <ul className="card divide-y divide-slate-100" aria-label="Upload queue">
          {items.map((item) => (
            <li key={item.id} className="flex items-center gap-3 px-4 py-3">
              <FileUp className="h-5 w-5 shrink-0 text-slate-400" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-3">
                  <p className="truncate text-sm font-medium text-slate-800">{item.file.name}</p>
                  <span className="shrink-0 text-xs text-slate-500">{formatBytes(item.file.size)}</span>
                </div>
                {item.state === "uploading" && <div className="mt-1.5"><ProgressBar value={item.progress * 100} /></div>}
                {item.state === "waiting" && <p className="text-xs text-slate-500">Waiting...</p>}
                {item.state === "done" && <p className="text-xs text-emerald-600">Uploaded - processing in the background</p>}
                {item.state === "error" && <p className="text-xs text-red-600">{item.error}</p>}
              </div>
              {item.state === "done" && <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-500" />}
              {item.state === "error" && <XCircle className="h-5 w-5 shrink-0 text-red-500" />}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
