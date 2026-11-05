"use client";

import { useMemo, useState } from "react";
import { Ask } from "@/components/Ask";
import { Audit } from "@/components/Audit";
import { DataRoom } from "@/components/DataRoom";
import { Memo } from "@/components/Memo";
import { SourcePanel } from "@/components/SourcePanel";
import type { Citation, Identity, Role } from "@/lib/api";

const TABS = ["Ask", "Data room", "IC memo", "Audit"] as const;
type Tab = (typeof TABS)[number];

export default function Workspace() {
  const [tab, setTab] = useState<Tab>("Ask");
  const [user, setUser] = useState("A. Analyst");
  const [role, setRole] = useState<Role>("analyst");
  const [citation, setCitation] = useState<Citation | null>(null);
  const who: Identity = useMemo(() => ({ user, role }), [user, role]);

  return (
    <>
      <header className="top">
        <div>
          <div className="brand">dealroom-copilot</div>
          <div className="deal">
            Northgate Capital Partners · Project Edelweiss · Alpine Precision Components AG — fictional data room
          </div>
        </div>
        <div className="identity">
          <label>
            Signed in as{" "}
            <input aria-label="User name" value={user} onChange={(event) => setUser(event.target.value)} />
          </label>
          <select
            aria-label="Role"
            data-testid="role"
            value={role}
            onChange={(event) => setRole(event.target.value as Role)}
          >
            <option value="analyst">Analyst</option>
            <option value="associate">Associate</option>
            <option value="partner">Partner</option>
          </select>
        </div>
      </header>
      <nav className="tabs" role="tablist">
        {TABS.map((name) => (
          <button key={name} role="tab" type="button" aria-selected={tab === name} onClick={() => setTab(name)}>
            {name}
          </button>
        ))}
      </nav>
      <main className="grid">
        <div>
          {tab === "Ask" && <Ask who={who} selected={citation} onSelect={setCitation} />}
          {tab === "Data room" && <DataRoom who={who} onSelect={setCitation} />}
          {tab === "IC memo" && <Memo who={who} selected={citation} onSelect={setCitation} />}
          {tab === "Audit" && <Audit who={who} />}
        </div>
        <SourcePanel who={who} citation={citation} />
      </main>
    </>
  );
}
