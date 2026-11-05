"use client";

import { useEffect, useState } from "react";
import { api, type ChunkView, type Citation, type DocumentSummary, type Identity } from "@/lib/api";

const KIND = { pdf: "PDF", scan: "Scan (OCR)", xlsx: "Spreadsheet" } as const;

export function DataRoom({ who, onSelect }: { who: Identity; onSelect: (citation: Citation) => void }) {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [chunks, setChunks] = useState<ChunkView[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .documents(who)
      .then(setDocuments)
      .catch((reason: unknown) => setError(String(reason)));
  }, [who]);

  useEffect(() => {
    if (!open) return;
    api
      .chunks(who, open)
      .then(setChunks)
      .catch((reason: unknown) => setError(String(reason)));
  }, [who, open]);

  return (
    <section className="panel">
      <h2>Data room · {documents.length} files</h2>
      {error && <p className="error">{error}</p>}
      <table data-testid="documents">
        <thead>
          <tr>
            <th>File</th>
            <th>Type</th>
            <th>Chunks</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => (
            <tr
              key={doc.file}
              className="clickable"
              aria-selected={open === doc.file}
              onClick={() => setOpen(doc.file)}
            >
              <td>
                <div>{doc.title}</div>
                <div className="mono">{doc.file}</div>
              </td>
              <td>{KIND[doc.kind]}</td>
              <td>{doc.chunks}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {open && (
        <>
          <h3>{open}</h3>
          {chunks.map((chunk) => (
            <button
              key={chunk.id}
              type="button"
              className="cite"
              onClick={() =>
                onSelect({ n: 0, chunk_id: chunk.id, citation: chunk.citation, text: chunk.text.split("\n")[1] ?? "" })
              }
            >
              {chunk.citation} · {chunk.kind}
            </button>
          ))}
        </>
      )}
    </section>
  );
}
