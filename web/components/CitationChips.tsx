"use client";

import type { Citation } from "@/lib/api";

export function CitationChips({
  citations,
  selected,
  onSelect,
}: {
  citations: Citation[];
  selected: Citation | null;
  onSelect: (citation: Citation) => void;
}) {
  return (
    <span>
      {citations.map((citation) => (
        <button
          key={`${citation.n}-${citation.chunk_id}`}
          type="button"
          className="cite"
          aria-pressed={selected?.chunk_id === citation.chunk_id && selected.text === citation.text}
          data-testid="citation"
          onClick={() => onSelect(citation)}
          title={citation.text}
        >
          [{citation.n}] {citation.citation}
        </button>
      ))}
    </span>
  );
}
