import { escapeRegExp } from "../lib/format";

/** Wraps matches of the search terms in <mark>. Safe: text is rendered by React, never as HTML. */
export default function Highlight({ text, terms }: { text: string; terms: string[] }) {
  const clean = terms.filter(Boolean);
  if (clean.length === 0) return <>{text}</>;
  const pattern = new RegExp(`(${clean.map(escapeRegExp).join("|")})`, "gi");
  const lowered = clean.map((t) => t.toLowerCase());
  return (
    <>
      {text.split(pattern).map((part, i) =>
        lowered.includes(part.toLowerCase()) ? <mark key={i} className="rounded bg-accent-100 px-0.5 text-brand-900">{part}</mark> : <span key={i}>{part}</span>,
      )}
    </>
  );
}
