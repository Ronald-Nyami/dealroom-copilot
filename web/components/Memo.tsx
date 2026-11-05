"use client";

import { useState } from "react";
import { api, type Citation, type Identity, type MemoState } from "@/lib/api";
import { CitationChips } from "./CitationChips";

const STATE_LABEL: Record<string, string> = {
  draft: "Draft",
  in_review: "In review",
  approved: "Approved",
  changes_requested: "Changes requested",
};

export function Memo({
  who,
  selected,
  onSelect,
}: {
  who: Identity;
  selected: Citation | null;
  onSelect: (citation: Citation) => void;
}) {
  const [memo, setMemo] = useState<MemoState | null>(null);
  const [responses, setResponses] = useState<Record<string, string>>({});
  const [comment, setComment] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [approvalId, setApprovalId] = useState("");
  const [exported, setExported] = useState("");

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }

  const draft = () =>
    run(async () => {
      setMemo(await api.draftMemo(who));
      setResponses({});
      setExported("");
      setApprovalId("");
    });

  const decide = (action: "approve" | "request_changes") =>
    run(async () => {
      if (!memo) return;
      setMemo(await api.review(who, memo.memo_id, { action, comment, responses }));
    });

  const requestExport = () =>
    run(async () => {
      const outcome = await api.requestExport(who);
      setApprovalId(outcome.approval_id ?? "");
    });

  const approveExport = () =>
    run(async () => {
      await api.approve(who, approvalId);
      const outcome = await api.requestExport(who, approvalId);
      setExported(outcome.path ?? "");
      setApprovalId("");
    });

  const state = memo?.review.state ?? "";
  const high = memo?.arguments.filter((a) => a.severity === "high") ?? [];

  return (
    <section className="panel">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2>Investment committee memo</h2>
        <button className="btn" type="button" onClick={draft} disabled={busy} data-testid="draft-memo">
          {memo ? "Redraft" : "Draft memo"}
        </button>
      </div>
      {error && (
        <p className="error" data-testid="memo-error">
          {error}
        </p>
      )}
      {!memo && (
        <p className="notice">
          Associates and partners can draft. The memo is checked by the IC challenger and cannot be approved until a
          partner has answered every high-severity argument.
        </p>
      )}
      {memo && (
        <>
          <p>
            <span className={`badge state-${state}`} data-testid="memo-state">
              {STATE_LABEL[state] ?? state}
            </span>{" "}
            <span className="notice">
              {memo.uncited === 0 ? "Every sentence is cited." : `${memo.uncited} uncited sentence(s).`}
            </span>
          </p>
          {memo.memo.sections.map((section) => (
            <div key={section.title}>
              <h3>{section.title}</h3>
              <ul className="memo">
                {section.sentences.map((sentence) => (
                  <li key={sentence.text}>
                    {sentence.text}{" "}
                    <CitationChips citations={sentence.citations} selected={selected} onSelect={onSelect} />
                  </li>
                ))}
                {section.unanswered.map((question) => (
                  <li key={question} className="notice">
                    Open: {question}
                  </li>
                ))}
              </ul>
            </div>
          ))}

          <h3>IC challenger · {memo.arguments.length} arguments against the deal</h3>
          <div data-testid="challenger">
            {memo.arguments.map((argument) => (
              <div className="argument" key={argument.title}>
                <div className="row">
                  <span className={`badge sev-${argument.severity}`}>{argument.severity}</span>
                  <strong>{argument.title}</strong>
                </div>
                <p>{argument.text}</p>
                <CitationChips citations={argument.citations} selected={selected} onSelect={onSelect} />
                {argument.severity === "high" && state === "in_review" && (
                  <textarea
                    aria-label={`Response to ${argument.title}`}
                    data-testid="response"
                    placeholder="Partner response (required before approval)"
                    value={responses[argument.title] ?? ""}
                    onChange={(event) => setResponses({ ...responses, [argument.title]: event.target.value })}
                  />
                )}
                {memo.review.responses[argument.title] && (
                  <p className="notice">Response: {memo.review.responses[argument.title]}</p>
                )}
              </div>
            ))}
          </div>

          {state === "in_review" && (
            <>
              <h3>Review</h3>
              <textarea
                className="comment"
                aria-label="Review comment"
                placeholder="Comment (required when requesting changes)"
                value={comment}
                onChange={(event) => setComment(event.target.value)}
              />
              <div className="row">
                <button className="btn" type="button" onClick={() => decide("approve")} disabled={busy} data-testid="approve">
                  Approve
                </button>
                <button
                  className="btn secondary"
                  type="button"
                  onClick={() => decide("request_changes")}
                  disabled={busy}
                >
                  Request changes
                </button>
                <span className="notice">
                  {high.length} high-severity argument(s) need a response. Only a partner can approve.
                </span>
              </div>
            </>
          )}

          {state === "approved" && (
            <>
              <h3>Export</h3>
              {!approvalId && !exported && (
                <button className="btn" type="button" onClick={requestExport} disabled={busy} data-testid="export">
                  Request export
                </button>
              )}
              {approvalId && (
                <div className="row">
                  <span className="mono">Approval {approvalId.slice(0, 8)} pending</span>
                  <button className="btn" type="button" onClick={approveExport} disabled={busy} data-testid="approve-export">
                    Approve and export
                  </button>
                </div>
              )}
              {exported && (
                <p data-testid="exported">
                  Exported to <span className="mono">{exported}</span>
                </p>
              )}
            </>
          )}

          <h3>History</h3>
          <ul className="memo">
            {memo.review.history.map((event) => (
              <li key={event.at + event.action}>
                <span className="mono">{event.at.slice(0, 19).replace("T", " ")}</span> {event.actor} ({event.role}):{" "}
                {event.action}
                {event.comment ? ` — ${event.comment}` : ""}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
