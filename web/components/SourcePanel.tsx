"use client";

import { useEffect, useState } from "react";
import { api, type Citation, type Identity } from "@/lib/api";

/** Where in the chunk text the cited span sits. Table rows are rendered differently, so fall back to the row label. */
export function locate(chunk: string, quote: string): [number, number] | null {
  const exact = chunk.indexOf(quote);
  if (exact >= 0) return [exact, exact + quote.length];
  // A row is cited as "Label, FY2027E: 104.8" or, with its table caption, "Caption: Label (...)".
  const candidates = [quote, quote.includes(": ") ? quote.slice(quote.indexOf(": ") + 2) : ""];
  const lines = chunk.split("\n");
  for (const candidate of candidates) {
    const label = candidate.split(/[,(:]/)[0]?.trim() ?? "";
    if (label.length < 3) continue;
    let offset = 0;
    for (const line of lines) {
      if (line.startsWith(`${label} |`) || line === label) return [offset, offset + line.length];
      offset += line.length + 1;
    }
  }
  return null;
}

export function SourcePanel({ who, citation }: { who: Identity; citation: Citation | null }) {
  const [text, setText] = useState<string>("");
  const [error, setError] = useState<string>("");

  useEffect(() => {
    if (!citation) return;
    let live = true;
    api
      .chunk(who, citation.chunk_id)
      .then((chunk) => {
        if (live) {
          setText(chunk.text);
          setError("");
        }
      })
      .catch((reason: unknown) => live && setError(String(reason)));
    return () => {
      live = false;
    };
  }, [who, citation]);

  if (!citation) {
    return (
      <aside className="source" data-testid="source-panel">
        <h2>Source</h2>
        <p className="notice">Select a citation to see the exact passage it comes from.</p>
      </aside>
    );
  }
  const span = text ? locate(text, citation.text) : null;
  return (
    <aside className="source" data-testid="source-panel">
      <h2>Source</h2>
      <p className="mono">{citation.citation}</p>
      {error && <p className="error">{error}</p>}
      <pre className="chunk">
        {span ? (
          <>
            {text.slice(0, span[0])}
            <mark data-testid="highlight">{text.slice(span[0], span[1])}</mark>
            {text.slice(span[1])}
          </>
        ) : (
          text
        )}
      </pre>
    </aside>
  );
}
