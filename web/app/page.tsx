"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  CAT_LABEL,
  CAT_META,
  dotFor,
  initials,
  tintFor,
  type Categories,
  type ChatCitation,
  type ChatListItem,
  type EmailDetail,
  type EmailSummary,
  type Label,
  type ReplyProposal,
} from "@/lib/api";

type ChatMsg = {
  role: "user" | "assistant";
  text: string;
  citations?: ChatCitation[];
  proposal?: ReplyProposal;
  sent?: boolean;
  error?: boolean;
};

const RAIL_ORDER = [
  "all",
  "work",
  "personal",
  "newsletter",
  "receipt_order",
  "notification",
  "spam_phishing",
];

const svgProps = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

const Shield = () => (
  <svg {...svgProps}>
    <path d="M12 2l8 3v6c0 5-3.5 8-8 11-4.5-3-8-6-8-11V5z" />
  </svg>
);
const Check = () => (
  <svg {...svgProps}>
    <path d="M20 6L9 17l-5-5" />
  </svg>
);
const Star = ({ fill }: { fill: boolean }) => (
  <svg {...svgProps} fill={fill ? "currentColor" : "none"}>
    <path d="M12 3l2.9 5.9 6.5.9-4.7 4.6 1.1 6.5L12 18.8 6.2 21.9l1.1-6.5L2.6 9.8l6.5-.9z" />
  </svg>
);
const Archive = () => (
  <svg {...svgProps}>
    <rect x="3" y="4" width="18" height="4" rx="1" />
    <path d="M5 8v11a1 1 0 001 1h12a1 1 0 001-1V8M10 12h4" />
  </svg>
);
const Sparkle = () => (
  <svg {...svgProps}>
    <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" />
  </svg>
);
const Arrow = () => (
  <svg {...svgProps}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </svg>
);
const Plus = () => (
  <svg {...svgProps}>
    <path d="M12 5v14M5 12h14" />
  </svg>
);
const Expand = () => (
  <svg {...svgProps}>
    <path d="M8 3H5a2 2 0 00-2 2v3M16 3h3a2 2 0 012 2v3M8 21H5a2 2 0 01-2-2v-3M16 21h3a2 2 0 002-2v-3" />
  </svg>
);
const Close = () => (
  <svg {...svgProps}>
    <path d="M6 6l12 12M18 6L6 18" />
  </svg>
);
const Compose = () => (
  <svg {...svgProps}>
    <path d="M4 20h4L18 10l-4-4L4 16z" />
    <path d="M14 6l4 4" />
  </svg>
);
const Refresh = ({ spinning }: { spinning?: boolean }) => (
  <svg {...svgProps} className={spinning ? "spin" : undefined}>
    <polyline points="23 4 23 10 17 10" />
    <polyline points="1 20 1 14 7 14" />
    <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
  </svg>
);

type Filter = "none" | "starred" | "unread";

export default function Console() {
  const [cats, setCats] = useState<Categories | null>(null);
  const [selectedCat, setSelectedCat] = useState("all");
  const [emails, setEmails] = useState<EmailSummary[]>([]);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("date");
  const [filter, setFilter] = useState<Filter>("none");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<EmailDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Custom color-coded labels.
  const [labels, setLabels] = useState<Label[]>([]);
  const [labelFilter, setLabelFilter] = useState<string | null>(null);
  const [organizing, setOrganizing] = useState(false);

  const loadLabels = useCallback(() => {
    api
      .labels()
      .then((r) => setLabels(r.labels))
      .catch(() => {});
  }, []);

  // Conversational agent over the inbox.
  const [chatOpen, setChatOpen] = useState(false);
  const [chatExpanded, setChatExpanded] = useState(false);
  const [chatId, setChatId] = useState<string | undefined>(undefined);
  const [chatMsgs, setChatMsgs] = useState<ChatMsg[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [chatList, setChatList] = useState<ChatListItem[]>([]);

  const loadChatList = useCallback(() => {
    api
      .chats()
      .then((r) => setChatList(r.chats))
      .catch(() => {});
  }, []);

  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);
  const [composeOpen, setComposeOpen] = useState(false);

  const refreshCats = useCallback(() => {
    api.categories().then(setCats).catch((e) => setError(String(e)));
  }, []);

  useEffect(() => refreshCats(), [refreshCats]);

  const loadEmails = useCallback(async () => {
    try {
      const r = await api.emails({
        category: labelFilter ? "all" : selectedCat,
        label: labelFilter || undefined,
        sort,
        order: sort === "date" ? "desc" : "asc",
        q: search || undefined,
        starred: filter === "starred" || undefined,
        unread: filter === "unread" || undefined,
      });
      setEmails(r.emails);
      setSelectedId((cur) => {
        if (cur && r.emails.some((e) => e.id === cur)) return cur;
        const flagged = r.emails.find((e) => e.flagged.length);
        return (flagged || r.emails[0])?.id ?? null;
      });
    } catch (e) {
      setError(String(e));
    }
  }, [selectedCat, sort, search, filter, labelFilter]);

  useEffect(() => {
    loadEmails();
  }, [loadEmails]);

  useEffect(() => {
    if (chatOpen) loadChatList();
  }, [chatOpen, loadChatList]);

  useEffect(() => loadLabels(), [loadLabels]);

  // Load the open email, and mark it read once.
  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let alive = true;
    api
      .email(selectedId)
      .then((d) => {
        if (!alive) return;
        setDetail(d);
        if (!d.read) {
          api.setState(d.id, { read: true }).then(() => {
            setEmails((es) => es.map((e) => (e.id === d.id ? { ...e, read: true } : e)));
          });
        }
      })
      .catch((e) => setError(String(e)));
    return () => {
      alive = false;
    };
  }, [selectedId]);

  const pickCategory = useCallback((cat: string) => {
    setLabelFilter(null);
    setSelectedCat(cat);
  }, []);

  const selectLabel = useCallback((id: string) => {
    setLabelFilter((cur) => (cur === id ? null : id));
  }, []);

  const createLabel = useCallback(
    async (name: string, color: string, instructions: string) => {
      try {
        await api.createLabel(name, color, instructions);
        loadLabels();
      } catch (e) {
        setError(String(e));
      }
    },
    [loadLabels],
  );

  const deleteLabel = useCallback(
    async (id: string) => {
      try {
        await api.deleteLabel(id);
        setLabelFilter((cur) => (cur === id ? null : cur));
        loadLabels();
        loadEmails();
      } catch (e) {
        setError(String(e));
      }
    },
    [loadLabels, loadEmails],
  );

  const toggleEmailLabel = useCallback(
    async (messageId: string, labelId: string, on: boolean) => {
      try {
        const r = await api.setEmailLabel(messageId, labelId, on);
        setDetail((d) => (d && d.id === messageId ? { ...d, labels: r.labels } : d));
        loadLabels();
        loadEmails();
      } catch (e) {
        setError(String(e));
      }
    },
    [loadLabels, loadEmails],
  );

  const doSync = useCallback(
    async (silent = false) => {
      if (!silent) setSyncing(true);
      try {
        const r = await api.sync();
        if (r.added > 0) {
          loadEmails();
          refreshCats();
          setSyncMsg(`${r.added} new`);
        } else if (!silent) {
          setSyncMsg("Up to date");
        }
      } catch (e) {
        if (!silent) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!silent) setSyncing(false);
      }
    },
    [loadEmails, refreshCats],
  );

  // Auto-pull fresh mail from Gmail every 2 minutes (silent; errors ignored).
  useEffect(() => {
    const id = setInterval(() => doSync(true), 120_000);
    return () => clearInterval(id);
  }, [doSync]);

  useEffect(() => {
    if (!syncMsg) return;
    const id = setTimeout(() => setSyncMsg(null), 4000);
    return () => clearTimeout(id);
  }, [syncMsg]);

  const autoOrganize = useCallback(async () => {
    setOrganizing(true);
    try {
      await api.applyLabels();
      loadLabels();
      loadEmails();
      if (selectedId) api.email(selectedId).then(setDetail).catch(() => {});
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setOrganizing(false);
    }
  }, [loadLabels, loadEmails, selectedId]);

  const sendChat = useCallback(
    async (text: string) => {
      const msg = text.trim();
      if (!msg || chatBusy) return;
      setChatInput("");
      setChatMsgs((m) => [...m, { role: "user", text: msg }]);
      setChatBusy(true);
      try {
        const r = await api.chat(msg, chatId);
        setChatId(r.chat_id);
        setChatMsgs((m) => [
          ...m,
          {
            role: "assistant",
            text: r.reply,
            citations: r.citations,
            proposal: r.proposal ?? undefined,
          },
        ]);
        loadChatList();
        // A chat action may have changed inbox state (labels, read, star…).
        if (r.kind !== "question") {
          loadEmails();
          refreshCats();
          loadLabels();
        }
      } catch (e) {
        const detail = e instanceof Error ? e.message : String(e);
        setChatMsgs((m) => [...m, { role: "assistant", text: detail, error: true }]);
      } finally {
        setChatBusy(false);
      }
    },
    [chatId, chatBusy, loadChatList, loadEmails, refreshCats, loadLabels],
  );

  const sendChatReply = useCallback(async (idx: number, proposal: ReplyProposal) => {
    if (!window.confirm(`Send this reply to ${proposal.to}?`)) return;
    try {
      await api.sendReply(proposal.id, proposal.body);
      setChatMsgs((m) => m.map((msg, i) => (i === idx ? { ...msg, sent: true } : msg)));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const loadChat = useCallback(async (id: string) => {
    try {
      const r = await api.chatHistory(id);
      setChatId(id);
      setChatMsgs(
        r.messages.map((m) => ({ role: m.role, text: m.content, citations: m.citations })),
      );
    } catch {
      /* ignore */
    }
  }, []);

  const openCitation = useCallback((id: string) => {
    // Open the cited email in the reader behind the popup; shrink so it's visible.
    setChatExpanded(false);
    setSelectedId(id);
  }, []);

  const resetChat = useCallback(() => {
    setChatMsgs([]);
    setChatId(undefined);
    setChatInput("");
  }, []);

  const toggleStar = useCallback(
    async (id: string, next: boolean) => {
      setEmails((es) => es.map((e) => (e.id === id ? { ...e, starred: next } : e)));
      setDetail((d) => (d && d.id === id ? { ...d, starred: next } : d));
      try {
        await api.setState(id, { starred: next });
      } catch (e) {
        setError(String(e));
      }
    },
    [],
  );

  const archive = useCallback(
    async (id: string) => {
      try {
        await api.setState(id, { archived: true });
        setDetail(null);
        setSelectedId(null);
        await loadEmails();
        refreshCats();
      } catch (e) {
        setError(String(e));
      }
    },
    [loadEmails, refreshCats],
  );

  const catCount = useMemo(() => {
    const m: Record<string, number> = {};
    cats?.categories.forEach((c) => (m[c.id] = c.count));
    return m;
  }, [cats]);

  const labelById = useMemo(() => {
    const m: Record<string, Label> = {};
    labels.forEach((l) => (m[l.id] = l));
    return m;
  }, [labels]);

  const rows: EmailSummary[] = emails;

  const listTitle = labelFilter
    ? labels.find((l) => l.id === labelFilter)?.name ?? "Label"
    : selectedCat === "all"
      ? "All mail"
      : CAT_LABEL[selectedCat] ?? selectedCat;

  return (
    <div className={`app${chatOpen ? " chat-open" : ""}${chatOpen && chatExpanded ? " chat-expanded" : ""}`}>
      <header className="topbar">
        <div className="brand">
          <div className="mark" aria-hidden>
            <svg {...svgProps}>
              <path d="M3 7l9 6 9-6" />
              <rect x="3" y="5" width="18" height="14" rx="2" />
            </svg>
          </div>
          <div>
            <div className="brand-name">Inbox Agent</div>
            <div className="brand-sub">triage · chat · guard</div>
          </div>
        </div>
        <div className="top-right">
          <span className="env">
            <span className="live" />
            {syncMsg ?? (cats ? `${cats.total} emails · ${cats.flagged} flagged` : "connecting…")}
          </span>
          <button
            className="compose-launch"
            onClick={() => setComposeOpen(true)}
            title="Compose a new email"
            aria-label="Compose a new email"
          >
            <Compose />
            Compose
          </button>
          <button
            className="icon-btn"
            onClick={() => doSync(false)}
            disabled={syncing}
            title="Sync with Gmail"
            aria-label="Sync with Gmail"
          >
            <Refresh spinning={syncing} />
          </button>
          <ThemeToggle />
        </div>
      </header>

      <form className="ask" onSubmit={(e) => e.preventDefault()}>
        <span className="search" aria-hidden>
          <svg {...svgProps}>
            <circle cx="11" cy="11" r="7" />
            <path d="M21 21l-4-4" />
          </svg>
        </span>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search your inbox…  sender, subject, or any word"
          aria-label="Search your inbox"
        />
        {search ? (
          <button type="button" className="clear" onClick={() => setSearch("")}>
            clear
          </button>
        ) : (
          <span className="kbd">/</span>
        )}
      </form>

      {error && (
        <div className="pane" style={{ padding: "14px 16px", color: "var(--danger)" }}>
          {error}. Is the API running? Try <code>inbox-agent serve</code>.
        </div>
      )}

      <div className="console">
        <aside className="pane rail">
            <nav className="rail-scroll" aria-label="Categories">
              {RAIL_ORDER.map((id) => (
                <button
                  key={id}
                  className="cat"
                  aria-selected={selectedCat === id}
                  onClick={() => pickCategory(id)}
                >
                <span className="dot" style={{ background: CAT_META[id].dot }} />
                <span className="cat-name">{CAT_META[id].label}</span>
                <span className="cat-count mono">
                  {id === "all" ? cats?.total ?? "" : catCount[id] ?? ""}
                </span>
              </button>
            ))}
            <div className="rail-sep" />
            <button
              className="cat flagged"
              aria-selected={selectedCat === "flagged"}
              onClick={() => pickCategory("flagged")}
            >
              <span className="shield-sm">
                <Shield />
              </span>
              <span className="cat-name">Flagged</span>
              <span className="cat-count mono">{cats?.flagged ?? ""}</span>
            </button>

            <LabelRail
              labels={labels}
              activeId={labelFilter}
              organizing={organizing}
              onSelect={selectLabel}
              onCreate={createLabel}
              onDelete={deleteLabel}
              onOrganize={autoOrganize}
            />
          </nav>
        </aside>

        <section className="pane">
          <div className="pane-head">
            <span className="pane-title">{listTitle}</span>
            <span className="pane-meta">
              {rows.length} {rows.length === 1 ? "email" : "emails"}
            </span>
          </div>

          <div className="toolbar">
              <select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort by">
                <option value="date">Newest</option>
                <option value="sender">Sender</option>
                <option value="subject">Subject</option>
                <option value="category">Category</option>
              </select>
              <button
                className="toggle"
                aria-pressed={filter === "starred"}
                onClick={() => setFilter((f) => (f === "starred" ? "none" : "starred"))}
              >
                Starred
              </button>
              <button
                className="toggle"
                aria-pressed={filter === "unread"}
                onClick={() => setFilter((f) => (f === "unread" ? "none" : "unread"))}
              >
                Unread
              </button>
            </div>

          <div className="list-scroll">
            {rows.length === 0 && <div className="empty">Nothing here.</div>}
            {rows.map((m) => (
              <button
                key={m.id}
                className={`msg${!m.read ? " unread" : ""}`}
                aria-selected={m.id === selectedId}
                onClick={() => setSelectedId(m.id)}
              >
                <span
                  className="avatar"
                  style={{ background: tintFor(m.category || "all"), color: dotFor(m.category || "all") }}
                >
                  {initials(m.from_name)}
                </span>
                <span className="msg-main">
                  <span className="msg-from">
                    {m.from_name}
                    {m.flagged.length > 0 && (
                      <span className="flag-chip">
                        <Shield />
                        manipulation
                      </span>
                    )}
                  </span>
                  <span className="msg-subj">{m.subject}</span>
                  <span className="msg-snip">{m.snippet}</span>
                  {m.labels.length > 0 && (
                    <span className="row-labels">
                      {m.labels.map(
                        (lid) =>
                          labelById[lid] && (
                            <span
                              key={lid}
                              className="row-label"
                              style={{
                                color: labelById[lid].color,
                                background: `color-mix(in srgb, ${labelById[lid].color} 15%, transparent)`,
                              }}
                            >
                              {labelById[lid].name}
                            </span>
                          ),
                      )}
                    </span>
                  )}
                </span>
                <span className="row-star">
                  <span
                    role="button"
                    tabIndex={0}
                    className={`star-btn${m.starred ? " on" : ""}`}
                    title={m.starred ? "Unstar" : "Star"}
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleStar(m.id, !m.starred);
                    }}
                  >
                    <Star fill={m.starred} />
                  </span>
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
            {detail ? (
              <Reader
                email={detail}
                labels={labels}
                onStar={() => toggleStar(detail.id, !detail.starred)}
                onArchive={() => archive(detail.id)}
                onToggleLabel={(labelId, on) => toggleEmailLabel(detail.id, labelId, on)}
              />
            ) : (
              <div className="placeholder">Select an email to read it.</div>
            )}
          </div>
        </section>
      </div>

      <ChatWidget
        open={chatOpen}
        expanded={chatExpanded}
        messages={chatMsgs}
        input={chatInput}
        busy={chatBusy}
        chats={chatList}
        activeChatId={chatId}
        onOpen={() => setChatOpen(true)}
        onClose={() => setChatOpen(false)}
        onToggleExpand={() => setChatExpanded((v) => !v)}
        onInput={setChatInput}
        onSend={() => sendChat(chatInput)}
        onReset={resetChat}
        onSelectChat={loadChat}
        onCitation={openCitation}
        onSendReply={sendChatReply}
      />

      <ComposeModal open={composeOpen} onClose={() => setComposeOpen(false)} />
    </div>
  );
}

function ChatWidget({
  open,
  expanded,
  messages,
  input,
  busy,
  chats,
  activeChatId,
  onOpen,
  onClose,
  onToggleExpand,
  onInput,
  onSend,
  onReset,
  onSelectChat,
  onCitation,
  onSendReply,
}: {
  open: boolean;
  expanded: boolean;
  messages: ChatMsg[];
  input: string;
  busy: boolean;
  chats: ChatListItem[];
  activeChatId?: string;
  onOpen: () => void;
  onClose: () => void;
  onToggleExpand: () => void;
  onInput: (v: string) => void;
  onSend: () => void;
  onReset: () => void;
  onSelectChat: (id: string) => void;
  onCitation: (id: string) => void;
  onSendReply: (idx: number, proposal: ReplyProposal) => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy, open, expanded]);

  // Grow the composer with its content, up to a cap; then it scrolls internally.
  const taRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [input, open, expanded]);

  const suggestions = [
    "How many unread emails do I have?",
    "Label all from Instagram as Social",
    "Mark everything from TikTok as read",
    "Reply to Priya saying I'll review it Friday",
  ];

  if (!open) {
    return (
      <button className="chat-fab" onClick={onOpen} aria-label="Chat with your inbox">
        <Sparkle />
        <span>Ask</span>
      </button>
    );
  }

  return (
    <div
      className={`chat-pop${expanded ? " expanded" : ""}`}
      role="dialog"
      aria-label="Chat with your inbox"
    >
      <div className="chat-pop-head">
        <span className="pane-title">
          <span className="chat-title-spark">
            <Sparkle />
          </span>
          Chat with your inbox
        </span>
        <span className="chat-head-actions">
          <button className="chat-icon" onClick={onReset} title="New chat" aria-label="New chat">
            <Plus />
          </button>
          <button
            className="chat-icon"
            onClick={onToggleExpand}
            title={expanded ? "Shrink" : "Expand"}
            aria-label="Toggle chat size"
          >
            <Expand />
          </button>
          <button className="chat-icon" onClick={onClose} title="Close" aria-label="Close chat">
            <Close />
          </button>
        </span>
      </div>

      <div className="chat-pop-body">
        {expanded && (
          <aside className="chat-pop-rail">
            <div className="chat-pop-rail-head">Recent chats</div>
            <div className="chat-list">
              {chats.length === 0 && <div className="chat-list-empty">No saved chats yet.</div>}
              {chats.map((c) => (
                <button
                  key={c.id}
                  className="chat-list-item"
                  aria-selected={c.id === activeChatId}
                  onClick={() => onSelectChat(c.id)}
                >
                  <span className="cli-title">{c.title || "Untitled chat"}</span>
                  <span className="cli-date">{c.updated_at.slice(0, 10)}</span>
                </button>
              ))}
            </div>
          </aside>
        )}

        <div className="chat-pop-main">
          <div className="chat-scroll" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="chat-welcome">
            <div className="chat-welcome-spark">
              <Sparkle />
            </div>
            <h2>Ask me about your inbox</h2>
            <p>
              I read only the emails that match your question, answer in plain language, and cite
              the ones I used. Everything runs on your local model — nothing leaves this machine.
            </p>
            <div className="chat-suggest">
              {suggestions.map((s) => (
                <button key={s} onClick={() => onInput(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`bubble-row ${m.role}`}>
            {m.role === "assistant" && (
              <span className="bubble-avatar" aria-hidden>
                <Sparkle />
              </span>
            )}
            <div className={`bubble ${m.role}${m.error ? " error" : ""}`}>
              <div className="bubble-text">{m.text}</div>
              {m.proposal && m.proposal.body && (
                <div className="proposal">
                  <div className="proposal-body">{m.proposal.body}</div>
                  <button
                    className="send-btn"
                    disabled={m.sent}
                    onClick={() => onSendReply(i, m.proposal!)}
                  >
                    {m.sent ? "Sent ✓" : `Send to ${m.proposal.to}`}
                  </button>
                </div>
              )}
              {m.citations && m.citations.length > 0 && (
                <div className="cites">
                  {m.citations.map((c) => (
                    <button key={c.id} className="cite" onClick={() => onCitation(c.id)}>
                      <span className="cite-subj">{c.subject || "(no subject)"}</span>
                      <span className="cite-meta">
                        {c.from_name} · {c.date.slice(0, 10)}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {busy && (
          <div className="bubble-row assistant">
            <span className="bubble-avatar" aria-hidden>
              <Sparkle />
            </span>
            <div className="bubble assistant">
              <span className="typing">
                <i />
                <i />
                <i />
              </span>
            </div>
          </div>
        )}
          </div>

          <form
            className="chat-input"
            onSubmit={(e) => {
              e.preventDefault();
              onSend();
            }}
          >
            <textarea
              ref={taRef}
              className="chat-textarea"
              value={input}
              rows={1}
              onChange={(e) => onInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  onSend();
                }
              }}
              placeholder="Message your inbox…  (Shift+Enter for a new line)"
              aria-label="Message your inbox"
              autoFocus
            />
            <button type="submit" disabled={busy || !input.trim()} aria-label="Send">
              <Arrow />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

function Reader({
  email,
  labels,
  onStar,
  onArchive,
  onToggleLabel,
}: {
  email: EmailDetail;
  labels: Label[];
  onStar: () => void;
  onArchive: () => void;
  onToggleLabel: (labelId: string, on: boolean) => void;
}) {
  const flagged = email.flagged.length > 0;
  const [labelMenu, setLabelMenu] = useState(false);
  const [draft, setDraft] = useState<string | null>(null);
  const [drafting, setDrafting] = useState(false);
  const [draftErr, setDraftErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);

  useEffect(() => {
    setDraft(null);
    setDraftErr(null);
    setCopied(false);
    setSending(false);
    setSent(false);
  }, [email.id]);

  const sendReply = async () => {
    if (draft === null || sending || sent) return;
    if (!window.confirm(`Send this reply to ${email.from_name} <${email.from_addr}>?`)) return;
    setSending(true);
    setDraftErr(null);
    try {
      await api.sendReply(email.id, draft);
      setSent(true);
    } catch (e) {
      setDraftErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  };

  const runDraft = async () => {
    setDrafting(true);
    setDraftErr(null);
    try {
      const r = await api.draftReply(email.id);
      setDraft(r.draft);
    } catch (e) {
      setDraftErr(e instanceof Error ? e.message : String(e));
    } finally {
      setDrafting(false);
    }
  };

  return (
    <>
      <div className="reader-head">
        <div className="reader-from-row">
          <span
            className="avatar"
            style={{ background: tintFor(email.category), color: dotFor(email.category) }}
          >
            {initials(email.from_name)}
          </span>
          <span>
            <div className="rfr-name">{email.from_name}</div>
            <div className="rfr-addr">{email.from_addr}</div>
          </span>
          <span className="reader-actions">
            <button
              className={`act-btn${email.starred ? " on" : ""}`}
              onClick={onStar}
              title={email.starred ? "Unstar" : "Star"}
            >
              <Star fill={email.starred} />
              {email.starred ? "Starred" : "Star"}
            </button>
            <button className="act-btn" onClick={onArchive} title="Archive">
              <Archive />
              Archive
            </button>
          </span>
        </div>
        <div className="reader-subj">{email.subject}</div>
        <div className="rfr-date" style={{ marginTop: "6px" }}>
          {email.date.replace("T", " ").slice(0, 16)}
        </div>
      </div>

      <div className="verdict-row">
        <span className="chip">
          <span className="dot" style={{ background: dotFor(email.category) }} />
          Triage <b>{CAT_LABEL[email.category] ?? email.category}</b> <span className="tag">stub</span>
        </span>
        {email.thread_id && (
          <span className="chip">
            Thread <b className="mono">{email.thread_id}</b>
          </span>
        )}
        {!flagged && (
          <span className="chip subtle" title="No prompt-injection signals found in this email">
            <Check /> Checked
          </span>
        )}
      </div>

      <div className="label-row">
        {email.labels.map((lid) => {
          const l = labels.find((x) => x.id === lid);
          if (!l) return null;
          return (
            <span
              key={lid}
              className="label-chip"
              style={{ color: l.color, borderColor: l.color }}
            >
              <span className="label-dot" style={{ background: l.color }} />
              {l.name}
              <button
                className="label-x"
                onClick={() => onToggleLabel(lid, false)}
                aria-label={`Remove ${l.name}`}
              >
                <Close />
              </button>
            </span>
          );
        })}
        <span className="label-add">
          <button className="label-add-btn" onClick={() => setLabelMenu((v) => !v)}>
            <Plus /> Label
          </button>
          {labelMenu && (
            <div className="label-menu">
              {labels.length === 0 && <div className="label-menu-empty">No labels yet.</div>}
              {labels
                .filter((l) => !email.labels.includes(l.id))
                .map((l) => (
                  <button
                    key={l.id}
                    className="label-menu-item"
                    onClick={() => {
                      onToggleLabel(l.id, true);
                      setLabelMenu(false);
                    }}
                  >
                    <span className="label-dot" style={{ background: l.color }} />
                    {l.name}
                  </button>
                ))}
            </div>
          )}
        </span>
      </div>

      {flagged && (
        <div className="sec warn">
          <div className="sec-head">
            <Shield /> Manipulation attempt detected
          </div>
          <div className="sec-body">
            This email contains text aimed at hijacking an AI assistant. It was treated as untrusted
            data and no instruction in it was followed.
          </div>
          <div className="signals">
            {email.flagged.map((s) => (
              <span className="sig" key={s}>
                {s}
              </span>
            ))}
          </div>
          <div className="sec-foot">
            Architectural guardrail: triage output is clamped, so this could only ever become a
            category label, never an action.
          </div>
        </div>
      )}

      {email.body_html ? (
        // Sanitized server-side (nh3) — see api.py / sanitize.py.
        <div className="body-html" dangerouslySetInnerHTML={{ __html: email.body_html }} />
      ) : (
        <div className="body-text">{email.body}</div>
      )}

      <div className="reader-foot">
        <button className="draft-btn" onClick={runDraft} disabled={drafting}>
          <svg {...svgProps}>
            <path d="M4 20h4L18 10l-4-4L4 16z" />
            <path d="M14 6l4 4" />
          </svg>
          {drafting ? "Drafting…" : draft !== null ? "Regenerate" : "Draft a reply"}
        </button>
        <span className="soon">
          a suggestion only
          <br />
          you review and send it yourself
        </span>
      </div>

      {draftErr && <div className="draft-err">{draftErr}</div>}

      {draft !== null && (
        <div className="draft-box">
          <div className="draft-box-head">
            <span>Suggested reply</span>
            <span className="draft-actions">
              <button
                className="chat-mini"
                onClick={() => {
                  navigator.clipboard?.writeText(draft);
                  setCopied(true);
                }}
              >
                {copied ? "Copied" : "Copy"}
              </button>
              <button className="send-btn" onClick={sendReply} disabled={sending || sent}>
                {sent ? "Sent ✓" : sending ? "Sending…" : "Send"}
              </button>
            </span>
          </div>
          <textarea
            className="draft-text"
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
              setCopied(false);
            }}
            rows={7}
          />
          <div className="draft-note">
            Nothing is sent — this is a local suggestion. Copy it into your reply when you are happy
            with it.
          </div>
        </div>
      )}
    </>
  );
}

const LABEL_COLORS = [
  "#2f6bea",
  "#7a5cf0",
  "#0e9c9c",
  "#1f8a6b",
  "#c23b4e",
  "#b0791a",
  "#d1477a",
  "#5a6b86",
];

function LabelRail({
  labels,
  activeId,
  organizing,
  onSelect,
  onCreate,
  onDelete,
  onOrganize,
}: {
  labels: Label[];
  activeId: string | null;
  organizing: boolean;
  onSelect: (id: string) => void;
  onCreate: (name: string, color: string, instructions: string) => void;
  onDelete: (id: string) => void;
  onOrganize: () => void;
}) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [color, setColor] = useState(LABEL_COLORS[0]);
  const [instructions, setInstructions] = useState("");

  const submit = () => {
    const n = name.trim();
    if (!n) return;
    onCreate(n, color, instructions.trim());
    setName("");
    setInstructions("");
    setColor(LABEL_COLORS[0]);
    setCreating(false);
  };

  return (
    <>
      <div className="rail-sep" />
      <div className="rail-labels-head">
        <span>Labels</span>
        <button className="rail-add" onClick={() => setCreating((v) => !v)} aria-label="New label">
          <Plus />
        </button>
      </div>

      {labels.map((l) => (
        <div key={l.id} className={`label-cat${activeId === l.id ? " sel" : ""}`}>
          <button
            className="label-cat-main"
            aria-selected={activeId === l.id}
            onClick={() => onSelect(l.id)}
          >
            <span className="dot" style={{ background: l.color }} />
            <span className="cat-name">{l.name}</span>
            <span className="cat-count mono">{l.count ?? 0}</span>
          </button>
          <button className="label-del" onClick={() => onDelete(l.id)} aria-label={`Delete ${l.name}`}>
            <Close />
          </button>
        </div>
      ))}

      {creating && (
        <div className="label-form">
          <input
            className="label-form-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Label name"
            aria-label="Label name"
          />
          <div className="label-swatches">
            {LABEL_COLORS.map((c) => (
              <button
                key={c}
                className={`swatch${color === c ? " on" : ""}`}
                style={{ background: c }}
                onClick={() => setColor(c)}
                aria-label={`color ${c}`}
              />
            ))}
          </div>
          <textarea
            className="label-form-inst"
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            placeholder="What does this label mean? The assistant uses this to auto-apply it — e.g. anything about money, bills, or invoices."
            rows={3}
            aria-label="Label instructions"
          />
          <div className="label-form-actions">
            <button className="chat-mini" onClick={submit}>
              Add
            </button>
            <button className="chat-mini" onClick={() => setCreating(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {labels.length > 0 && (
        <button className="organize-btn" onClick={onOrganize} disabled={organizing}>
          <Sparkle /> {organizing ? "Organizing…" : "Auto-organize"}
        </button>
      )}
    </>
  );
}

function ComposeModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [instruction, setInstruction] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setTo("");
      setSubject("");
      setBody("");
      setInstruction("");
      setSent(false);
      setErr(null);
    }
  }, [open]);

  if (!open) return null;

  const draftIt = async () => {
    if (!instruction.trim() || drafting) return;
    setDrafting(true);
    setErr(null);
    try {
      const r = await api.composeDraft(instruction);
      setBody(r.draft);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setDrafting(false);
    }
  };

  const sendIt = async () => {
    if (!to.trim() || !body.trim() || sending || sent) return;
    if (!window.confirm(`Send this email to ${to}?`)) return;
    setSending(true);
    setErr(null);
    try {
      await api.sendNew(to, subject, body);
      setSent(true);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <span className="pane-title">
            <span className="chat-title-spark">
              <Compose />
            </span>
            New message
          </span>
          <button className="chat-icon" onClick={onClose} aria-label="Close">
            <Close />
          </button>
        </div>

        <div className="compose-body">
          <input
            className="compose-field"
            placeholder="To"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            aria-label="To"
          />
          <input
            className="compose-field"
            placeholder="Subject"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            aria-label="Subject"
          />
          <textarea
            className="compose-text"
            placeholder="Write your message…"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={8}
            aria-label="Message body"
          />
          <div className="compose-ai">
            <span className="chat-title-spark">
              <Sparkle />
            </span>
            <input
              className="compose-field"
              placeholder="…or describe it and let AI draft — e.g. ask Bob to lunch Friday"
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  draftIt();
                }
              }}
              aria-label="Describe the email for AI"
            />
            <button className="chat-mini" onClick={draftIt} disabled={drafting}>
              {drafting ? "Drafting…" : "Draft"}
            </button>
          </div>
          {err && <div className="draft-err">{err}</div>}
        </div>

        <div className="modal-foot">
          <button className="chat-mini" onClick={onClose}>
            Cancel
          </button>
          <button
            className="send-btn"
            onClick={sendIt}
            disabled={sending || sent || !to.trim() || !body.trim()}
          >
            {sent ? "Sent ✓" : sending ? "Sending…" : "Send"}
          </button>
        </div>
      </div>
    </div>
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
      <svg {...svgProps}>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M19 5l-1.5 1.5M6.5 17.5L5 19" />
      </svg>
    </button>
  );
}
