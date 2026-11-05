export type Role = "analyst" | "associate" | "partner";

export interface Identity {
  user: string;
  role: Role;
}

export interface Citation {
  n: number;
  chunk_id: string;
  citation: string;
  text: string;
}

export interface DocumentSummary {
  file: string;
  title: string;
  kind: "pdf" | "scan" | "xlsx";
  chunks: number;
}

export interface ChunkView {
  id: string;
  file: string;
  text: string;
  citation: string;
  kind: string;
}

export interface Argument {
  check: string;
  title: string;
  severity: "high" | "medium" | "low";
  text: string;
  citations: Citation[];
}

export interface MemoSentence {
  text: string;
  citations: Citation[];
}

export interface MemoSection {
  title: string;
  sentences: MemoSentence[];
  unanswered: string[];
}

export interface ReviewEvent {
  action: string;
  actor: string;
  role: string;
  state: string;
  comment: string;
  at: string;
}

export interface MemoState {
  memo_id: string;
  memo: { title: string; sections: MemoSection[] };
  arguments: Argument[];
  review: { state: string; history: ReviewEvent[]; responses: Record<string, string> };
  uncited: number;
  error?: string;
}

export interface AuditRecord {
  at: string;
  actor: string;
  role: string;
  tool: string;
  decision: string;
  detail: string;
  hash: string;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

function headers(who: Identity, json = false): HeadersInit {
  return { "X-User": who.user, "X-Role": who.role, ...(json ? { "Content-Type": "application/json" } : {}) };
}

async function call<T>(path: string, who: Identity, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { ...init, headers: headers(who, init.body !== undefined) });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
    throw new ApiError(response.status, typeof body.detail === "string" ? body.detail : response.statusText);
  }
  return (await response.json()) as T;
}

export const api = {
  documents: (who: Identity) => call<DocumentSummary[]>("/api/documents", who),
  chunks: (who: Identity, file: string) => call<ChunkView[]>(`/api/documents/${encodeURIComponent(file)}/chunks`, who),
  chunk: (who: Identity, id: string) =>
    call<{ chunk_id: string; citation: string; text: string }>(`/api/chunks/${id}`, who),
  draftMemo: (who: Identity) => call<MemoState>("/api/memos", who, { method: "POST" }),
  review: (
    who: Identity,
    memoId: string,
    body: { action: string; comment?: string; responses?: Record<string, string> },
  ) => call<MemoState>(`/api/memos/${memoId}/review`, who, { method: "POST", body: JSON.stringify(body) }),
  requestExport: (who: Identity, approvalId?: string) =>
    call<{ status?: string; approval_id?: string; path?: string }>("/api/export", who, {
      method: "POST",
      body: JSON.stringify(approvalId ? { approval_id: approvalId } : {}),
    }),
  approve: (who: Identity, approvalId: string) =>
    call<{ status: string }>(`/api/approvals/${approvalId}`, who, { method: "POST" }),
  audit: (who: Identity) => call<{ verified: boolean; records: AuditRecord[] }>("/api/audit", who),
};

/** Streams an answer: the citations arrive first, then the text word by word. */
export async function streamAnswer(
  who: Identity,
  question: string,
  onCitations: (citations: Citation[]) => void,
  onToken: (token: string) => void,
): Promise<{ abstained: boolean }> {
  const response = await fetch(`/api/ask/stream?q=${encodeURIComponent(question)}`, { headers: headers(who) });
  if (!response.ok || !response.body) {
    throw new ApiError(response.status, "the question could not be answered");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let outcome = { abstained: false };
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const block of events) {
      const event = /^event: (\w+)/m.exec(block)?.[1];
      const data = /^data: (.*)$/m.exec(block)?.[1];
      if (!event || data === undefined) continue;
      const payload: unknown = JSON.parse(data);
      if (event === "citations") onCitations(payload as Citation[]);
      if (event === "token") onToken(payload as string);
      if (event === "done") outcome = payload as { abstained: boolean };
    }
  }
  return outcome;
}
