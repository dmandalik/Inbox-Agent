"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  CAT_LABEL,
  CAT_META,
  dotFor,
  initials,
  tintFor,
  type AskHit,
  type Categories,
  type EmailDetail,
  type EmailSummary,
} from "@/lib/api";

const RAIL_ORDER = [
  "all",
  "work",
  "personal",
  "newsletter",
  "receipt_order",
  "notification",
  "spam_phishing",
];

function Shield() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2l8 3v6c0 5-3.5 8-8 11-4.5-3-8-6-8-11V5z" />
    </svg>
  );
}
function Check() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 6L9 17l-5-5" />
    </svg>
  );
}

export default function Console() {
  const [cats, setCats] = useState<Categories | null>(null);
  const [selectedCat, setSelectedCat] = useState("all");
  const [emails, setEmails] = useState<EmailSummary[]>([]);
  const [ask, setAsk] = useState<{ q: string; hits: AskHit[] } | null>(null);
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<EmailDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.categories().then(setCats).catch((e) => setError(String(e)));
  }, []);

  // Load the list for the selected category (unless we are showing ask results).
  useEffect(() => {
    if (ask) return;
    let alive = true;
    api
      .emails(selectedCat)
      .then((r) => {
        if (!alive) return;
        setEmails(r.emails);
        setSelectedId((cur) => {
          if (cur && r.emails.some((e) => e.id === cur)) return cur;
          const flagged = r.emails.find((e) => e.flagged.length);
          return (flagged || r.emails[0])?.id ?? null;
        });
      })
      .catch((e) => setError(String(e)));
    return () => {
      alive = false;
    };
  }, [selectedCat, ask]);

  // Load the open email's detail.
  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let alive = true;
    api
      .email(selectedId)
      .then((d) => alive && setDetail(d))
      .catch((e) => setError(String(e)));
    return () => {
      alive = false;
    };
  }, [selectedId]);

  const pickCategory = useCallback((cat: string) => {
    setAsk(null);
    setQuery("");
    setSelectedCat(cat);
  }, []);

  const runAsk = useCallback(async () => {
    const q = query.trim();
    if (!q) return;
    try {
      const r = await api.ask(q, 6);
      setAsk({ q, hits: r.hits });
      if (r.hits[0]) setSelectedId(r.hits[0].id);
    } catch (e) {
      setError(String(e));
    }
  }, [query]);

  const catCount = useMemo(() => {
    const m: Record<string, number> = {};
    cats?.categories.forEach((c) => (m[c.id] = c.count));
    return m;
  }, [cats]);

  const rows: EmailSummary[] = ask
    ? ask.hits.map((h) => ({
        id: h.id,
        from_name: h.from_name,
        date: h.date,
        subject: h.subject,
        snippet: h.snippet,
        category: "",
        flagged: [],
      }))
    : emails;

  const listTitle = ask
    ? `Results for “${ask.q}”`
    : selectedCat === "all"
      ? "All mail"
      : CAT_LABEL[selectedCat] ?? selectedCat;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="mark" aria-hidden>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 7l9 6 9-6" />
              <rect x="3" y="5" width="18" height="14" rx="2" />
            </svg>
          </div>
          <div>
            <div className="brand-name">Inbox Agent</div>
            <div className="brand-sub">triage · ask · guard</div>
          </div>
        </div>
        <div className="top-right">
          <span className="env">
            <span className="live" />
            {cats ? `${cats.total} emails · ${cats.flagged} flagged` : "connecting…"}
          </span>
          <ThemeToggle />
        </div>
      </header>

      <form
        className="ask"
        onSubmit={(e) => {
          e.preventDefault();
          runAsk();
        }}
      >
        <span className="search" aria-hidden>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="7" />
            <path d="M21 21l-4-4" />
          </svg>
        </span>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ask your inbox…  e.g. when is the Q3 planning doc due?"
          aria-label="Ask your inbox"
        />
        {ask ? (
          <button type="button" className="clear" onClick={() => pickCategory(selectedCat)}>
            clear
          </button>
        ) : (
          <span className="kbd">/</span>
        )}
      </form>

      {error && <div className="pane" style={{ padding: "14px 16px", color: "var(--danger)" }}>{error}. Is the API running? Try <code>inbox-agent serve</code>.</div>}

      <div className="console">
        <aside className="pane rail">
          <nav className="rail-scroll" aria-label="Categories">
            {RAIL_ORDER.map((id) => (
              <button
                key={id}
                className="cat"
                aria-selected={!ask && selectedCat === id}
                onClick={() => pickCategory(id)}
              >
                <span className="dot" style={{ background: CAT_META[id].dot }} />
                <span className="cat-name">{CAT_META[id].label}</span>
                <span className="cat-count mono">{id === "all" ? cats?.total ?? "" : catCount[id] ?? ""}</span>
              </button>
            ))}
            <div className="rail-sep" />
            <button className="cat flagged" aria-selected={selectedCat === "flagged" && !ask} onClick={() => pickCategory("flagged")}>
              <span className="shield-sm"><Shield /></span>
              <span className="cat-name">Flagged</span>
              <span className="cat-count mono">{cats?.flagged ?? ""}</span>
            </button>
          </nav>
        </aside>

        <section className="pane">
          <div className="pane-head">
            <span className="pane-title">{listTitle}</span>
            <span className="pane-meta">{rows.length} {rows.length === 1 ? "email" : "emails"}</span>
          </div>
          <div className="list-scroll">
            {rows.length === 0 && <div className="empty">Nothing here yet.</div>}
            {rows.map((m, i) => (
              <button key={m.id} className="msg" aria-selected={m.id === selectedId} onClick={() => setSelectedId(m.id)}>
                <span className="avatar" style={{ background: tintFor(m.category || "all"), color: dotFor(m.category || "all") }}>
                  {initials(m.from_name)}
                </span>
                <span className="msg-main">
                  <span className="msg-from">
                    {m.from_name}
                    {m.flagged.length > 0 && (
                      <span className="flag-chip"><Shield />manipulation</span>
                    )}
                  </span>
                  <span className="msg-subj">{m.subject}</span>
                  <span className="msg-snip">{m.snippet}</span>
                </span>
                <span className="msg-time mono">
                  {ask ? <span className="score">{ask.hits[i]?.score}</span> : m.date.slice(5, 10)}
                </span>
              </button>
            ))}
          </div>
        </section>

        <section className="pane">
          <div className="pane-head">
            <span className="pane-title">Reading</span>
            <span className="pane-meta">{detail?.id ?? ""}</span>
          </div>
          <div className="reader-scroll">
            {detail ? <Reader email={detail} /> : <div className="placeholder">Select an email to read it.</div>}
          </div>
        </section>
      </div>
    </div>
  );
}

function Reader({ email }: { email: EmailDetail }) {
  const flagged = email.flagged.length > 0;
  return (
    <>
      <div className="reader-head">
        <div className="reader-from-row">
          <span className="avatar" style={{ background: tintFor(email.category), color: dotFor(email.category) }}>
            {initials(email.from_name)}
          </span>
          <span>
            <div className="rfr-name">{email.from_name}</div>
            <div className="rfr-addr">{email.from_addr}</div>
          </span>
          <span className="rfr-date">{email.date.replace("T", " ").slice(0, 16)}</span>
        </div>
        <div className="reader-subj">{email.subject}</div>
      </div>

      <div className="verdict-row">
        <span className="chip">
          <span className="dot" style={{ background: dotFor(email.category) }} />
          Triage <b>{CAT_LABEL[email.category] ?? email.category}</b> <span className="tag">stub</span>
        </span>
        {email.thread_id && (
          <span className="chip">Thread <b className="mono">{email.thread_id}</b></span>
        )}
      </div>

      {flagged ? (
        <div className="sec warn">
          <div className="sec-head"><Shield /> Manipulation attempt detected</div>
          <div className="sec-body">
            This email contains text aimed at hijacking an AI assistant. It was treated as untrusted data and no instruction in it was followed.
          </div>
          <div className="signals">
            {email.flagged.map((s) => (
              <span className="sig" key={s}>{s}</span>
            ))}
          </div>
          <div className="sec-foot">
            Architectural guardrail: triage output is clamped, so this could only ever become a category label, never an action.
          </div>
        </div>
      ) : (
        <div className="sec safe">
          <div className="sec-head"><Check /> No manipulation detected</div>
          <div className="sec-body">Nothing in this email looks like an attempt to instruct the assistant. Read normally.</div>
        </div>
      )}

      <div className="body-text">{email.body}</div>

      <div className="reader-foot">
        <button className="draft-btn" disabled>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 20h4L18 10l-4-4L4 16z" />
            <path d="M14 6l4 4" />
          </svg>
          Draft a reply
        </button>
        <span className="soon">drafting ships next<br />you approve before anything sends</span>
      </div>
    </>
  );
}

function ThemeToggle() {
  return (
    <button
      className="icon-btn"
      title="Toggle theme"
      aria-label="Toggle light or dark theme"
      onClick={() => {
        const root = document.documentElement;
        const dark =
          root.getAttribute("data-theme") === "dark" ||
          (!root.getAttribute("data-theme") && matchMedia("(prefers-color-scheme: dark)").matches);
        root.setAttribute("data-theme", dark ? "light" : "dark");
      }}
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M19 5l-1.5 1.5M6.5 17.5L5 19" />
      </svg>
    </button>
  );
}
