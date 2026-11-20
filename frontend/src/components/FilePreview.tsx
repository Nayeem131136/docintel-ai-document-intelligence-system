import { useEffect, useState } from "react";
import { Download } from "lucide-react";
import { api } from "../lib/api";
import { Alert, Button, Spinner } from "./ui";

/** Loads the original file with the auth header and shows it from a temporary local URL. */
export default function FilePreview({ id, type, name }: { id: string; type: string; name: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState("");
  const previewable = ["pdf", "png", "jpg", "jpeg"].includes(type);

  useEffect(() => {
    let revoked = false;
    let objectUrl: string | null = null;
    api.fileBlob(id)
      .then((blob) => {
        if (revoked) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch((e: Error) => !revoked && setError(e.message));
    return () => {
      revoked = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [id]);

  if (error) return <Alert kind="error">{error}</Alert>;
  if (!url) return <Spinner label="Loading the original file..." />;
  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <a href={url} download={name}><Button icon={<Download className="h-4 w-4" />}>Download original</Button></a>
      </div>
      {previewable ? (
        type === "pdf" ? (
          <iframe title={`Preview of ${name}`} src={url} className="h-[75vh] w-full rounded-xl border border-slate-200 bg-white" />
        ) : (
          <img alt={name} src={url} className="mx-auto max-h-[75vh] rounded-xl border border-slate-200 bg-white" />
        )
      ) : (
        <Alert kind="info">A preview is not available for this file type. Use the download button to open it.</Alert>
      )}
    </div>
  );
}
