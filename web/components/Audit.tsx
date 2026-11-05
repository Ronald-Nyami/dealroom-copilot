"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type AuditRecord, type Identity } from "@/lib/api";

export function Audit({ who }: { who: Identity }) {
  const [records, setRecords] = useState<AuditRecord[]>([]);
  const [verified, setVerified] = useState<boolean | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api
      .audit(who)
      .then((data) => {
        setRecords([...data.records].reverse());
        setVerified(data.verified);
      })
      .catch((reason: unknown) => setError(String(reason)));
  }, [who]);

  useEffect(load, [load]);

  return (
    <section className="panel">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2>Audit log</h2>
        <button className="btn secondary" type="button" onClick={load}>
          Refresh
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {verified !== null && (
        <p>
          <span className={`badge ${verified ? "state-approved" : "sev-high"}`} data-testid="audit-verified">
            {verified ? "Hash chain verified" : "Hash chain broken"}
          </span>{" "}
          <span className="notice">Every tool call and review decision, by humans and agents, newest first.</span>
        </p>
      )}
      <table>
        <thead>
          <tr>
            <th>Time (UTC)</th>
            <th>Who</th>
            <th>Tool</th>
            <th>Decision</th>
            <th>Hash</th>
          </tr>
        </thead>
        <tbody>
          {records.map((record) => (
            <tr key={record.hash}>
              <td className="mono">{record.at.slice(0, 19).replace("T", " ")}</td>
              <td>
                {record.actor} <span className="notice">({record.role})</span>
              </td>
              <td className="mono">{record.tool}</td>
              <td>
                {record.decision}
                {record.detail ? <div className="notice">{record.detail}</div> : null}
              </td>
              <td className="mono">{record.hash.slice(0, 10)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
