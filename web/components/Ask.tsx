"use client";

import { type FormEvent, useState } from "react";
import { type Citation, type Identity, streamAnswer } from "@/lib/api";
import { CitationChips } from "./CitationChips";

const SUGGESTIONS = [
  "What was audited net revenue in FY2025?",
  "What net debt does the model project for FY2027?",
  "Can Ostara Pumps terminate its supply agreement for convenience?",
  "What annual volume does Brenntal commit to in Schedule 3?",
  "What is the CEO's annual salary?",
];

export function Ask({
  who,
  selected,
  onSelect,
}: {
  who: Identity;
  selected: Citation | null;
  onSelect: (citation: Citation) => void;
}) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [citations, setCitations] = useState<Citation[]>([]);
  const [abstained, setAbstained] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function ask(text: string) {
    setBusy(true);
    setAnswer("");
    setCitations([]);
    setError("");
    try {
      const outcome = await streamAnswer(who, text, setCitations, (token) => setAnswer((prior) => prior + token));
      setAbstained(outcome.abstained);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (question.trim().length >= 3) void ask(question.trim());
  }

  return (
    <section className="panel">
      <h2>Ask the data room</h2>
      <form className="row" onSubmit={submit}>
        <input
          className="question"
          aria-label="Question"
          data-testid="question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="e.g. When does the Thun lease end?"
        />
        <button className="btn" type="submit" disabled={busy} data-testid="ask">
          {busy ? "Searching…" : "Ask"}
        </button>
      </form>
      <div className="suggestions">
        {SUGGESTIONS.map((text) => (
          <div key={text}>
            <button
              type="button"
              onClick={() => {
                setQuestion(text);
                void ask(text);
              }}
            >
              {text}
            </button>
          </div>
        ))}
      </div>
      {error && <p className="error">{error}</p>}
      {(answer || busy) && (
        <div className={abstained ? "answer abstained" : "answer"} data-testid="answer">
          {answer || "…"}
        </div>
      )}
      {citations.length > 0 && (
        <div>
          <span className="notice">Sources: </span>
          <CitationChips citations={citations} selected={selected} onSelect={onSelect} />
        </div>
      )}
      <p className="notice">
        Answers come only from the data room. Every claim carries a source; if the evidence is not there, the answer
        says so.
      </p>
    </section>
  );
}
